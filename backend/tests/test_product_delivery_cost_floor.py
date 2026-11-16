"""尾程配送费进成本底线（批次 4，2026-11-16）守护测试。

这一批修的是「尾程这笔钱会不会被算两遍 / 会不会被漏掉」：

- **漏掉**：尾程是每卖一件必付的成本。老口径里 `other_cost_rate` 是从实测净利率反推的
  **残差桶**（生产库实测：TikTok 的「总费用」里恰好含 `实际运费`，Shopee 的
  `卖家支付运费` 直接从结算里扣），所以桶里**已经含了按收入摊的那份尾程**。
  尾程按 SKU 重量单件计价后，只加分子不剔残差 ⇒ **同一笔尾程扣两次**（底线偏高）。
- **算两遍**：反过来，只剔残差不加分子 ⇒ 尾程被白送（底线偏低，更危险）。

所以本文件把「**成对生效**」钉死：

    分子 = 采购成本 + 尾程配送费
    分母 = 1 − 平台其他成本率 + 尾程占收入比 − 达人 − 货损 − 退货 − 目标利润率

    尾程与尾程占收入比**必须同时有值**才生效；缺任何一半 ⇒ 尾程**不进底线**
    （宁可不算，也不重复扣），并在缺失原因里点名缺了什么。

另有一条硬规则：**尾程算不出来 ⇒ 利润算不出来**（不是按 0 计）。
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

OTHER_COST_RATE = Decimal("0.2727")
CREATOR_RATE = Decimal("0.0606")
RETURN_LOSS_RATE = Decimal("0.0467")
DAMAGE_RATE = Decimal("0.0158")
TARGET_MARGIN = Decimal("0.25")

#: 批次 4 的拆分基准（尾程占收入比）。
DELIVERY_RATE = Decimal("0.10")
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
        "other_cost_rate": OTHER_COST_RATE,
        "spu_bound": True,
        "spu_return_loss_rate": RETURN_LOSS_RATE,
        "spu_damage_rate": DAMAGE_RATE,
        "policy": _policy(),
        "deepest_policy": _policy(),
        "min_selling_price_override": None,
        "days_since_restock": None,
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
        "expected_ad_rate": Decimal("0.10"),
        "target_roi": None,
        "return_rate": Decimal("0.03"),
        "damage_rate": Decimal("0.02"),
    }
    payload.update(overrides)
    return build_platform_profit_preview(**payload)


# ---------------------------------------------------------------------------
# 1. 成对生效：底线公式
# ---------------------------------------------------------------------------


def test_cost_floor_with_delivery_uses_paired_formula():
    """尾程 + 拆分基准同时有值 ⇒ 分子加尾程、分母加回尾程占比。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
        delivery_cost=DELIVERY_COST,
        delivery_cost_rate=DELIVERY_RATE,
    )
    denominator = (
        Decimal("1")
        - OTHER_COST_RATE
        + DELIVERY_RATE
        - CREATOR_RATE
        - RETURN_LOSS_RATE
        - DAMAGE_RATE
        - TARGET_MARGIN
    )
    assert denominator == Decimal("0.4542")
    assert floor == (Decimal("15") / denominator).quantize(Decimal("0.01"))


def test_cost_floor_without_delivery_keeps_legacy_caliber():
    """没有尾程 ⇒ 底线就是老口径（残差桶原样用）。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
    )
    assert floor == Decimal("28.23")


def test_cost_floor_without_delivery_rate_does_not_add_delivery_cost():
    """**只给尾程、不给拆分基准 ⇒ 尾程不进底线**。

    这是本批最关键的一条：分子加了尾程而分母没把残差里的那份剔掉 ⇒
    同一笔尾程扣两次 ⇒ 底线被抬高（看起来更保守，实际是错的）。
    """
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
        delivery_cost=DELIVERY_COST,
        delivery_cost_rate=None,
    )
    assert floor == Decimal("28.23")


def test_cost_floor_without_delivery_cost_does_not_remove_residual_share():
    """**只给拆分基准、不给尾程 ⇒ 尾程也不进底线**。

    反向同样危险：分母里把尾程剔了、分子却没加 ⇒ 尾程被白送（底线偏低）。
    """
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=TARGET_MARGIN,
        delivery_cost=None,
        delivery_cost_rate=DELIVERY_RATE,
    )
    assert floor == Decimal("28.23")


# ---------------------------------------------------------------------------
# 2. SKU 定价：成对生效的标记与缺失原因
# ---------------------------------------------------------------------------


def test_sku_pricing_marks_delivery_in_cost_floor_when_paired():
    out = _pricing(delivery_cost=DELIVERY_COST, delivery_cost_rate=DELIVERY_RATE)
    assert out["delivery_cost_in_cost_floor"] is True
    assert out["cost_floor_delivery_cost"] == pytest.approx(5.0)
    assert out["cost_floor_delivery_cost_rate"] == pytest.approx(0.10)
    assert out["min_selling_price_missing_reasons"] == []
    # 底线确实比老口径高（尾程进了分子）
    assert out["min_selling_price"] > Decimal("28.23")


def test_sku_pricing_reports_missing_delivery_cost():
    out = _pricing()
    assert out["delivery_cost_in_cost_floor"] is False
    assert "missing_delivery_cost" in out["min_selling_price_missing_reasons"]


def test_sku_pricing_reports_missing_delivery_cost_rate_split():
    out = _pricing(delivery_cost=DELIVERY_COST, delivery_cost_rate=None)
    assert out["delivery_cost_in_cost_floor"] is False
    assert (
        "missing_delivery_cost_rate_split" in out["min_selling_price_missing_reasons"]
    )
    # 没配拆分基准 ⇒ 底线仍是老口径（不重复扣）
    assert out["min_selling_price"] == pytest.approx(28.23, abs=0.01)


# ---------------------------------------------------------------------------
# 3. 利润链：尾程是必付成本
# ---------------------------------------------------------------------------


def test_delivery_cost_is_deducted_from_pre_ad_profit():
    """尾程必须从广告前利润里扣掉，否则利润被系统性高估。"""
    without = _preview(delivery_cost=Decimal("0"))
    with_delivery = _preview(delivery_cost=Decimal("12"))
    assert without["expected"]["pre_ad_profit"] - with_delivery["expected"][
        "pre_ad_profit"
    ] == Decimal("12.00")
    assert with_delivery["expected"]["delivery_cost"] == Decimal("12.00")


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
    """单 SKU 试算链路（preview_platform_sku_profit）必须取尾程。"""
    assert "find_delivery_cost" in FINANCE_SOURCE
    assert "delivery_cost=delivery_result.amount" in FINANCE_SOURCE


def test_platform_split_field_exists_in_orm():
    """平台级拆分基准必须是 ORM 的一等字段（不是散落在别处的常量）。"""
    from modules.core.db import DimPlatform

    assert "delivery_cost_rate" in DimPlatform.__table__.columns
