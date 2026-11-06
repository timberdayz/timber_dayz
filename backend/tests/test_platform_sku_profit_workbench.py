from decimal import Decimal

from backend.services.product_profit_service import build_platform_profit_preview
from modules.core.db import DimErpSku, SkuOperatingProfile, SkuProfitEstimate
from sqlalchemy import inspect
from pathlib import Path


def test_workbench_models_store_reference_price_measurement_and_dual_basis():
    sku_columns = {column.name for column in inspect(DimErpSku).columns}
    profile_columns = {column.name for column in inspect(SkuOperatingProfile).columns}
    estimate_columns = {column.name for column in inspect(SkuProfitEstimate).columns}

    assert {
        "reference_selling_price",
        "selling_price_currency",
        "selling_price_source",
        "selling_price_confirmed_at",
    } <= sku_columns
    assert {
        "competitor_price",
        "expected_selling_price",
        "seller_coupon_amount",
        "expected_ad_rate",
    } <= profile_columns
    assert {
        "calculation_basis",
        "expected_ad_cost",
        "actual_logistics_cost",
        "actual_storage_cost",
        "actual_recost_profit",
    } <= estimate_columns


def test_expected_profit_uses_ad_rate_and_ignores_competitor_price():
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=Decimal("80"),
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

    # expected_ad_rate 的分母是**广告前利润**，不是收入（与 ERP docstring / 命名层契约 §3.6 一致）
    #   revenue   = 100 - 10 = 90
    #   pre_ad    = 90 - (30 采购 + 8 物流 + 2 仓储 + 0 贴单 + 9 平台费 + 0 达人佣金 + 2.70 退货 + 1.80 货损) = 36.50
    #   ad_cost   = 36.50 × 0.10 = 3.65
    #   profit    = 36.50 - 3.65 = 32.85
    assert result["expected"]["ad_cost"] == Decimal("3.65")
    assert result["expected"]["profit"] == Decimal("32.85")
    assert result["expected"]["competitor_price_difference"] == Decimal("20.00")


def test_label_fee_absent_is_treated_as_zero_not_as_missing_input():
    """贴单费是收货仓仓储规则上的**可选**每件费用：规则没配 = 0，不是"缺输入"。

    缺输入（物流 / 仓储）要挡住整条利润链（见 test_missing_reference_cost_does_not_become_zero_profit_input）；
    贴单费属于可选成本，缺失不得让整条利润算不出来 —— 口径与达人佣金率（None 按 0 计）一致。
    """
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("10"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("8"),
        expected_storage_cost=Decimal("2"),
        expected_label_fee=None,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.10"),
        expected_ad_rate=Decimal("0.10"),
        return_rate=Decimal("0.03"),
        damage_rate=Decimal("0.02"),
    )

    assert result["expected"]["profit"] is not None
    assert result["expected"]["profit"] == Decimal("32.85")
    assert result["actual_recost"]["completeness"] == "estimated"
    # 原始值保持 None（前端可据此显示"贴单费未配置"），并显式标出"按 0 计"这个假设
    assert result["expected"]["label_fee"] is None
    assert result["expected"]["label_fee_source"] == "assumed_zero"


def test_label_fee_configured_is_deducted_from_pre_ad_profit():
    """仓库规则里配了贴单费就必须扣 —— 不能因为"可选"而漏扣。"""
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("10"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("8"),
        expected_storage_cost=Decimal("2"),
        expected_label_fee=Decimal("2"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.10"),
        expected_ad_rate=Decimal("0.10"),
        return_rate=Decimal("0.03"),
        damage_rate=Decimal("0.02"),
    )

    # pre_ad = 36.50 - 2 = 34.50 ; ad = 3.45 ; profit = 31.05
    assert result["expected"]["label_fee"] == Decimal("2.00")
    assert result["expected"]["label_fee_source"] == "warehouse_rule"
    assert result["expected"]["profit"] == Decimal("31.05")


def test_actual_recost_falls_back_to_expected_storage_and_is_mixed():
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("10"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("8"),
        expected_storage_cost=Decimal("2"),
        actual_logistics_cost=Decimal("9"),
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0.10"),
        expected_ad_rate=Decimal("0.10"),
        return_rate=Decimal("0.03"),
        damage_rate=Decimal("0.02"),
    )

    assert result["actual_recost"]["logistics_cost"] == Decimal("9.00")
    assert result["actual_recost"]["storage_cost"] == Decimal("2.00")
    assert result["actual_recost"]["storage_cost_source"] == "expected_fallback"
    assert result["actual_recost"]["completeness"] == "mixed"
    assert result["variance"]["storage"] is None
    assert result["variance"]["total"] == Decimal("1.00")


def test_recost_without_any_actual_cost_has_no_cost_variance():
    result = build_platform_profit_preview(
        expected_selling_price=100,
        competitor_price=None,
        seller_coupon_amount=0,
        purchase_cost=30,
        expected_logistics_cost=8,
        expected_storage_cost=2,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=0,
        expected_ad_rate=0,
        return_rate=0,
        damage_rate=0,
    )

    assert result["actual_recost"]["completeness"] == "estimated"
    assert result["variance"]["total"] is None


def test_missing_reference_cost_does_not_become_zero_profit_input():
    result = build_platform_profit_preview(
        expected_selling_price=100,
        competitor_price=None,
        seller_coupon_amount=0,
        purchase_cost=30,
        expected_logistics_cost=None,
        expected_storage_cost=2,
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=0,
        expected_ad_rate=0,
        return_rate=0,
        damage_rate=0,
    )

    assert result["expected"]["logistics_cost"] is None
    assert result["expected"]["profit"] is None
    assert result["actual_recost"]["completeness"] == "incomplete"


def test_workbench_exposes_candidate_preview_and_immutable_estimate_endpoints():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )

    assert '"/api/platform-sku-profit/candidates"' in source
    assert '"/api/platform-sku-profit/preview"' in source
    assert '"/api/platform-sku-profit/estimates"' in source
    assert "list_platform_sku_profit_candidates" in source


