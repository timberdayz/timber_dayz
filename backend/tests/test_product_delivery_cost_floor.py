"""尾程配送费进成本底线（批次 9 B 路线，2026-11-19）守护测试。

这一批改的是「尾程这笔钱进不进底线、扣几遍」：

- **旧机制（批次 4）**：尾程成对生效 —— 分子加尾程 ⇔ 分母加回「尾程占收入比」，
  两者必须同时有值才生效，否则同一笔尾程要么被扣两次、要么被白送。
  批次 9 拍板 **B 路线**：桶是黑箱，里面那笔运费**拆不出来** ⇒ 对冲永远无解
  ⇒ 「尾程占收入比」字段与「成对生效」机制**一并退役**，尾程**直接进分子**。
- **新口径**：

      分子 = (采购成本 + 头程 + 仓储 + 贴单 + 尾程) × (1 + SPU退货率 + SPU货损率)
      分母 = 1 − 平台佣金率 − 平台其他成本率(桶) − 达人佣金率 − 目标利润率

所以本文件把「**尾程直接进分子**」钉死：

- 给了尾程 ⇒ 尾程进分子（底线变高），**不需要**任何拆分基准；
- 没给尾程 ⇒ 尾程不进分子，但必须报 `missing_delivery_cost`；
- 利润链里尾程仍是**必付成本**（算不出来 ⇒ 利润算不出来，不是按 0 计）。

另有一条硬规则没变：**尾程算不出来 ⇒ 利润算不出来**（不是按 0 计）。
尾程不免费，按 0 计等于凭空多出一笔利润。
"""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_sku_pricing,
)
from backend.services.product_profit_service import build_platform_profit_preview

ROUTER_SOURCE = Path("backend/domains/business/routers/product_center.py").read_text(
    encoding="utf-8"
)
FINANCE_SOURCE = Path("backend/services/product_finance_service.py").read_text(
    encoding="utf-8"
)

PLATFORM_FEE_RATE = Decimal("0.0737")
OTHER_COST_RATE = Decimal("0.2727")
CREATOR_RATE = Decimal("0.0606")
RETURN_LOSS_RATE = Decimal("0.0467")
DAMAGE_RATE = Decimal("0.0158")
TARGET_MARGIN = Decimal("0.25")

#: 分母 = 1 − 0.0737 − 0.2727 − 0.0606 − 0.25 = 0.343
DENOMINATOR = Decimal("0.343")
#: 分子（无尾程）= 10 × (1 + 0.0467 + 0.0158) = 10.625 ⇒ 底线 30.9778… ⇒ 30.98
COST_FLOOR = Decimal("30.98")
#: 分子（有尾程 5）= 15 × 1.0625 = 15.9375 ⇒ 底线 46.4650… ⇒ 46.47
COST_FLOOR_WITH_DELIVERY = Decimal("46.47")

#: 这个 SKU 的单件尾程（按重量档算出来的）。
DELIVERY_COST = Decimal("5")


def _policy():
    return {
        "min_restock_days": 0,
        "tier_label": "日常",
        "discount_rate": Decimal("0.10"),
        "target_margin_rate": TARGET_MARGIN,
    }


def _pricing(**overrides):
    payload = {
        "purchase_cost": Decimal("10"),
        "reference_selling_price": Decimal("30"),
        "creator_commission_rate": None,
        "platform_creator_commission_rate": CREATOR_RATE,
        "platform_fee_rate": PLATFORM_FEE_RATE,
        "other_cost_rate": OTHER_COST_RATE,
        "spu_bound": True,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "policy": _policy(),
        "deepest_policy": _policy(),
        "min_selling_price_override": None,
        "days_since_restock": None,
        "delivery_cost": None,
        "free_shipping": True,
    }
    payload.update(overrides)
    return compute_sku_pricing(**payload)


