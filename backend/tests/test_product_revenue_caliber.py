"""商家实收口径守卫：商家实收 = 测算售价（优惠券概念从商品中心链路移除）。

背景（2026-11-16 口径归一）：
运营在商品中心填的「测算售价」就是**折后到手价**。老口径把它当"标价"，
再扣一次卖家优惠券当商家实收 ⇒ 收入被少算 ⇒ ROI 偏乐观、平台佣金少扣。
同时老口径的「最低售价」底线里根本没扣券（``compute_cost_floor`` 无券项），
于是「最低售价」承诺的和「利润试算」算的不是同一个东西。

本文件是这条口径的**守护测试**：口径一旦被改回去（有人再加回优惠券扣减、
或把优惠券列塞回 API 契约 / 前端表格），这里必须立刻变红。
"""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    PlatformSkuProfitCandidateResponse,
    PlatformSkuProfitPreviewRequest,
    ProfitPreviewRequest,
    SkuOperatingProfitRequest,
    SkuOperatingProfileCreateRequest,
    SkuOperatingProfileUpdateRequest,
)
from backend.services.product_profit_service import (
    build_baseline_profit,
    build_platform_profit_preview,
)


def _preview(**overrides):
    """一份成本齐全的最小预览输入（口径：商家实收 = 测算售价）。"""
    payload = {
        "expected_selling_price": Decimal("100"),
        "competitor_price": None,
        "purchase_cost": Decimal("30"),
        "expected_logistics_cost": Decimal("8"),
        "expected_storage_cost": Decimal("2"),
        "actual_logistics_cost": None,
        "actual_storage_cost": None,
        "platform_fee_rate": Decimal("0.10"),
        "expected_ad_rate": Decimal("0.10"),
        "return_rate": Decimal("0.03"),
        "damage_rate": Decimal("0.02"),
        # 尾程配送费（批次 4）：本文件只守护「商家实收」口径，尾程按 0 传入
        # （显式给 0 = 尾程免费，避免它把利润链算成不可算、遮住被测口径）。
        "delivery_cost": Decimal("0"),
    }
    payload.update(overrides)
    return build_platform_profit_preview(**payload)


# ---------------------------------------------------------------------------
# 1. 计算口径
# ---------------------------------------------------------------------------


def test_platform_profit_preview_revenue_equals_measured_selling_price():
    """商家实收 = 测算售价，平台佣金等按比例成本都按它算。"""
    result = _preview()

    assert result["expected"]["net_revenue"] == Decimal("100.00")
    # 平台佣金 = 商家实收 × 平台费率 = 100 × 10% = 10
    assert result["expected"]["platform_fee"] == Decimal("10.00")
    # 退货损失 = 100 × 3% = 3；货损 = 100 × 2% = 2
    assert result["expected"]["return_loss"] == Decimal("3.00")
    assert result["expected"]["damage_loss"] == Decimal("2.00")
    # 广告前利润 = 100 − (30 + 8 + 2 + 0 贴单 + 10 平台佣金 + 0 达人佣金 + 3 + 2) = 45
    assert result["expected"]["pre_ad_profit"] == Decimal("45.00")


def test_platform_profit_preview_has_no_coupon_parameter():
    """签名里不得再有优惠券入口 —— 留一个参数就等于留一个"再扣一次"的口子。"""
    with pytest.raises(TypeError):
        build_platform_profit_preview(
            expected_selling_price=Decimal("100"),
            competitor_price=None,
            seller_coupon_amount=Decimal("10"),
            purchase_cost=Decimal("30"),
            expected_logistics_cost=Decimal("8"),
            expected_storage_cost=Decimal("2"),
            actual_logistics_cost=None,
            actual_storage_cost=None,
            platform_fee_rate=Decimal("0.10"),
            expected_ad_rate=Decimal("0.10"),
            return_rate=Decimal("0.03"),
            damage_rate=Decimal("0.02"),
        )


