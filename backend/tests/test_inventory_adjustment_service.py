import importlib


def test_build_adjustment_ledger_entry_moves_negative_delta_to_qty_out():
    module = importlib.import_module("backend.services.inventory.adjustment_service")

    entry = module.build_adjustment_ledger_entry(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        qty_before=20,
        avg_cost_before=5.0,
        qty_delta=-3,
        unit_cost=5.0,
        adjustment_id="ADJ-001",
    )

    assert entry["movement_type"] == "adjustment"
    assert entry["qty_in"] == 0
    assert entry["qty_out"] == 3
    assert entry["qty_after"] == 17


def test_inventory_domain_router_exposes_adjustment_routes():
    module = importlib.import_module("backend.routers.inventory_domain")
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory/adjustments" in paths
    assert "/api/inventory/adjustments/{adjustment_id}/post" in paths
