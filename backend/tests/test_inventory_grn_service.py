import importlib
import importlib.util


def test_build_receipt_ledger_entry_sets_receipt_quantities():
    module_name = "backend.services.inventory.grn_service"

    assert importlib.util.find_spec(module_name) is not None

    module = importlib.import_module(module_name)
    entry = module.build_receipt_ledger_entry(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        qty_before=10,
        avg_cost_before=5.0,
        qty_received=4,
        unit_cost=6.0,
        grn_id="GRN-001",
    )

    assert entry["movement_type"] == "receipt"
    assert entry["qty_in"] == 4
    assert entry["qty_after"] == 14


def test_inventory_domain_router_exposes_grn_routes():
    module = importlib.import_module("backend.routers.inventory_domain")
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory/grns" in paths
    assert "/api/inventory/grns/{grn_id}/post" in paths
