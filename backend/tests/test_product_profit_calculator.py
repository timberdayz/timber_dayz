from decimal import Decimal

import pytest

from backend.services.product_profit_service import (
    BillTotalMismatchError,
    build_baseline_profit,
    build_logistics_sku_line,
    validate_bill_total,
)
from backend.schemas.product_center import LogisticsBillLinesReplaceRequest, SkuCreateRequest


def test_logistics_sku_line_uses_sku_defaults_and_calculates_three_unit_costs():
    result = build_logistics_sku_line(
        shipped_qty=10,
        unit_weight_kg=Decimal("0.2"),
        unit_volume_cbm=Decimal("0.0015"),
        actual_total_weight_kg=None,
        actual_total_volume_cbm=None,
        headhaul_cost=Decimal("100"),
        handling_cost=Decimal("20"),
        last_mile_cost=Decimal("30"),
    )
    assert result["calculated_total_weight_kg"] == Decimal("2.000")
    assert result["calculated_total_volume_cbm"] == Decimal("0.015000")
    assert result["line_total_amount"] == Decimal("150.00")
    assert result["unit_headhaul_cost"] == Decimal("10.000000")
    assert result["unit_handling_cost"] == Decimal("2.000000")
    assert result["unit_last_mile_cost"] == Decimal("3.000000")


def test_logistics_sku_line_keeps_actual_measurements_when_supplied():
    result = build_logistics_sku_line(
        shipped_qty=5,
        unit_weight_kg=Decimal("0.2"),
        unit_volume_cbm=Decimal("0.001"),
        actual_total_weight_kg=Decimal("1.25"),
        actual_total_volume_cbm=Decimal("0.006"),
        headhaul_cost=Decimal("5"),
        handling_cost=Decimal("0"),
        last_mile_cost=Decimal("0"),
    )
    assert result["actual_total_weight_kg"] == Decimal("1.25")
    assert result["actual_total_volume_cbm"] == Decimal("0.006")


def test_bill_confirmation_requires_sku_line_costs_to_match_header_total():
    validate_bill_total(Decimal("150"), [Decimal("100"), Decimal("50")])
    with pytest.raises(BillTotalMismatchError):
        validate_bill_total(Decimal("150"), [Decimal("149.99")])


def test_baseline_profit_prefers_confirmed_logistics_cost_over_assumption():
    result = build_baseline_profit(
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
    assert result["logistics_cost"] == Decimal("15.00")
    assert result["logistics_cost_source"] == "confirmed_logistics_bill"
    assert result["purchase_cost_source"] == "sku_default_purchase_cost"
    assert result["estimated_contribution_profit"] == Decimal("34.70")


def test_sku_create_accepts_default_purchase_cost_fields():
    request = SkuCreateRequest(
        sku_key="SKU-NEW",
        default_purchase_cost=12.5,
        purchase_cost_currency="CNY",
        purchase_cost_source="factory_quote",
        purchase_cost_confidence="medium",
    )
    assert request.default_purchase_cost == 12.5
    assert request.purchase_cost_source == "factory_quote"


def test_logistics_bill_lines_reject_duplicate_skus():
    try:
        LogisticsBillLinesReplaceRequest(
            lines=[
                {"sku_id": 1, "shipped_qty": 1},
                {"sku_id": 1, "shipped_qty": 2},
            ]
        )
    except ValueError:
        return
    raise AssertionError("duplicate SKU lines must be rejected")
