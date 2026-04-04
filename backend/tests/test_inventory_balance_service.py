import importlib
import importlib.util


def test_compute_balance_summary_uses_opening_plus_movements():
    module_name = "backend.services.inventory.balance_service"

    assert importlib.util.find_spec(module_name) is not None

    module = importlib.import_module(module_name)
    summary = module.compute_balance_summary(
        opening_qty=10,
        ledger_rows=[
            {"qty_in": 5, "qty_out": 0},
            {"qty_in": 0, "qty_out": 3},
        ],
    )

    assert summary["current_qty"] == 12


def test_inventory_domain_router_exposes_balance_and_ledger_routes():
    module_name = "backend.routers.inventory_domain"

    assert importlib.util.find_spec(module_name) is not None

    module = importlib.import_module(module_name)
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory/balances" in paths
    assert "/api/inventory/ledger" in paths
