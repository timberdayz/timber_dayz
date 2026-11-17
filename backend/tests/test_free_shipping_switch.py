"""包邮开关（批次 6，2026-11-17）守护测试。

业务前提
--------
跨境电商**不是默认包邮**，而是**选择性包邮** —— 同一个平台上，
有的 listing 包邮、有的不包邮。

⇒ 「包不包邮」是 **SKU × 平台** 的经营选择（粒度与底线、人工覆盖一致），
与费率表（平台 × 仓 × 重量段的**承运商报价**）**无关**：
费率表回答「这一段运费多少钱」，包邮开关回答「这笔钱谁付」。

三条口径
--------
1. **包邮** ⇒ 商家承担尾程 ⇒ 尾程进成本底线分子 + 平台尾程占比进分母
   （成对生效）+ 利润链扣掉这笔尾程。
2. **不包邮** ⇒ 买家付运费 ⇒ 商家不承担 ⇒ 尾程**完全不适用**：
   不进底线、**不报**「缺尾程费率」、利润链尾程按 **0** 计（**不是**算不出来）。
3. **默认关闭**（未设置 = 不包邮）：默认包邮 ⇒ 每个 SKU 的底线都被塞进一笔
   并不存在的尾程 ⇒ 底线系统性偏高 ⇒ 定价过高 ⇒ 丢单。
"""

from pathlib import Path

import pytest

from backend.schemas.product_center import (
    SkuFreeShippingRequest,
    SkuFreeShippingResponse,
)
from backend.services.product_pricing_query_service import resolve_free_shipping
from backend.services.product_pricing_service import compute_sku_pricing
from modules.core.db import SkuPlatformPricing

MIGRATION_PATH = Path("current_migrations/versions/20261237_free_shipping_flag.py")
ROUTER_PATH = Path("backend/domains/business/routers/product_center.py")
FRONTEND_PATH = Path("frontend/src/domains/business/views/ProductCenter.vue")
FRONTEND_API_PATH = Path("frontend/src/api/productCenter.js")


# ---------------------------------------------------------------------------
# 1 · 表与迁移
# ---------------------------------------------------------------------------


def test_free_shipping_column_is_nullable_boolean():
    """NULL = 未设置 ⇒ 按不包邮；不能是 NOT NULL（否则整表都要有值）。"""
    columns = {column.name: column for column in SkuPlatformPricing.__table__.columns}
    assert "free_shipping" in columns
    assert columns["free_shipping"].nullable is True


def test_free_shipping_migration_chains_after_weight_tiers():
    assert MIGRATION_PATH.exists()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision = "current_schema_20261237_free_shipping_flag"' in source
    assert 'down_revision = "current_schema_20261236_weight_tiers"' in source
    assert "free_shipping" in source


# ---------------------------------------------------------------------------
# 2 · 读路径：默认关闭
# ---------------------------------------------------------------------------


def test_free_shipping_defaults_to_false():
    assert resolve_free_shipping({}, 1, "shopee") is False


def test_free_shipping_reads_the_sku_platform_row():
    class _Row:
        free_shipping = True

    context = {"overrides": {(1, "shopee"): _Row()}}
    assert resolve_free_shipping(context, 1, "shopee") is True
    # 平台不匹配 ⇒ 没设置 ⇒ 不包邮
    assert resolve_free_shipping(context, 1, "tiktok") is False
    # SKU 不匹配 ⇒ 没设置 ⇒ 不包邮
    assert resolve_free_shipping(context, 2, "shopee") is False


def test_explicit_false_is_not_treated_as_unset():
    class _Row:
        free_shipping = False

    context = {"overrides": {(1, "shopee"): _Row()}}
    assert resolve_free_shipping(context, 1, "shopee") is False


# ---------------------------------------------------------------------------
# 3 · 计算链：不包邮 ⇒ 尾程不适用
# ---------------------------------------------------------------------------


def _pricing(**overrides):
    payload = {
        "purchase_cost": 10.0,
        "reference_selling_price": 30.0,
        "creator_commission_rate": 0.1,
        "platform_creator_commission_rate": 0.1,
        "other_cost_rate": 0.4,
        "spu_bound": True,
        "spu_return_loss_rate": 0.03,
        "spu_damage_rate": 0.01,
        "policy": {
            "target_margin_rate": 0.25,
            "discount_rate": 0.1,
            "tier_label": "日常",
            "min_restock_days": 0,
        },
        "deepest_policy": {
            "target_margin_rate": 0.25,
            "discount_rate": 0.1,
            "tier_label": "日常",
            "min_restock_days": 0,
        },
        "min_selling_price_override": None,
        "delivery_cost": 22.31,
        "delivery_cost_rate": 0.1124,
    }
    payload.update(overrides)
    return compute_sku_pricing(**payload)


def test_free_shipping_delivery_enters_the_cost_floor():
    result = _pricing(free_shipping=True)
    assert result["delivery_cost_in_cost_floor"] is True
    assert result["cost_floor_delivery_cost"] == 22.31
    assert result["free_shipping"] is True


def test_not_free_shipping_keeps_delivery_out_of_the_cost_floor():
    """不包邮 ⇒ 商家不承担 ⇒ 尾程不进底线（分子分母都不动）。"""
    result = _pricing(free_shipping=False)
    assert result["delivery_cost_in_cost_floor"] is False
    assert result["cost_floor_delivery_cost"] is None
    assert result["cost_floor_delivery_cost_rate"] is None


def test_not_free_shipping_does_not_report_missing_delivery_rate():
    """⚠️ 不包邮的 SKU 压根不需要尾程费率 ⇒ 报缺是噪声，会把真缺料淹掉。"""
    result = _pricing(free_shipping=False, delivery_cost=None)
    assert "missing_delivery_cost" not in result["min_selling_price_missing_reasons"]


def test_free_shipping_with_missing_rate_still_reports_it():
    """包邮 ⇒ 尾程必需 ⇒ 算不出来必须报出来。"""
    result = _pricing(free_shipping=True, delivery_cost=None)
    assert "missing_delivery_cost" in result["min_selling_price_missing_reasons"]


# ---------------------------------------------------------------------------
# 4 · 端点与契约
# ---------------------------------------------------------------------------


def test_free_shipping_endpoint_exists():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert '"/api/skus/{sku_id}/free-shipping"' in source
    assert "set_free_shipping" in source


def test_free_shipping_contract():
    request = SkuFreeShippingRequest(platform_code="shopee", free_shipping=True)
    assert request.free_shipping is True
    response = SkuFreeShippingResponse(
        sku_id=1, platform_code="shopee", free_shipping=False
    )
    assert response.free_shipping is False


# ---------------------------------------------------------------------------
# 5 · 前端
# ---------------------------------------------------------------------------


def test_frontend_has_free_shipping_switch():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "onFreeShippingChange" in source
    assert "row.free_shipping" in source
    assert 'label="包邮"' in source


def test_frontend_api_calls_free_shipping_endpoint():
    source = FRONTEND_API_PATH.read_text(encoding="utf-8")
    assert "setSkuFreeShipping" in source
    assert "/free-shipping" in source


def test_frontend_tells_operator_that_not_free_shipping_excludes_delivery():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "买家付运费" in source
    assert "不包邮" in source


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
