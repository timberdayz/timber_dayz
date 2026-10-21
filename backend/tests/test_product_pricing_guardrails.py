from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

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



def test_router_exposes_pricing_policy_routes():
    from pathlib import Path

    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    # 只匹配到路径为止的装饰器前缀：新路由必须声明 response_model（AGENTS.md 硬要求），
    # 精确匹配整个装饰器会因为多了 ", response_model=..." 而失配
    assert '@router.get("/api/sku-pricing-policies"' in source
    assert '@router.get("/api/sku-pricing-policies/current"' in source
    assert '@router.post("/api/sku-pricing-policies"' in source
    assert '@router.put("/api/sku-pricing-policies/{min_age_days}"' in source
    # 四条端点都必须声明 response_model
    for line in source.splitlines():
        if "@router." in line and "sku-pricing-policies" in line:
            assert "response_model" in line, line
    assert "_require_platform_fee_editor" in source


@pytest.mark.asyncio
async def test_pricing_policy_crud_and_versioned_update(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    await pricing_seed()

    created = await pg_async_client.post(
        "/api/sku-pricing-policies",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 30,
            "tier_label": "测试档",
            "discount_rate": 0.12,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    current = await pg_async_client.get(
        "/api/sku-pricing-policies/current", headers=pricing_auth_headers
    )
    assert current.status_code == 200
    assert any(row["min_age_days"] == 30 for row in current.json())

    # 未来生效日期 -> 422
    future = await pg_async_client.post(
        "/api/sku-pricing-policies",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 45,
            "tier_label": "未来档",
            "discount_rate": 0.12,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert future.status_code == 422

    # 同一档位再 POST -> 409
    duplicate = await pg_async_client.post(
        "/api/sku-pricing-policies",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 30,
            "tier_label": "测试档2",
            "discount_rate": 0.13,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    assert duplicate.status_code == 409

    # 同日改率 -> 原地更新，仍只有一条当前行
    same_day = await pg_async_client.put(
        "/api/sku-pricing-policies/30",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 30,
            "tier_label": "测试档",
            "discount_rate": 0.14,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    assert same_day.status_code == 200, same_day.text
    current = await pg_async_client.get(
        "/api/sku-pricing-policies/current", headers=pricing_auth_headers
    )
    rows = [row for row in current.json() if row["min_age_days"] == 30]
    assert len(rows) == 1
    assert rows[0]["discount_rate"] == pytest.approx(0.14)

    # 改档位边界（路径=30 旧起点, body=45 新起点）-> 关旧行 + 建新行
    # ⚠️ 新起点必须选一个**空闲**档位：seed 已经占了 0/60/90/120。
    # 改到 60 会撞 uq_sku_pricing_policies_current（每个档位至多一条当前行）-> 409，
    # 测的就不是「改边界」而是「冲突」了。
    retier = await pg_async_client.put(
        "/api/sku-pricing-policies/30",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 45,
            "tier_label": "改边界档",
            "discount_rate": 0.15,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    assert retier.status_code == 200, retier.text
    current = await pg_async_client.get(
        "/api/sku-pricing-policies/current", headers=pricing_auth_headers
    )
    tiers = {row["min_age_days"] for row in current.json()}
    assert 45 in tiers
    assert 30 not in tiers

    # 改成已被占用的起点（seed 占了 60）-> 409
    conflict = await pg_async_client.put(
        "/api/sku-pricing-policies/45",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 60,
            "tier_label": "冲突档",
            "discount_rate": 0.16,
            "target_margin_rate": 0.22,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    assert conflict.status_code == 409, conflict.text


@pytest.mark.asyncio
async def test_pricing_policy_write_is_audited(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    await pricing_seed()
    await pg_async_client.post(
        "/api/sku-pricing-policies",
        headers=pricing_auth_headers,
        json={
            "min_age_days": 77,
            "tier_label": "审计档",
            "discount_rate": 0.2,
            "target_margin_rate": 0.18,
            "platform_basis": "tiktok",
            "effective_from": date.today().isoformat(),
        },
    )
    result = await pg_session.execute(
        text(
            "SELECT count(*) FROM public.fact_audit_logs "
            "WHERE resource_type = 'sku_pricing_policy'"
        )
    )
    assert result.scalar() >= 1


@pytest.mark.asyncio
async def test_platform_fee_rate_partial_update_keeps_other_fields(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """只传 default_creator_commission_rate 时，其余费率与来源标记保持原值。

    既有实现是无条件赋值（`row.default_fee_rate = body.default_fee_rate`），
    未传的字段会被写成 NULL —— 这会让平台佣金率、来源标记被静默清空。
    """
    from modules.core.db import DimPlatform

    await pricing_seed()
    platform_row = await pg_session.get(DimPlatform, "tiktok")
    platform_row.fee_rate_source = "b_class_measured_2026_01_07"
    platform_row.fee_rate_version = "v2"
    await pg_session.flush()

    resp = await pg_async_client.patch(
        "/api/platforms/tiktok/fee-rate",
        headers=pricing_auth_headers,
        json={"default_creator_commission_rate": 0.09},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["default_creator_commission_rate"] == pytest.approx(0.09)
    # 其余保持原值，不得被刷成 NULL
    assert body["default_fee_rate"] == pytest.approx(0.0737)
    assert body["other_cost_rate"] == pytest.approx(0.2727)
    assert body["fee_rate_source"] == "b_class_measured_2026_01_07"
    assert body["fee_rate_version"] == "v2"


@pytest.mark.asyncio
async def test_platform_fee_rate_and_sku_writes_are_audited(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """平台成本率与 SKU 覆盖值/达人佣金率的写操作都要产生审计。"""
    await pricing_seed()

    await pg_async_client.patch(
        "/api/platforms/tiktok/fee-rate",
        headers=pricing_auth_headers,
        json={"default_creator_commission_rate": 0.09},
    )
    await pg_async_client.patch(
        "/api/skus/9001",
        headers=pricing_auth_headers,
        json={
            "creator_commission_rate": 0.15,
            "min_selling_price_override": 20.0,
        },
    )
    for resource_type in ("platform_fee_rate", "sku"):
        result = await pg_session.execute(
            text(
                "SELECT count(*) FROM public.fact_audit_logs "
                "WHERE resource_type = :t"
            ),
            {"t": resource_type},
        )
        assert result.scalar() >= 1, resource_type
