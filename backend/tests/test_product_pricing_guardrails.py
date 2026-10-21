from decimal import Decimal

import pytest

from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_discount_guard,
    compute_min_selling_price,
    compute_sku_pricing,
    select_age_tier,
)

# tiktok 基准值（实测，见 spec §2.3 / §1.2）
OTHER_COST_RATE = Decimal("0.2727")
CREATOR_COMMISSION_RATE = Decimal("0.0606")
RETURN_LOSS_RATE = Decimal("0.0467")
DAMAGE_RATE = Decimal("0.0158")


def _policy(min_age_days, label, discount_rate, target_margin_rate):
    return {
        "min_age_days": min_age_days,
        "tier_label": label,
        "discount_rate": Decimal(str(discount_rate)),
        "target_margin_rate": Decimal(str(target_margin_rate)),
    }


def test_cost_floor_matches_spec_example():
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("28.23")


def test_cost_floor_does_not_double_count_platform_commission():
    """平台佣金率已含在 other_cost_rate 内，误加会让底线偏高 26%。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    # 若误加平台佣金 0.0737，分母变 0.2805，底线会变成 35.65
    assert floor != Decimal("35.65")


def test_cost_floor_uses_sku_creator_commission_rate_when_provided():
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=Decimal("0.15"),
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("37.76")


def test_rates_are_not_quantized():
    """费率不得过 _money 量化：0.2727 -> 0.27 会让底线从 28.23 变 28.02。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=Decimal("0.2727"),
        creator_commission_rate=Decimal("0.0606"),
        spu_return_loss_rate=Decimal("0.0467"),
        spu_damage_rate=Decimal("0.0158"),
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("28.23")


def test_self_consistency_identity():
    """目标利润率 = 实测净利率时，分母必须还原实测采购成本率 0.4261。"""
    denominator = (
        Decimal("1")
        - OTHER_COST_RATE
        - CREATOR_COMMISSION_RATE
        - RETURN_LOSS_RATE
        - DAMAGE_RATE
        - Decimal("0.1781")
    )
    assert denominator == Decimal("0.4261")


def test_discount_guard_uses_current_tier_rate():
    guard = compute_discount_guard(
        reference_selling_price=Decimal("30"),
        discount_rate=Decimal("0.15"),
    )
    assert guard == Decimal("25.50")


def test_discount_guard_is_none_without_reference_price():
    assert compute_discount_guard(reference_selling_price=None, discount_rate=Decimal("0.15")) is None


def test_select_age_tier_picks_largest_boundary_not_exceeding_age():
    policies = [
        _policy(0, "日常", 0.10, 0.25),
        _policy(60, "滞销30天", 0.15, 0.22),
        _policy(90, "滞销60天", 0.20, 0.18),
        _policy(120, "滞销60天以上", 0.30, 0.10),
    ]
    assert select_age_tier(policies, 30)["min_age_days"] == 0
    assert select_age_tier(policies, 59)["min_age_days"] == 0
    assert select_age_tier(policies, 60)["min_age_days"] == 60
    assert select_age_tier(policies, 89)["min_age_days"] == 60
    assert select_age_tier(policies, 90)["min_age_days"] == 90
    assert select_age_tier(policies, 200)["min_age_days"] == 120


def test_select_age_tier_falls_back_to_lowest_boundary_without_age():
    policies = [_policy(0, "日常", 0.10, 0.25), _policy(60, "滞销30天", 0.15, 0.22)]
    assert select_age_tier(policies, None)["min_age_days"] == 0


def test_min_selling_price_takes_the_maximum_of_three_lines():
    result = compute_min_selling_price(
        cost_floor=Decimal("28.23"),
        discount_guard=Decimal("27.00"),
        manual_override=None,
    )
    assert result["min_selling_price"] == Decimal("28.23")
    assert result["source"] == "cost_floor"


def test_min_selling_price_prefers_manual_override():
    result = compute_min_selling_price(
        cost_floor=Decimal("28.23"),
        discount_guard=Decimal("27.00"),
        manual_override=Decimal("26.00"),
    )
    assert result["min_selling_price"] == Decimal("26.00")
    assert result["source"] == "manual_override"
    assert result["is_override"] is True