def test_baseline_profit_revenue_equals_selling_price():
    """老链路（经营档案试算）也必须同一口径，否则两条链算出来的利润对不上。"""
    result = build_baseline_profit(
        selling_price=Decimal("100"),
        default_purchase_cost=Decimal("20"),
        confirmed_logistics_cost=Decimal("15"),
        assumption_logistics_cost=Decimal("30"),
        storage_cost=Decimal("5"),
        platform_fee_rate=Decimal("0.10"),
        return_rate=Decimal("0.05"),
        damage_rate=Decimal("0.02"),
    )
    assert result["net_revenue"] == Decimal("100.00")
    # 100 − (20 + 15 + 5 + 10 平台费 + 5 退货 + 2 货损) = 43
    assert result["estimated_contribution_profit"] == Decimal("43.00")


def test_baseline_profit_has_no_coupon_parameter():
    with pytest.raises(TypeError):
        build_baseline_profit(
            selling_price=Decimal("100"),
            coupon_amount=Decimal("10"),
            default_purchase_cost=Decimal("20"),
            confirmed_logistics_cost=Decimal("15"),
            assumption_logistics_cost=Decimal("30"),
            storage_cost=Decimal("5"),
            platform_fee_rate=Decimal("0.10"),
            return_rate=Decimal("0.05"),
            damage_rate=Decimal("0.02"),
        )


# ---------------------------------------------------------------------------
# 2. API 契约
# ---------------------------------------------------------------------------


def test_preview_request_rejects_coupon_field():
    """测算页请求模型是 ``extra="forbid"`` —— 带上优惠券直接 422，不静默忽略。"""
    with pytest.raises(ValidationError):
        PlatformSkuProfitPreviewRequest(
            sku_id=1,
            platform_code="tiktok",
            warehouse_code="MY-01",
            transport_type="sea",
            seller_coupon_amount=10,
        )


def test_candidate_response_drops_coupon_field():
    assert "seller_coupon_amount" not in PlatformSkuProfitCandidateResponse.model_fields


def test_profile_requests_drop_coupon_fields():
    assert "default_coupon_amount" not in SkuOperatingProfileCreateRequest.model_fields
    assert "default_coupon_amount" not in SkuOperatingProfileUpdateRequest.model_fields


def test_legacy_profit_requests_drop_coupon_fields():
    assert "coupon_amount" not in ProfitPreviewRequest.model_fields
    assert "coupon_amount" not in SkuOperatingProfitRequest.model_fields


# ---------------------------------------------------------------------------
# 3. 链路与前端不得残留
# ---------------------------------------------------------------------------


def test_backend_product_center_chain_has_no_coupon_plumbing():
    """商品中心后端链路不得再出现优惠券字段（列名 / 入参 / 落库）。"""
    targets = [
        "backend/services/product_profit_service.py",
        "backend/services/product_finance_service.py",
        "backend/services/product_target_roi_backfill_service.py",
        "backend/schemas/product_center.py",
        "backend/domains/business/routers/product_center.py",
    ]
    for target in targets:
        source = Path(target).read_text(encoding="utf-8")
        assert "seller_coupon_amount" not in source, target
        assert "default_coupon_amount" not in source, target


def test_frontend_measurement_tab_has_no_coupon_column():
    """测算页不得再有优惠券列 / 优惠券预填 / 优惠券提交。"""
    source = Path("frontend/src/domains/business/views/ProductCenter.vue").read_text(
        encoding="utf-8"
    )
    assert "seller_coupon_amount" not in source
    assert "优惠券" not in source


def test_feishu_projection_column_is_merchant_receipt():
    """飞书投影的列名从「优惠券」改成「商家实收」，值取测算售价。"""
    source = Path("backend/services/feishu_projection_service.py").read_text(
        encoding="utf-8"
    )
    assert "商家实收" in source
    assert "优惠券" not in source
