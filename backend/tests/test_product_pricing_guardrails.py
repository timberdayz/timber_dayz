import ast
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
    select_restock_tier,
)

# tiktok 基准值（实测，见 spec §2.3 / §1.2）
# ⚠️ 批次 9（2026-11-19）口径：
#   分子 = (采购 + 头程 + 仓储 + 贴单 + 尾程) × (1 + SPU退货率 + SPU货损率)
#   分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率
# 平台佣金率**单独进分母**（以前藏在桶里，界面上填了不生效）；
# 桶只装「佣金与尾程之外」的平台侧按收入比例扣款。
PLATFORM_FEE_RATE = Decimal("0.0737")
OTHER_COST_RATE = Decimal("0.2727")
CREATOR_COMMISSION_RATE = Decimal("0.0606")
RETURN_LOSS_RATE = Decimal("0.0467")
DAMAGE_RATE = Decimal("0.0158")
TARGET_MARGIN_RATE = Decimal("0.25")

#: 分母 = 1 − 0.0737 − 0.2727 − 0.0606 − 0.25 = 0.343
COST_FLOOR_DENOMINATOR = Decimal("0.343")
#: 分子 = 10 × (1 + 0.0467 + 0.0158) = 10.625
COST_FLOOR_NUMERATOR = Decimal("10.625")
#: 底线 = 10.625 / 0.343 = 30.9778… ⇒ 30.98
COST_FLOOR = Decimal("30.98")


def _policy(min_restock_days, label, discount_rate, target_margin_rate):
    return {
        "min_restock_days": min_restock_days,
        "tier_label": label,
        "discount_rate": Decimal(str(discount_rate)),
        "target_margin_rate": Decimal(str(target_margin_rate)),
    }


def test_cost_floor_matches_spec_example():
    """成本底线 = (采购 + 履约按件成本) × (1 + 退货率 + 货损率) ÷ 新分母。

    批次 9 口径：分子 10 × (1 + 0.0467 + 0.0158) = 10.625，
    分母 1 − 0.0737 − 0.2727 − 0.0606 − 0.25 = 0.343
    ⇒ 10.625 / 0.343 = 30.9778… ⇒ 30.98
    """
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN_RATE,
    )
    assert floor == COST_FLOOR


def test_cost_floor_subtracts_platform_commission_exactly_once():
    """平台佣金率**单独进分母**，且**只扣一次**。

    ⚠️ 批次 9 之前，模块头明写「平台佣金率已包含在 other_cost_rate 内，
    不得单独进入分母」⇒ 界面上填的佣金率**根本没进计算**。
    现在佣金要单独进分母，所以这条守护反过来写：
    **分母里必须有它，而且只扣一次**（重复扣 ⇒ 底线被抬高）。
    """
    denominator = (
        Decimal("1")
        - PLATFORM_FEE_RATE
        - OTHER_COST_RATE
        - CREATOR_COMMISSION_RATE
        - TARGET_MARGIN_RATE
    )
    assert denominator == COST_FLOOR_DENOMINATOR

    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN_RATE,
    )
    assert floor == (COST_FLOOR_NUMERATOR / denominator).quantize(Decimal("0.01"))
    # 佣金率从 0.0737 抬到 0.18：分母 0.343 → 0.2367，底线 10.625 / 0.2367 = 44.89
    raised = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=Decimal("0.18"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN_RATE,
    )
    assert raised == Decimal("44.89")
    assert raised != floor, "平台佣金率必须真的进分母（以前它藏在桶里，改了没反应）"


def test_cost_floor_uses_sku_creator_commission_rate_when_provided():
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=Decimal("0.15"),
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN_RATE,
    )
    # 分母 = 1 − 0.0737 − 0.2727 − 0.15 − 0.25 = 0.2536 ⇒ 10.625 / 0.2536 = 41.90
    assert floor == Decimal("41.90")