def test_min_selling_price_reports_unavailable_when_no_line():
    result = compute_min_selling_price(cost_floor=None, discount_guard=None, manual_override=None)
    assert result["min_selling_price"] is None
    assert result["source"] == "unavailable"
    assert result["missing_reasons"]


def test_policy_update_creates_when_no_current_row():
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current=None,
        requested={"min_age_days": 0, "effective_from": date(2026, 10, 20)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "create"
    assert decision["close_current"] is None


def test_policy_update_same_day_updates_in_place():
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_age_days": 0, "effective_from": date(2026, 10, 20)},
        requested={"min_age_days": 0, "effective_from": date(2026, 10, 20), "discount_rate": 0.12},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "update"
    assert decision["close_current"] is None
    # 同日原地改不产生新行，因此不需要 effective_from
    assert "effective_from" not in decision["values"]


def test_policy_update_closes_old_row_and_inserts_new():
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_age_days": 0, "effective_from": date(2026, 10, 1)},
        requested={"min_age_days": 0, "effective_from": date(2026, 10, 15)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "version"
    assert decision["close_current"] == date(2026, 10, 15)


def test_policy_update_retier_when_boundary_changes():
    """路径指向被编辑的档位，body 的 min_age_days 是新起点；两者不同 = 改边界。"""
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_age_days": 0, "effective_from": date(2026, 10, 1)},
        requested={"min_age_days": 45, "effective_from": date(2026, 10, 1)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "retier"
    assert decision["close_current"] == date(2026, 10, 1)
    assert decision["values"]["min_age_days"] == 45


def test_policy_update_rejects_future_and_backdated():
    from datetime import date

    import pytest

    from backend.services.product_pricing_service import (
        PolicyUpdateRejected,
        resolve_policy_update,
    )

    # 未来生效 -> 拒绝
    with pytest.raises(PolicyUpdateRejected):
        resolve_policy_update(
            current={"min_age_days": 0, "effective_from": date(2026, 10, 1)},
            requested={"min_age_days": 0, "effective_from": date(2026, 11, 1)},
            today=date(2026, 10, 20),
        )
    # 回溯生效 -> 拒绝
    with pytest.raises(PolicyUpdateRejected):
        resolve_policy_update(
            current={"min_age_days": 0, "effective_from": date(2026, 10, 20)},
            requested={"min_age_days": 0, "effective_from": date(2026, 10, 1)},
            today=date(2026, 10, 20),
        )


def test_policy_update_rejects_backdated_retier():
    """同时改档位起点 + 把生效日期往回拨 -> 必须 422 拒绝，不能落到 retier 分支。

    retier 会插一行 effective_from 早于当前行的记录，撞 ck_sku_pricing_policy_window
    变成 IntegrityError(409)，与 spec §5.1 的 422 语义不符。
    """
    from datetime import date

    import pytest

    from backend.services.product_pricing_service import (
        PolicyUpdateRejected,
        resolve_policy_update,
    )

    with pytest.raises(PolicyUpdateRejected):
        resolve_policy_update(
            current={"min_age_days": 0, "effective_from": date(2026, 10, 20)},
            requested={"min_age_days": 60, "effective_from": date(2026, 10, 1)},
            today=date(2026, 10, 20),
        )


def test_policy_update_retier_allows_same_day_boundary_change():
    """改档位边界（但生效日期不倒退）-> retier。"""
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_age_days": 0, "effective_from": date(2026, 10, 20)},
        requested={"min_age_days": 30, "effective_from": date(2026, 10, 20)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "retier"
    assert decision["close_current"] == date(2026, 10, 20)
    assert decision["values"]["min_age_days"] == 30


# ---------------------------------------------------------------- 降级链（spec §4.4 / §8.1）

def _pricing(**overrides):
    """完整输入的一组默认值；测试里只覆盖要破坏的那一项。"""
    payload = {
        "purchase_cost": Decimal("10"),
        "reference_selling_price": Decimal("30"),
        "creator_commission_rate": None,
        "platform_creator_commission_rate": CREATOR_COMMISSION_RATE,
        "other_cost_rate": OTHER_COST_RATE,
        "spu_bound": True,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "policy": _policy(0, "日常", 0.10, 0.25),
        "deepest_policy": _policy(120, "滞销60天以上", 0.30, 0.10),
        "min_selling_price_override": None,
        "age_days": None,
    }
    payload.update(overrides)
    return compute_sku_pricing(**payload)


def test_sku_pricing_happy_path_matches_spec_example():
    out = _pricing()
    assert out["min_selling_price"] == pytest.approx(28.23, abs=0.01)
    assert out["min_selling_price_source"] == "cost_floor"
    assert out["current_discount_rate"] == pytest.approx(0.10)
    assert out["clearance_max_discount_rate"] == pytest.approx(0.30)
    assert out["pricing_tier_label"] == "日常"
    assert out["pricing_tier_source"] == "fallback_no_age_data"
    assert out["pricing_age_days"] is None
    assert out["min_selling_price_missing_reasons"] == []


def test_sku_pricing_missing_purchase_cost_degrades_to_discount_guard():
    out = _pricing(purchase_cost=None)
    assert out["min_selling_price"] == pytest.approx(27.00, abs=0.01)
    assert out["min_selling_price_source"] == "discount_guard"
    assert "missing_purchase_cost" in out["min_selling_price_missing_reasons"]


def test_sku_pricing_missing_policy_reports_unavailable():
    out = _pricing(policy=None, deepest_policy=None)
    assert out["min_selling_price"] is None
    assert out["min_selling_price_source"] == "unavailable"
    assert "missing_pricing_policy" in out["min_selling_price_missing_reasons"]


def test_sku_pricing_missing_platform_cost_rate_reports_reason():
    out = _pricing(other_cost_rate=None)
    assert "missing_platform_cost_rate" in out["min_selling_price_missing_reasons"]
    # 成本线算不出，但纪律线仍可算
    assert out["min_selling_price_source"] == "discount_guard"


def test_sku_pricing_missing_creator_commission_rate_reports_reason():
    out = _pricing(creator_commission_rate=None, platform_creator_commission_rate=None)
    assert "missing_creator_commission_rate" in out["min_selling_price_missing_reasons"]


def test_sku_pricing_missing_spu_binding_and_rates_are_distinguished():
    unbound = _pricing(spu_bound=False)
    assert "missing_spu_binding" in unbound["min_selling_price_missing_reasons"]
    assert "missing_spu_rates" not in unbound["min_selling_price_missing_reasons"]

    no_rates = _pricing(spu_return_loss_rate=None)
    assert "missing_spu_rates" in no_rates["min_selling_price_missing_reasons"]
    assert "missing_spu_binding" not in no_rates["min_selling_price_missing_reasons"]


def test_sku_pricing_non_positive_denominator_falls_back_to_discount_guard():
    """分母 ≤ 0 -> 不抛异常，降级到纪律线，并记 non_positive_cost_denominator。"""
    out = _pricing(policy=_policy(0, "日常", 0.10, 0.99))
    assert out["min_selling_price"] == pytest.approx(27.00, abs=0.01)
    assert out["min_selling_price_source"] == "discount_guard"
    assert "non_positive_cost_denominator" in out["min_selling_price_missing_reasons"]


def test_sku_pricing_never_reads_turnover_class():
    """档位只由库龄决定；turnover_class 不得作为定价输入（spec §4.1 / §8.1）。"""
    import inspect

    assert "turnover_class" not in inspect.signature(compute_sku_pricing).parameters


def test_sku_pricing_returns_sku_creator_commission_rate_untouched():
    """SKU 没单独设置佣金时，回给前端的仍是 None（空框），不能把平台兜底值填进输入框。"""
    out = _pricing(creator_commission_rate=None)
    assert out["creator_commission_rate"] is None
    # 但底线计算用的是平台兜底值
    assert out["min_selling_price"] == pytest.approx(28.23, abs=0.01)


def test_sku_pricing_manual_override_wins_and_is_flagged():
    out = _pricing(min_selling_price_override=Decimal("20.00"))
    assert out["min_selling_price"] == pytest.approx(20.00, abs=0.01)
    assert out["min_selling_price_source"] == "manual_override"
    assert out["min_selling_price_is_override"] is True
    assert out["min_selling_price_override"] == pytest.approx(20.00, abs=0.01)
