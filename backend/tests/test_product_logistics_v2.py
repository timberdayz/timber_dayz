from datetime import date
from decimal import Decimal

import pytest


def test_logistics_rule_defaults_to_volume_and_matches_specific_scope():
    from backend.services.product_logistics_service import match_logistics_rule

    rules = [
        {"provider": "Ocean", "destination": None, "transport_type": "sea", "cargo_class": None, "billing_basis": "volume", "freight_unit_rate": Decimal("700"), "effective_from": date(2026, 1, 1)},
        {"provider": "Ocean", "destination": "MANILA", "transport_type": "sea", "cargo_class": "sensitive", "billing_basis": "volume", "freight_unit_rate": Decimal("930"), "effective_from": date(2026, 1, 1)},
    ]
    selected = match_logistics_rule(rules, provider="Ocean", destination="MANILA", transport_type="sea", cargo_class="sensitive", as_of=date(2026, 9, 11))
    assert selected["freight_unit_rate"] == Decimal("930")
    assert selected["billing_basis"] == "volume"


def test_allocate_bill_line_supports_mixed_basis_and_reconciles_amount():
    from backend.services.product_logistics_service import allocate_bill_line

    allocations = allocate_bill_line(
        line_amount=Decimal("1200"),
        basis="volume",
        items=[
            {"sku_id": 1, "quantity": Decimal("10"), "volume_cbm": Decimal("1")},
            {"sku_id": 2, "quantity": Decimal("20"), "volume_cbm": Decimal("3")},
        ],
    )
    assert sum(item["allocated_amount"] for item in allocations) == Decimal("1200.00")
    assert allocations[0]["allocated_amount"] == Decimal("300.00")
    assert allocations[1]["allocated_amount"] == Decimal("900.00")


def test_bill_batch_models_support_many_purchase_orders_and_billing_basis():
    from modules.core.db import LogisticsBillLine, LogisticsBillPurchaseOrder

    assert LogisticsBillPurchaseOrder.__table__.c.po_id.nullable is False
    assert LogisticsBillLine.__table__.c.billing_basis.default.arg == "volume"
    assert "bill_id" in LogisticsBillPurchaseOrder.__table__.c


def test_new_logistics_requests_allow_fixed_basis_and_multiple_skus():
    from backend.schemas.product_center import LogisticsBillLineRequest, LogisticsBillLinesReplaceRequest

    request = LogisticsBillLinesReplaceRequest(lines=[LogisticsBillLineRequest(sku_ids=[1, 2], billing_basis="fixed", line_total_amount=100)])
    assert request.lines[0].billing_basis == "fixed"
    assert request.lines[0].sku_ids == [1, 2]