def test_rates_are_not_quantized():
    """费率不得过 _money 量化：0.2727 -> 0.27 会让底线从 30.98 变 30.74。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=Decimal("0.0737"),
        other_cost_rate=Decimal("0.2727"),
        creator_commission_rate=Decimal("0.0606"),
        spu_return_loss_rate=Decimal("0.0467"),
        spu_damage_rate=Decimal("0.0158"),
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == COST_FLOOR


def test_self_consistency_identity():
    """自洽恒等式：分子与分母都要还原成新口径的那两行。

    ⚠️ 批次 9：分母**不再**扣 SPU 两率（两率改成乘进分子），
    分子**必须**乘 (1 + 退货率 + 货损率) —— 分子分母各归各的。
    """
    denominator = (
        Decimal("1")
        - PLATFORM_FEE_RATE
        - OTHER_COST_RATE
        - CREATOR_COMMISSION_RATE
        - TARGET_MARGIN_RATE
    )
    assert denominator == COST_FLOOR_DENOMINATOR

    numerator = Decimal("10") * (Decimal("1") + RETURN_LOSS_RATE + DAMAGE_RATE)
    assert numerator == COST_FLOOR_NUMERATOR
    # 底线 = 分子 ÷ 分母 ⇒ 在底线上卖，利润率恰好是目标利润率
    assert (numerator / denominator).quantize(Decimal("0.01")) == COST_FLOOR


def test_discount_guard_uses_current_tier_rate():
    guard = compute_discount_guard(
        reference_selling_price=Decimal("30"),
        discount_rate=Decimal("0.15"),
    )
    assert guard == Decimal("25.50")


def test_discount_guard_is_none_without_reference_price():
    assert (
        compute_discount_guard(
            reference_selling_price=None, discount_rate=Decimal("0.15")
        )
        is None
    )


def test_select_restock_tier_picks_largest_boundary_not_exceeding_age():
    policies = [
        _policy(0, "日常", 0.10, 0.25),
        _policy(60, "滞销30天", 0.15, 0.22),
        _policy(90, "滞销60天", 0.20, 0.18),
        _policy(120, "滞销60天以上", 0.30, 0.10),
    ]
    assert select_restock_tier(policies, 30)["min_restock_days"] == 0
    assert select_restock_tier(policies, 59)["min_restock_days"] == 0
    assert select_restock_tier(policies, 60)["min_restock_days"] == 60
    assert select_restock_tier(policies, 89)["min_restock_days"] == 60
    assert select_restock_tier(policies, 90)["min_restock_days"] == 90
    assert select_restock_tier(policies, 200)["min_restock_days"] == 120


def test_select_restock_tier_falls_back_to_lowest_boundary_without_age():
    policies = [_policy(0, "日常", 0.10, 0.25), _policy(60, "滞销30天", 0.15, 0.22)]
    assert select_restock_tier(policies, None)["min_restock_days"] == 0


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
    result = compute_min_selling_price(
        cost_floor=None, discount_guard=None, manual_override=None
    )
    assert result["min_selling_price"] is None
    assert result["source"] == "unavailable"
    assert result["missing_reasons"]


def test_policy_update_creates_when_no_current_row():
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current=None,
        requested={"min_restock_days": 0, "effective_from": date(2026, 10, 20)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "create"
    assert decision["close_current"] is None


def test_policy_update_same_day_updates_in_place():
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_restock_days": 0, "effective_from": date(2026, 10, 20)},
        requested={
            "min_restock_days": 0,
            "effective_from": date(2026, 10, 20),
            "discount_rate": 0.12,
        },
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
        current={"min_restock_days": 0, "effective_from": date(2026, 10, 1)},
        requested={"min_restock_days": 0, "effective_from": date(2026, 10, 15)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "version"
    assert decision["close_current"] == date(2026, 10, 15)


def test_policy_update_retier_when_boundary_changes():
    """路径指向被编辑的档位，body 的 min_restock_days 是新起点；两者不同 = 改边界。"""
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_restock_days": 0, "effective_from": date(2026, 10, 1)},
        requested={"min_restock_days": 45, "effective_from": date(2026, 10, 1)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "retier"
    assert decision["close_current"] == date(2026, 10, 1)
    assert decision["values"]["min_restock_days"] == 45


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
            current={"min_restock_days": 0, "effective_from": date(2026, 10, 1)},
            requested={"min_restock_days": 0, "effective_from": date(2026, 11, 1)},
            today=date(2026, 10, 20),
        )
    # 回溯生效 -> 拒绝
    with pytest.raises(PolicyUpdateRejected):
        resolve_policy_update(
            current={"min_restock_days": 0, "effective_from": date(2026, 10, 20)},
            requested={"min_restock_days": 0, "effective_from": date(2026, 10, 1)},
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
            current={"min_restock_days": 0, "effective_from": date(2026, 10, 20)},
            requested={"min_restock_days": 60, "effective_from": date(2026, 10, 1)},
            today=date(2026, 10, 20),
        )


def test_policy_update_retier_allows_same_day_boundary_change():
    """改档位边界（但生效日期不倒退）-> retier。"""
    from datetime import date

    from backend.services.product_pricing_service import resolve_policy_update

    decision = resolve_policy_update(
        current={"min_restock_days": 0, "effective_from": date(2026, 10, 20)},
        requested={"min_restock_days": 30, "effective_from": date(2026, 10, 20)},
        today=date(2026, 10, 20),
    )
    assert decision["action"] == "retier"
    assert decision["close_current"] == date(2026, 10, 20)
    assert decision["values"]["min_restock_days"] == 30


# ---------------------------------------------------------------- 降级链（spec §4.4 / §8.1）


def _pricing(**overrides):
    """完整输入的一组默认值；测试里只覆盖要破坏的那一项。"""
    payload = {
        "purchase_cost": Decimal("10"),
        "reference_selling_price": Decimal("30"),
        "creator_commission_rate": None,
        "platform_creator_commission_rate": CREATOR_COMMISSION_RATE,
        "platform_fee_rate": PLATFORM_FEE_RATE,
        "other_cost_rate": OTHER_COST_RATE,
        "spu_bound": True,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "policy": _policy(0, "日常", 0.10, TARGET_MARGIN_RATE),
        "deepest_policy": _policy(120, "滞销60天以上", 0.30, 0.10),
        "min_selling_price_override": None,
        "days_since_restock": None,
    }
    payload.update(overrides)
    return compute_sku_pricing(**payload)


def test_sku_pricing_happy_path_matches_spec_example():
    out = _pricing()
    assert out["min_selling_price"] == pytest.approx(30.98, abs=0.01)
    assert out["min_selling_price_source"] == "cost_floor"
    assert out["current_discount_rate"] == pytest.approx(0.10)
    assert out["clearance_max_discount_rate"] == pytest.approx(0.30)
    assert out["pricing_tier_label"] == "日常"
    assert out["pricing_tier_source"] == "fallback_no_restock_days"
    assert out["pricing_days_since_restock"] is None
    # ⚠️ 批次 9：底线 30.98 = 分子 10.625（采购 10 × 件损乘数 1.0625）÷ 分母 0.343。
    #    没配尾程 ⇒ 尾程不进底线（**不再**有「成对生效」那套拆分基准），
    #    但底线因此不完整 ⇒ 必须点名缺了什么。
    assert out["min_selling_price_missing_reasons"] == ["missing_delivery_cost"]
    assert out["delivery_cost_in_cost_floor"] is False
    # 批次 9：退役字段不再出现，履约按件成本改为三个独立字段
    assert "cost_floor_delivery_cost_rate" not in out
    assert out["cost_floor_logistics_cost"] is None
    assert out["cost_floor_storage_cost"] is None
    assert out["cost_floor_label_fee"] is None


def test_sku_pricing_missing_platform_fee_rate_reports_reason():
    """缺平台佣金率 ⇒ `missing_platform_fee_rate`，且**不算底线**（批次 9）。"""
    out = _pricing(platform_fee_rate=None)
    assert "missing_platform_fee_rate" in out["min_selling_price_missing_reasons"]
    # 成本线算不出，但纪律线仍可算
    assert out["min_selling_price_source"] == "discount_guard"
    assert out["min_selling_price"] == pytest.approx(27.00, abs=0.01)


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
    # 两条线都算不出时还会带上 no_pricing_input（compute_min_selling_price 的原因）
    assert "no_pricing_input" in out["min_selling_price_missing_reasons"]


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
    assert out["min_selling_price"] == pytest.approx(30.98, abs=0.01)


def test_sku_pricing_manual_override_wins_and_is_flagged():
    out = _pricing(min_selling_price_override=Decimal("20.00"))
    assert out["min_selling_price"] == pytest.approx(20.00, abs=0.01)
    assert out["min_selling_price_source"] == "manual_override"
    assert out["min_selling_price_is_override"] is True
    assert out["min_selling_price_override"] == pytest.approx(20.00, abs=0.01)


def _router_routes(source: str) -> dict[tuple[str, str], bool]:
    """从路由模块源码里抽出 router 装饰器：(HTTP 方法, 路径) -> 是否声明了 response_model。

    这里用 AST 而不是字符串匹配：black 会把 `@router.get("...")` 这种装饰器按行宽拆成
    多行，源码文本匹配会随排版漂移而误判（这正是 CI 的 Code formatting check 与
    本用例曾经互相打架的原因）。AST 只看结构，与排版无关。
    """
    tree = ast.parse(source)
    routes: dict[tuple[str, str], bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "router":
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            path = dec.args[0].value
            if not isinstance(path, str):
                continue
            has_response_model = any(kw.arg == "response_model" for kw in dec.keywords)
            routes[(func.attr, path)] = has_response_model
    return routes


def test_router_exposes_pricing_policy_routes():

    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    routes = _router_routes(source)
    # 四条端点都必须存在，且都必须声明 response_model（AGENTS.md 硬要求）
    expected = {
        ("get", "/api/sku-pricing-policies"),
        ("get", "/api/sku-pricing-policies/current"),
        ("post", "/api/sku-pricing-policies"),
        ("put", "/api/sku-pricing-policies/{min_restock_days}"),
    }
    for method, path in sorted(expected):
        key = (method, path)
        assert key in routes, f"缺少路由 {method.upper()} {path}"
        assert routes[key], f"{method.upper()} {path} 未声明 response_model"
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
            "min_restock_days": 30,
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
    assert any(row["min_restock_days"] == 30 for row in current.json())

    # 未来生效日期 -> 422
    future = await pg_async_client.post(
        "/api/sku-pricing-policies",
        headers=pricing_auth_headers,
        json={
            "min_restock_days": 45,
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
            "min_restock_days": 30,
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
            "min_restock_days": 30,
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
    rows = [row for row in current.json() if row["min_restock_days"] == 30]
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
            "min_restock_days": 45,
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
    tiers = {row["min_restock_days"] for row in current.json()}
    assert 45 in tiers
    assert 30 not in tiers

    # 改成已被占用的起点（seed 占了 60）-> 409
    conflict = await pg_async_client.put(
        "/api/sku-pricing-policies/45",
        headers=pricing_auth_headers,
        json={
            "min_restock_days": 60,
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
            "min_restock_days": 77,
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
    # 生效日期也不得被刷成当天（seed 刻意给的是 2026-09-01）
    assert body["fee_rate_effective_from"] == "2026-09-01"


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


# ---------------------------------------------------------------- SKU 资料页注入


@pytest.mark.asyncio
async def test_list_skus_injects_pricing_payload(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """SKU 列表必须带出定价底线四列的数据，且数值与公式一致。"""
    await pricing_seed()

    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    # ⚠️ 批次 9：**没传仓** ⇒ 尾程算不出来（尾程是「平台 × 仓」粒度的量，不能猜）
    #    ⇒ 尾程不进底线 ⇒ 底线 = 分子 10.625（采购 10 × 件损乘数 1.0625）÷ 分母 0.343
    #    = 30.98（> 纪律线 30*0.9 = 27.00）
    #    但底线因此不完整 ⇒ 必须点名缺了什么。
    assert row["min_selling_price"] == pytest.approx(30.98, abs=0.01)
    assert row["min_selling_price_source"] == "cost_floor"
    assert row["min_selling_price_is_override"] is False
    assert row["current_discount_rate"] == pytest.approx(0.10)
    assert row["clearance_max_discount_rate"] == pytest.approx(0.30)
    assert row["pricing_tier_label"] == "日常"
    # 测试库没有 mart 表 -> 回落日常档
    assert row["pricing_tier_source"] == "fallback_no_restock_days"
    assert row["pricing_days_since_restock"] is None
    # ⚠️ 批次 6：这个种子 SKU 是**包邮**的（商家承担尾程）⇒ 没传仓 ⇒ 尾程算不出来
    #    ⇒ 尾程不进底线，但底线因此不完整 ⇒ 必须点名缺了什么。
    # ⚠️ 批次 9 P2：没传仓 ⇒ 履约按件成本（头程/仓储/贴单）也算不出来 ⇒ 同样要点名。
    assert row["min_selling_price_missing_reasons"] == [
        "missing_delivery_cost",
        "missing_warehouse_for_fulfillment",
    ]
    assert row["delivery_cost_in_cost_floor"] is False
    # SKU 没单独设佣金 -> 返回 None（前端输入框留空），兜底值单独给
    assert row["creator_commission_rate"] is None
    assert row["creator_commission_rate_fallback"] == pytest.approx(0.0606)


@pytest.mark.asyncio
async def test_list_skus_with_warehouse_includes_delivery_cost_in_floor(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """批次 4 · 仓维度统一：传了仓 ⇒ 底线**含尾程**。

    尾程是「平台 × 仓 × 重量」粒度的量，所以同一个 SKU 在不同仓的底线可以不同 ——
    这正是按件计费尾程的意义（重货不该和轻货共用一条底线）。

    ⚠️ 批次 9：尾程**直接进分子**（不再有「成对生效」那套拆分基准），
    且履约按件成本（头程/仓储/贴单）也进分子：
    分子 = (采购 10 + 头程 0.05 + 仓储 3.00 + 贴单 0.50 + 尾程 5) × 1.0625 = 19.709375
    分母 = 1 − 0.0737(平台佣金) − 0.2727(桶) − 0.0606(达人) − 0.25(目标利润) = 0.343
    ⇒ 19.709375 / 0.343 = 57.4617… ⇒ 57.46
    """
    await pricing_seed()

    resp = await pg_async_client.get(
        "/api/skus",
        headers=pricing_auth_headers,
        params={"platform_code": "tiktok", "warehouse_code": "MY-01"},
    )
    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["min_selling_price"] == pytest.approx(57.46, abs=0.01)
    assert row["delivery_cost_in_cost_floor"] is True
    assert row["cost_floor_delivery_cost"] == pytest.approx(5.0)
    assert row["min_selling_price_missing_reasons"] == []


@pytest.mark.asyncio
async def test_list_skus_reflects_manual_override_and_creator_commission(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """人工覆盖值与达人佣金率写进去后，列表算出的底线要跟着变。"""
    await pricing_seed()

    resp = await pg_async_client.patch(
        "/api/skus/9001",
        headers=pricing_auth_headers,
        json={"creator_commission_rate": 0.15},
    )
    assert resp.status_code == 200, resp.text

    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    # 分子 10.625 ÷ (1 - 0.0737 - 0.2727 - 0.15 - 0.25) = 10.625 / 0.2536 = 41.90
    assert row["min_selling_price"] == pytest.approx(41.90, abs=0.01)
    assert row["min_selling_price_source"] == "cost_floor"
    assert row["creator_commission_rate"] == pytest.approx(0.15)
    # 兜底值仍是平台默认，不受 SKU 值影响
    assert row["creator_commission_rate_fallback"] == pytest.approx(0.0606)

    # 人工覆盖值可以低于成本线（人工有权拍板）。
    # ⚠️ 阶段 2.1b 起覆盖是 **SKU × 平台** 的量，写在独立接口上，
    #    不再挂在 SKU 主数据上（一个数套所有平台，口径不对；而且那张表
    #    会被「采集机 → 云端」同步 TRUNCATE ⇒ 覆盖值每次同步都蒸发）。
    resp = await pg_async_client.patch(
        "/api/skus/9001/pricing-override",
        headers=pricing_auth_headers,
        json={"platform_code": "tiktok", "min_selling_price_override": 20.0},
    )
    assert resp.status_code == 200, resp.text
    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["min_selling_price"] == pytest.approx(20.0, abs=0.01)
    assert row["min_selling_price_source"] == "manual_override"
    assert row["min_selling_price_is_override"] is True
    assert row["min_selling_price_override"] == pytest.approx(20.0, abs=0.01)


@pytest.mark.asyncio
async def test_manual_override_applies_even_when_platform_is_not_passed(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """**不传平台**时人工覆盖也要生效（阶段 2.1b 的回归防线）。

    背景：底线的费率在"不传平台"时走的是**回落后的 basis 平台**，
    而覆盖值如果按"调用方传的原始平台"去查（这里是 None）⇒ 找不到
    ⇒ **人工覆盖被静默忽略** —— 运营设了覆盖，页面却还是显示成本线，
    看起来就像系统坏了。两处必须是**同一个平台**。
    """
    await pricing_seed()

    resp = await pg_async_client.patch(
        "/api/skus/9001/pricing-override",
        headers=pricing_auth_headers,
        json={"platform_code": "tiktok", "min_selling_price_override": 20.0},
    )
    assert resp.status_code == 200, resp.text

    # 不带 platform_code 查询 —— 走 basis 平台回落
    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["min_selling_price"] == pytest.approx(20.0, abs=0.01)
    assert row["min_selling_price_source"] == "manual_override"
    assert row["min_selling_price_is_override"] is True

    # 明确按平台查，结果必须与上面**完全一致**（不存在第二份口径）
    resp = await pg_async_client.get(
        "/api/skus", headers=pricing_auth_headers, params={"platform_code": "tiktok"}
    )
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["min_selling_price"] == pytest.approx(20.0, abs=0.01)
    assert row["min_selling_price_source"] == "manual_override"


@pytest.mark.asyncio
async def test_mart_age_lookup_works_when_table_exists_and_survives_when_not(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """mart 表存在时真能取到库龄；不存在时回落日常档，**且事务不被 abort**。

    这条同时守住三件事：
    1. 库龄查询语句在 asyncpg 下真的能执行并取到数
       （用 `= ANY(:keys)` 的话，类型推断失败会被 `except Exception` 静默吞掉，
        库龄永远回落日常档且**没有任何报错**）；
    2. `to_regclass` 短路分支生效（表不存在时不发出会失败的查询）；
    3. 外层事务仍然可用——后续语句不抛 `InFailedSQLTransactionError`。
    """
    await pricing_seed()

    # 1) 状态层存在且有一行：距上次进货 75 天 -> 命中 min_restock_days=60 的「滞销30天」档
    # ⚠️ 必须建 `mart.inventory_state`（新判据的真实来源，列：sku_key/stock_added_at/
    #    available_stock/inventory_value），**不是** `mart.inventory_age_current`：
    #    后者是旧库龄口径（age_days），且真实表里根本没有 days_since_restock 这一列。
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS mart"))
    await pg_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS mart.inventory_state ("
            " sku_key text, stock_added_at timestamp, available_stock numeric,"
            " inventory_value numeric)"
        )
    )
    await pg_session.execute(
        text(
            "INSERT INTO mart.inventory_state "
            "(sku_key, stock_added_at, available_stock, inventory_value) "
            "VALUES ('TEST-SKU-1', CURRENT_DATE - INTERVAL '75 days', 10, 300)"
        )
    )

    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["pricing_days_since_restock"] == 75
    assert row["pricing_tier_source"] == "restock_days"
    assert row["pricing_tier_label"] == "滞销30天"
    assert row["current_discount_rate"] == pytest.approx(0.15)

    # 2) mart 表没了：回落日常档，且事务仍然健康
    await pg_session.execute(text("DROP SCHEMA mart CASCADE"))

    resp = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json()["data"] if item["sku_id"] == 9001)
    assert row["pricing_tier_source"] == "fallback_no_restock_days"
    assert row["pricing_days_since_restock"] is None

    # 3) 再查一次：若事务在上一步被 abort，这里会 500
    again = await pg_async_client.get("/api/skus", headers=pricing_auth_headers)
    assert again.status_code == 200, again.text


def test_profit_candidates_and_estimate_guardrail_wired():

    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    service = Path("backend/services/product_pricing_service.py").read_text(
        encoding="utf-8"
    )
    assert "below_min_selling_price" in source
    assert "min_selling_price_below" in source
    # 这三个字段由纯函数服务产出（路由只做 ORM 适配 + 合并），
    # 所以要在 service 里断言，而不是在路由里
    for name in (
        "min_selling_price",
        "clearance_max_discount_rate",
        "current_discount_rate",
    ):
        assert name in service, name


@pytest.mark.asyncio
async def test_estimate_below_floor_is_rejected_but_draft_is_not(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """低于最低售价时 estimates 422 拦截，drafts 仍放行。"""
    await pricing_seed()

    # 候选接口需要 active 的 sales 平台 + active 仓库 + SKU，seed 已满足
    candidates = await pg_async_client.get(
        "/api/platform-sku-profit/candidates",
        headers=pricing_auth_headers,
        params={
            "platform_code": "tiktok",
            "warehouse_code": "MY-01",
            "transport_type": "sea",
        },
    )
    assert candidates.status_code == 200, candidates.text
    rows = candidates.json()["data"]
    assert rows, "seed 后应有候选行"
    row = rows[0]
    assert "min_selling_price" in row
    assert row["min_selling_price"] is not None
    # seed 的期望数值（批次 9 口径）：
    # 成本线 = (采购 10 + 头程 0.05 + 仓储 3.00 + 贴单 0.50 + 尾程 5) × 1.0625 ÷ 0.343
    #        = 19.709375 / 0.343 = 57.4617… ⇒ 57.46（> 纪律线 30*0.9 = 27.00）
    assert row["min_selling_price"] == pytest.approx(57.46, abs=0.01)
    assert row["min_selling_price_source"] == "cost_floor"
    # 库龄表在测试库不存在 -> 回落「日常」档
    assert row["pricing_tier_source"] == "fallback_no_restock_days"
    assert row["pricing_days_since_restock"] is None

    payload = {
        "sku_id": row["sku_id"],
        "platform_code": row["platform_code"],
        "warehouse_code": row["warehouse_code"],
        "transport_type": row["transport_type"],
        "expected_selling_price": 0.01,
    }
    estimate = await pg_async_client.post(
        "/api/platform-sku-profit/estimates", headers=pricing_auth_headers, json=payload
    )
    assert estimate.status_code == 422, estimate.text
    body = estimate.json()
    # ⚠️ 仓库统一错误信封是 {"success": false, "error": {...}, "message": ..., "timestamp": ...}
    # **没有顶层 `detail` 键**；结构化业务码在 `error.detail.code`。
    # （`backend/app/exception_handlers.py` 的 handle_http_exception 会把 HTTPException.detail
    #   拍平成字符串，所以必须走 APIException 路线才能保住 dict 结构。）
    assert body["success"] is False
    assert body["error"]["detail"]["code"] == "below_min_selling_price"
    # ⚠️ 批次 9 口径收口：护栏的底线现在**带仓**（与商品中心页面同口径）⇒
    # 分子 = (采购 10 + 头程 0.05 + 仓储 3.00 + 贴单 0.50 + 尾程 5) × 1.0625 = 19.709375
    # 分母 = 0.343 ⇒ 57.4617… ⇒ 57.46
    assert body["error"]["detail"]["min_selling_price"] == pytest.approx(
        57.46, abs=0.01
    )
    assert body["error"]["detail"]["expected_selling_price"] == pytest.approx(
        0.01, abs=0.01
    )

    draft = await pg_async_client.post(
        "/api/platform-sku-profit/drafts", headers=pricing_auth_headers, json=payload
    )
    assert draft.status_code == 201, draft.text


@pytest.mark.asyncio
async def test_estimate_above_floor_saves_successfully(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """高于底线的价格必须能存——证明护栏只拦「低于底线」，不是把整条保存链路堵死。

    这条同时是 **seed 完整性的探针**：如果 seed 缺物流规则 / 仓储规则 / 平台费率，
    这里会拿到 `cannot_save_profit_version` 而不是 201。

    ⚠️ 批次 2 P2：保存利润版本**必须**给一个广告费口径（目标 ROI 或显式的广告分成率）——
    「广告费不可算 ⇒ 利润空白」的利润版本没有意义，存下来只会误导事后复盘。

    ⚠️ 批次 4：尾程进利润后保本 ROI 从 2.19 抬到 3.66 ⇒ 目标 ROI 必须跟着抬，
    否则会被「低于保本线」拦下（这正是尾程该起的作用）。

    ⚠️ 批次 9：利润链**开始扣桶**（0.2727）⇒ 同样的售价下保本 ROI 又抬了一截
    （售价 35 时保本 ROI ≈ 33.33）⇒ 目标 ROI 4 已经够不着保本线。
    所以这里把**售价**抬到 60（仍高于底线 30.98），
    售价 60 时保本 ROI ≈ 3.78 < 目标 ROI 4 ⇒ 放行。
    """
    await pricing_seed()

    ok = await pg_async_client.post(
        "/api/platform-sku-profit/estimates",
        headers=pricing_auth_headers,
        json={
            "sku_id": 9001,
            "platform_code": "tiktok",
            "warehouse_code": "MY-01",
            "transport_type": "sea",
            "expected_selling_price": 60,
            "target_roi": 4,
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["estimate_ids"]


@pytest.mark.asyncio
async def test_estimate_without_ad_cost_input_is_rejected(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """没给目标 ROI 也没给广告分成率 ⇒ 广告费不可算 ⇒ 不许存利润版本（批次 2 P2）。

    老行为是把「没填」当成广告费 0 ⇒ 利润看着很美 ⇒ 存下来的版本会误导复盘。

    ⚠️ 批次 9：护栏的底线**带仓**了（57.46）⇒ 售价必须高于它，
    否则会先撞「低于最低售价」，压根走不到「广告费口径缺失」这条校验。
    """
    await pricing_seed()

    resp = await pg_async_client.post(
        "/api/platform-sku-profit/estimates",
        headers=pricing_auth_headers,
        json={
            "sku_id": 9001,
            "platform_code": "tiktok",
            "warehouse_code": "MY-01",
            "transport_type": "sea",
            "expected_selling_price": 60,
        },
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["detail"]["code"] == "cannot_save_profit_version"
    assert "完整预计利润口径" in body["error"]["detail"]["missing_fields"]


@pytest.mark.asyncio
async def test_guardrail_precedes_missing_fields_check(
    pg_async_client, pricing_auth_headers, pg_session, pricing_seed
):
    """缺物流/仓储规则 + 低于底线 -> 必须报 below_min_selling_price。

    ⚠️ 这是「护栏排在缺资料校验之前」的**唯一可观测断言**。
    用完整 seed 时 `_platform_profit_missing_fields` 恒返回 `[]`，
    护栏放前放后结果完全一样，测不出差别——所以必须用 `with_cost_rules=False` 的 seed。
    """
    await pricing_seed(with_cost_rules=False)

    estimate = await pg_async_client.post(
        "/api/platform-sku-profit/estimates",
        headers=pricing_auth_headers,
        json={
            "sku_id": 9001,
            "platform_code": "tiktok",
            "warehouse_code": "MY-01",
            "transport_type": "sea",
            "expected_selling_price": 0.01,
        },
    )
    assert estimate.status_code == 422, estimate.text
    body = estimate.json()
    # 不能是 cannot_save_profit_version（缺物流规则 / 缺仓储规则）
    assert body["error"]["detail"]["code"] == "below_min_selling_price"
    # ⚠️ 这条用的是 **with_cost_rules=False** 的种子：没有物流/仓储规则、没有尾程费率
    #    ⇒ 尾程与履约按件成本都**算不出来**（不进分子）⇒ 底线只剩采购成本：
    #    分子 10 × 1.0625 = 10.625 ÷ 分母 0.343 = 30.9778… ⇒ 30.98
    assert body["error"]["detail"]["min_selling_price"] == pytest.approx(
        30.98, abs=0.01
    )


# ---------------------------------------------------------------- 达人佣金计入利润


def test_creator_commission_is_deducted_from_profit():
    """达人佣金是真实现金流出，必须从利润里扣掉。"""
    from backend.services.product_profit_service import build_platform_profit_preview

    common = dict(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        purchase_cost=Decimal("10"),
        expected_logistics_cost=Decimal("5"),
        expected_storage_cost=Decimal("5"),
        expected_label_fee=Decimal("0"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.0737"),
        # 批次 9：桶（平台其他成本率）是利润链的**必填**成本项（缺它整条链算不出来）。
        # 本用例只测达人佣金 ⇒ 桶显式给 0，让被测口径（佣金扣减）不受桶影响。
        other_cost_rate=Decimal("0"),
        expected_ad_rate=Decimal("0"),
        return_rate=Decimal("0"),
        damage_rate=Decimal("0"),
        # 尾程配送费（批次 4）：本用例只测达人佣金，尾程按 0 传入（显式给 0 = 尾程免费），
        # 让被测口径（佣金扣减）不受尾程影响。
        delivery_cost=Decimal("0"),
    )
    without = build_platform_profit_preview(**common)
    with_commission = build_platform_profit_preview(
        **common, creator_commission_rate=Decimal("0.11")
    )
    # 不传 -> 按 0 计（既有调用方行为不变）
    assert without["expected"]["creator_commission"] == Decimal("0")
    # 收入 100 - 采购 10 - 物流 5 - 仓储 5 - 平台佣金 7.37 = 72.63
    assert without["expected"]["profit"] == Decimal("72.63")
    # 传 11% -> 收入 100 扣 11，利润同步降 11
    assert with_commission["expected"]["creator_commission"] == Decimal("11.00")
    assert with_commission["expected"]["profit"] == Decimal("61.63")
    assert with_commission["expected"]["creator_commission_rate"] == Decimal("0.11")


def test_creator_commission_none_does_not_block_profit():
    """未提供佣金口径时不能把利润变成 None。"""
    from backend.services.product_profit_service import build_platform_profit_preview

    result = build_platform_profit_preview(
        expected_selling_price=Decimal("50"),
        competitor_price=None,
        purchase_cost=Decimal("10"),
        expected_logistics_cost=Decimal("0"),
        expected_storage_cost=Decimal("0"),
        expected_label_fee=Decimal("0"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0"),
        # 批次 9：桶是必填项（见上一个用例的说明）⇒ 显式给 0。
        other_cost_rate=Decimal("0"),
        expected_ad_rate=Decimal("0"),
        return_rate=Decimal("0"),
        damage_rate=Decimal("0"),
        # 尾程配送费（批次 4）：本用例只测「佣金缺失不阻断利润」，尾程按 0 传入。
        delivery_cost=Decimal("0"),
    )
    assert result["expected"]["profit"] == Decimal("40.00")
    assert result["expected"]["creator_commission"] == Decimal("0")
