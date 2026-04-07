import importlib


def test_inventory_domain_router_exposes_opening_balance_routes():
    module = importlib.import_module("backend.routers.inventory_domain")
    paths = {route.path for route in module.router.routes}

    assert "/api/inventory/opening-balances" in paths


def test_opening_balance_create_request_accepts_required_fields():
    schemas = importlib.import_module("backend.schemas.inventory")

    payload = schemas.InventoryOpeningBalanceCreateRequest(
        period="2026-04",
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        opening_qty=12,
        opening_cost=5.5,
    )

    assert payload.platform_sku == "SKU1"
    assert payload.opening_value is None
