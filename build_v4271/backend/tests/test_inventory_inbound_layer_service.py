from datetime import date

from backend.services.inventory.inbound_layer_service import build_layer_record


def test_build_layer_record_uses_received_date_and_original_qty():
    layer = build_layer_record(
        source_type="grn",
        source_id="GRN-001",
        source_line_id="1",
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        warehouse="main",
        received_date=date(2026, 4, 4),
        qty=10,
        unit_cost=5.0,
        created_by="tester",
    )

    assert layer["original_qty"] == 10
    assert layer["remaining_qty"] == 10
    assert layer["received_date"] == date(2026, 4, 4)
