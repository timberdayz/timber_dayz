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


def test_logistics_rule_distinguishes_sensitive_goods_without_cargo_class():
    from backend.services.product_logistics_service import match_logistics_rule

    rules = [
        {
            "logistics_provider": "Ocean",
            "destination": "MANILA",
            "transport_type": "sea",
            "is_sensitive": False,
            "freight_unit_rate": Decimal("850"),
            "effective_from": date(2026, 1, 1),
        },
        {
            "logistics_provider": "Ocean",
            "destination": "MANILA",
            "transport_type": "sea",
            "is_sensitive": True,
            "freight_unit_rate": Decimal("930"),
            "effective_from": date(2026, 1, 1),
        },
    ]

    selected = match_logistics_rule(
        rules,
        provider="Ocean",
        destination="MANILA",
        transport_type="sea",
        is_sensitive=True,
        as_of=date(2026, 9, 11),
    )

    assert selected["freight_unit_rate"] == Decimal("930")


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


def test_new_logistics_request_preserves_each_purchase_order_sku_quantity():
    from backend.schemas.product_center import LogisticsBillLineRequest

    request = LogisticsBillLineRequest(
        sku_ids=[1, 2],
        allocations=[
            {"sku_id": 1, "po_id": "PO-001", "shipped_qty": 10},
            {"sku_id": 2, "po_id": "PO-002", "shipped_qty": 20},
        ],
        billing_basis="volume",
        line_total_amount=1200,
    )

    assert [(item.sku_id, item.po_id, item.shipped_qty) for item in request.allocations] == [
        (1, "PO-001", 10),
        (2, "PO-002", 20),
    ]


def test_purchase_order_cost_supplement_request_tracks_manual_source():
    from backend.schemas.product_center import PurchaseOrderLineCostSupplementRequest

    request = PurchaseOrderLineCostSupplementRequest(unit_price=15.5)

    assert request.unit_price == 15.5
    assert request.purchase_cost_source == "manual"
