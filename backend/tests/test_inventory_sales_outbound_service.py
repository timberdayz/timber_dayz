from backend.services.inventory.sales_outbound_service import build_sale_ledger_entry


def test_build_sale_ledger_entry_sets_sale_quantities_and_order_link():
    entry = build_sale_ledger_entry(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        qty_before=20,
        avg_cost_before=5.0,
        qty_out=3,
        order_id="ORDER-001",
    )

    assert entry["movement_type"] == "sale"
    assert entry["qty_in"] == 0
    assert entry["qty_out"] == 3
    assert entry["qty_after"] == 17
    assert entry["link_order_id"] == "ORDER-001"