def test_workbench_candidates_do_not_default_transport_or_include_non_sales_platforms():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )

    assert 'platform.platform_role != "sales"' in source
    assert 'profile.transport_type if profile else "sea"' not in source


def test_preview_exposes_pre_ad_profit_and_roi_metrics():
    """ROI 的分母是广告前利润，必须从利润预览里直接暴露出来。

    以前 pre_ad_profit 只是 `_ad_cost_and_profit` 的中间变量，算完就被丢掉 ——
    ROI 只能在外层把成本重算一遍，口径必然漂移。
    """
    result = build_platform_profit_preview(
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

    expected = result["expected"]
    # revenue = 90；pre_ad = 90 − (30+8+2+0+9+0+2.70+1.80) = 36.50
    assert expected["net_revenue"] == Decimal("90")
    assert expected["pre_ad_profit"] == Decimal("36.50")
    assert expected["break_even_roi"] == Decimal("90") / Decimal("36.50")
    assert expected["suggested_roi"] == expected["break_even_roi"] * Decimal("1.20")
    assert expected["suggested_roi_clamped"] is not None
    assert expected["roi_missing_reasons"] == []
    assert expected["roi_anomalies"] == []
    # 实际成本口径那一段也要有自己的一份
    assert result["actual_recost"]["pre_ad_profit"] == Decimal("36.50")
    assert result["actual_recost"]["break_even_roi"] == expected["break_even_roi"]


def test_roi_is_not_computed_when_a_reference_cost_is_missing():
    """成本不全守卫：成本缺一项 → pre_ad_profit 算不出来 → ROI 全部 None。

    缺输入宁可不算不可乐观：成本不全时保本 ROI 偏松，运营照着投广告就是亏。
    """
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("0"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=None,
        expected_storage_cost=Decimal("2"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0"),
        expected_ad_rate=Decimal("0"),
        return_rate=Decimal("0"),
        damage_rate=Decimal("0"),
    )

    expected = result["expected"]
    assert expected["pre_ad_profit"] is None
    assert expected["break_even_roi"] is None
    assert expected["suggested_roi"] is None
    assert expected["suggested_roi_clamped"] is None
    assert expected["equivalent_ad_cost_per_order"] is None
    assert expected["roi_missing_reasons"] == ["non_positive_cost_denominator"]


def test_platform_roi_config_is_passed_into_the_preview():
    """平台级 ROI 配置（安全边际 / 可填上限）必须传进利润预览，否则封顶值永远是默认值。"""
    result = build_platform_profit_preview(
        expected_selling_price=Decimal("100"),
        competitor_price=None,
        seller_coupon_amount=Decimal("0"),
        purchase_cost=Decimal("30"),
        expected_logistics_cost=Decimal("8"),
        expected_storage_cost=Decimal("2"),
        actual_logistics_cost=None,
        actual_storage_cost=None,
        platform_fee_rate=Decimal("0"),
        expected_ad_rate=Decimal("0"),
        return_rate=Decimal("0"),
        damage_rate=Decimal("0"),
        roi_safety_margin=Decimal("0.50"),
        target_roi_ceiling=Decimal("2"),
    )

    expected = result["expected"]
    # 安全边际 50% → 建议 ROI = 保本ROI × 1.5
    assert expected["suggested_roi"] == expected["break_even_roi"] * Decimal("1.50")
    # 上限 2 → 被截断
    assert expected["suggested_roi_clamped"] == Decimal("2")
    assert expected["suggestion_note"] == "above_platform_ceiling"