def _preview(**overrides):
    payload = {
        "expected_selling_price": Decimal("100"),
        "competitor_price": None,
        "purchase_cost": Decimal("30"),
        "expected_logistics_cost": Decimal("8"),
        "expected_storage_cost": Decimal("2"),
        "expected_label_fee": None,
        "actual_logistics_cost": None,
        "actual_storage_cost": None,
        "platform_fee_rate": Decimal("0.10"),
        # 批次 9：桶是利润链的必填项（缺它整条链算不出来）
        "other_cost_rate": Decimal("0"),
        "expected_ad_rate": Decimal("0.10"),
        "target_roi": None,
        "return_rate": Decimal("0.03"),
        "damage_rate": Decimal("0.02"),
    }
    payload.update(overrides)
    return build_platform_profit_preview(**payload)


# ---------------------------------------------------------------------------
# 1. 尾程直接进分子（不再「成对生效」）
# ---------------------------------------------------------------------------


def test_cost_floor_with_delivery_adds_it_to_the_numerator():
    """给了尾程 ⇒ 尾程进分子（**不需要**任何拆分基准）。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
        delivery_cost=DELIVERY_COST,
    )
    assert floor == COST_FLOOR_WITH_DELIVERY
    # 分子 = (采购 10 + 尾程 5) × 1.0625 = 15.9375；分母 = 0.343
    assert floor == (
        (Decimal("10") + DELIVERY_COST)
        * (Decimal("1") + RETURN_LOSS_RATE + DAMAGE_RATE)
        / DENOMINATOR
    ).quantize(Decimal("0.01"))


def test_cost_floor_without_delivery_keeps_the_purchase_only_caliber():
    """没有尾程 ⇒ 底线就是「只有采购成本」的口径。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        platform_fee_rate=PLATFORM_FEE_RATE,
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
    )
    assert floor == COST_FLOOR


def test_delivery_cost_rate_parameter_is_retired():
    """「尾程占收入比」入参**已退役** —— 传进去必须报错，不能被静默忽略。

    ⚠️ 静默忽略最危险：调用方以为尾程配了 ⇒ 底线算得偏低 ⇒ 定价偏低 ⇒ 亏本。
    """
    with pytest.raises(TypeError):
        compute_cost_floor(
            purchase_cost=Decimal("10"),
            platform_fee_rate=PLATFORM_FEE_RATE,
            other_cost_rate=OTHER_COST_RATE,
            creator_commission_rate=CREATOR_RATE,
            spu_return_loss_rate=RETURN_LOSS_RATE,
            spu_damage_rate=DAMAGE_RATE,
            target_margin_rate=TARGET_MARGIN,
            delivery_cost=DELIVERY_COST,
            delivery_cost_rate=Decimal("0.10"),
        )


# ---------------------------------------------------------------------------
# 2. SKU 定价：尾程的标记与缺失原因
# ---------------------------------------------------------------------------


def test_sku_pricing_marks_delivery_in_cost_floor_when_present():
    out = _pricing(delivery_cost=DELIVERY_COST)
    assert out["delivery_cost_in_cost_floor"] is True
    assert out["cost_floor_delivery_cost"] == pytest.approx(5.0)
    assert out["min_selling_price_missing_reasons"] == []
    # 底线确实比「没有尾程」高（尾程进了分子）
    assert out["min_selling_price"] > COST_FLOOR
    assert out["min_selling_price"] == pytest.approx(46.47, abs=0.01)


def test_sku_pricing_reports_missing_delivery_cost():
    out = _pricing()
    assert out["delivery_cost_in_cost_floor"] is False
    assert "missing_delivery_cost" in out["min_selling_price_missing_reasons"]
    # 尾程算不出来 ⇒ 底线退回「只有采购成本」的口径（30.98）
    assert out["min_selling_price"] == pytest.approx(30.98, abs=0.01)


