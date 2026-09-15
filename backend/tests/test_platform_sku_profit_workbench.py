from decimal import Decimal

from backend.services.product_profit_service import build_platform_profit_preview
from modules.core.db import DimErpSku, SkuOperatingProfile, SkuProfitEstimate
from sqlalchemy import inspect
from pathlib import Path


def test_workbench_models_store_reference_price_measurement_and_dual_basis():
    sku_columns = {column.name for column in inspect(DimErpSku).columns}
    profile_columns = {column.name for column in inspect(SkuOperatingProfile).columns}
    estimate_columns = {column.name for column in inspect(SkuProfitEstimate).columns}

    assert {"reference_selling_price", "selling_price_currency", "selling_price_source", "selling_price_confirmed_at"} <= sku_columns
    assert {"competitor_price", "expected_selling_price", "seller_coupon_amount", "expected_ad_rate"} <= profile_columns
    assert {"calculation_basis", "expected_ad_cost", "actual_logistics_cost", "actual_storage_cost", "actual_recost_profit"} <= estimate_columns


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

    assert result["expected"]["ad_cost"] == Decimal("9.00")
    assert result["expected"]["profit"] == Decimal("27.50")
    assert result["expected"]["competitor_price_difference"] == Decimal("20.00")


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
        expected_selling_price=100, competitor_price=None, seller_coupon_amount=0,
        purchase_cost=30, expected_logistics_cost=8, expected_storage_cost=2,
        actual_logistics_cost=None, actual_storage_cost=None, platform_fee_rate=0,
        expected_ad_rate=0, return_rate=0, damage_rate=0,
    )

    assert result["actual_recost"]["completeness"] == "estimated"
    assert result["variance"]["total"] is None


def test_missing_reference_cost_does_not_become_zero_profit_input():
    result = build_platform_profit_preview(
        expected_selling_price=100, competitor_price=None, seller_coupon_amount=0,
        purchase_cost=30, expected_logistics_cost=None, expected_storage_cost=2,
        actual_logistics_cost=None, actual_storage_cost=None, platform_fee_rate=0,
        expected_ad_rate=0, return_rate=0, damage_rate=0,
    )

    assert result["expected"]["logistics_cost"] is None
    assert result["expected"]["profit"] is None
    assert result["actual_recost"]["completeness"] == "incomplete"


def test_workbench_exposes_candidate_preview_and_immutable_estimate_endpoints():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert '"/api/platform-sku-profit/candidates"' in source
    assert '"/api/platform-sku-profit/preview"' in source
    assert '"/api/platform-sku-profit/estimates"' in source
    assert "list_platform_sku_profit_candidates" in source


def test_workbench_candidates_do_not_default_transport_or_include_non_sales_platforms():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert "platform.platform_role != \"sales\"" in source
    assert 'profile.transport_type if profile else "sea"' not in source
