import importlib


def test_compute_snapshot_delta_compares_internal_and_external_stock():
    module = importlib.import_module("backend.services.inventory.reconciliation_service")

    result = module.compute_snapshot_delta(internal_qty=12, external_qty=9)

    assert result["delta_qty"] == 3
    assert result["status"] == "mismatch"


def test_classify_inventory_alert_marks_zero_stock_as_out_of_stock():
    module = importlib.import_module("backend.services.inventory.reconciliation_service")

    alert = module.classify_inventory_alert(current_qty=0, safety_stock=5)

    assert alert == "out_of_stock"


def test_inventory_domain_router_exposes_alert_and_reconciliation_routes():
    module = importlib.import_module("backend.routers.inventory_domain")
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory/alerts" in paths
    assert "/api/inventory/reconciliation" in paths