def test_retired_delivery_rate_split_reason_is_gone():
    """「成对生效」那条缺料原因已退役 ⇒ 不得再出现。"""
    out = _pricing(delivery_cost=DELIVERY_COST)
    assert (
        "missing_delivery_cost_rate_split"
        not in out["min_selling_price_missing_reasons"]
    )
    # 返回值里那个退役字段也不该再有
    assert "cost_floor_delivery_cost_rate" not in out


# ---------------------------------------------------------------------------
# 3. 利润链：尾程是必付成本
# ---------------------------------------------------------------------------


def test_delivery_cost_is_deducted_from_pre_ad_profit():
    """尾程必须从广告前利润里扣掉，否则利润被系统性高估。

    ⚠️ 批次 9：尾程进了**按件成本合计** ⇒ 件损率（退货 + 货损 = 5%）会把它**再乘一次**
    ⇒ 尾程 12 元带来的总扣减 = 12.00（尾程本身）+ 0.60（件损折算 12 × 5%）= **12.60**。
    （旧口径按收入比例扣退货/货损 ⇒ 尾程不影响那两项 ⇒ 差额只有 12.00。）
    """
    without = _preview(delivery_cost=Decimal("0"))
    with_delivery = _preview(delivery_cost=Decimal("12"))
    assert without["expected"]["pre_ad_profit"] - with_delivery["expected"][
        "pre_ad_profit"
    ] == Decimal("12.60")
    assert with_delivery["expected"]["delivery_cost"] == Decimal("12.00")
    # 尾程本身那 12 元必须原样出现在成本项里
    assert with_delivery["expected"]["pre_ad_profit"] == without["expected"][
        "pre_ad_profit"
    ] - Decimal("12.00") - Decimal("0.60")


def test_delivery_cost_missing_makes_profit_not_computable():
    """尾程算不出来 ⇒ 利润算不出来（**不是按 0 计**）。

    尾程不免费：按 0 计等于凭空多出一笔利润，利润会偏乐观。
    """
    result = _preview(delivery_cost=None)
    assert result["expected"]["profit"] is None
    assert (
        "missing_delivery_cost" in result["expected"]["delivery_cost_missing_reasons"]
    )


# ---------------------------------------------------------------------------
# 4. 接线守护（口径漂移的防线）
# ---------------------------------------------------------------------------


def test_router_passes_delivery_cost_into_profit_preview():
    """候选列表的利润试算必须把尾程传进去。"""
    assert "delivery_cost=delivery_result.amount" in ROUTER_SOURCE


def test_router_passes_delivery_cost_into_cost_floor():
    """候选列表的底线必须把尾程传进去。"""
    assert "delivery_cost=delivery_result.amount" in ROUTER_SOURCE
    assert "delivery_cost_in_cost_floor" in ROUTER_SOURCE


def test_finance_service_fetches_delivery_cost():
    """单 SKU 试算链路（preview_platform_sku_profit）必须取尾程。

    ⚠️ 批次 6 起尾程要先过**包邮开关**：不包邮 ⇒ 买家付运费 ⇒ 商家不承担尾程
    ⇒ 进利润链的是 ``applied_delivery_cost``（不包邮时按 0），
    不是 ``delivery_result.amount`` 本身。
    """
    assert "find_delivery_cost" in FINANCE_SOURCE
    assert "applied_delivery_cost" in FINANCE_SOURCE
    assert "delivery_cost=applied_delivery_cost" in FINANCE_SOURCE


def test_retired_platform_split_field_is_gone_from_the_orm():
    """平台级「尾程占收入比」字段已退役 ⇒ ORM 里**不得再有**这一列。

    ⚠️ 留着这一列 = 界面还能填一个"看起来在生效、实际没人读"的输入框
    （批次 4 那个「填了不生效」的病，尾程占收入比重演一遍）。
    """
    from modules.core.db import DimPlatform

    assert "delivery_cost_rate" not in DimPlatform.__table__.columns
