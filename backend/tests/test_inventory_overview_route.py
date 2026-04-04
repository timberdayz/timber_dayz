import importlib


def test_inventory_overview_router_exposes_summary_and_product_routes():
    module = importlib.import_module("backend.routers.inventory_overview")
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory-overview/summary" in paths
    assert "/api/inventory-overview/products" in paths
