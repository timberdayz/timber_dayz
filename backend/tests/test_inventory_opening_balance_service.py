import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import ProgrammingError


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


@pytest.mark.asyncio
async def test_list_opening_balances_falls_back_when_received_date_column_is_missing():
    service_module = importlib.import_module("backend.services.inventory.opening_balance_service")

    class _MappingsResult:
        def all(self):
            return [
                {
                    "balance_id": 1,
                    "period": "2026-04",
                    "platform_code": "shopee",
                    "shop_id": "shop-1",
                    "platform_sku": "SKU-1",
                    "received_date": None,
                    "opening_age_days": 12,
                    "opening_qty": 8,
                    "opening_cost": 3.5,
                    "opening_value": 28.0,
                    "source": "manual",
                    "migration_batch_id": None,
                    "created_by": "system",
                    "created_at": "2026-04-01T00:00:00Z",
                }
            ]

    class _FallbackResult:
        def mappings(self):
            return _MappingsResult()

    missing_column_error = ProgrammingError(
        "SELECT * FROM finance.opening_balances",
        {},
        Exception("column opening_balances.received_date does not exist"),
    )

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[missing_column_error, _FallbackResult()])
    )

    service = service_module.InventoryOpeningBalanceService(db)
    records = await service.list_opening_balances()

    assert len(records) == 1
    assert records[0].platform_sku == "SKU-1"
    assert records[0].received_date is None
