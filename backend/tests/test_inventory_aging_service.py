from datetime import date

from backend.routers.inventory_domain import router
from backend.schemas.inventory import InventoryAgingRowResponse
from backend.services.inventory.aging_service import InventoryAgingService


class _FakeMappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeAsyncSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return _FakeMappingResult(self.rows)


async def test_inventory_aging_service_reads_snapshot_rows_from_api_module():
    db = _FakeAsyncSession(
        [
            {
                "snapshot_date": date(2025, 12, 8),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "product_name": "Product A",
                "current_qty": 2,
                "previous_qty": 2,
                "qty_delta": 0,
                "age_anchor_date": date(2025, 10, 8),
                "age_days": 61,
                "bucket": "61-90",
                "reset_reason": "continued",
                "inventory_value": 100.5,
            }
        ]
    )
    service = InventoryAgingService(db)

    rows = await service.list_aging_rows(platform="miaoshou", platform_sku="SKU-A")

    assert len(rows) == 1
    assert rows[0].sku_key == "SKU-A"
    assert rows[0].age_days == 61
    assert rows[0].reset_reason == "continued"
    assert rows[0].inventory_value == 100.5
    assert "api.inventory_age_list_module" in db.calls[0][0]
    assert db.calls[0][1]["platform"] == "miaoshou"
    assert db.calls[0][1]["platform_sku"] == "SKU-A"


async def test_inventory_aging_service_builds_bucket_summary_from_snapshot_rows(
    monkeypatch,
):
    service = InventoryAgingService(None)

    async def _fake_list_aging_rows(**kwargs):
        return [
            InventoryAgingRowResponse(
                snapshot_date=date(2025, 12, 8),
                platform_code="miaoshou",
                sku_key="SKU-A",
                platform_sku="SKU-A",
                product_name="Product A",
                current_qty=2,
                age_anchor_date=date(2025, 11, 26),
                age_days=12,
                bucket="0-30",
                reset_reason="continued",
                inventory_value=20.5,
            ),
            InventoryAgingRowResponse(
                snapshot_date=date(2025, 12, 8),
                platform_code="miaoshou",
                sku_key="SKU-B",
                platform_sku="SKU-B",
                product_name="Product B",
                current_qty=3,
                age_anchor_date=date(2025, 9, 24),
                age_days=75,
                bucket="61-90",
                reset_reason="continued",
                inventory_value=50.0,
            ),
        ]

    monkeypatch.setattr(service, "list_aging_rows", _fake_list_aging_rows)

    summary = await service.get_aging_summary(platform="miaoshou")

    assert summary.total_sku_count == 2
    assert summary.total_quantity == 5
    assert summary.total_value == 70.5
    buckets = {bucket.bucket: bucket for bucket in summary.buckets}
    assert buckets["0-30"].quantity == 2
    assert buckets["0-30"].inventory_value == 20.5
    assert buckets["61-90"].sku_count == 1


async def test_inventory_aging_service_reads_history_rows():
    db = _FakeAsyncSession(
        [
            {
                "snapshot_date": date(2025, 12, 1),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "product_name": "Product A",
                "current_qty": 2,
                "previous_qty": None,
                "qty_delta": 2,
                "age_anchor_date": date(2025, 12, 1),
                "age_days": 0,
                "bucket": "0-30",
                "reset_reason": "first_positive",
                "inventory_value": 20.5,
            },
            {
                "snapshot_date": date(2026, 2, 4),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "product_name": "Product A",
                "current_qty": 1,
                "previous_qty": 2,
                "qty_delta": -1,
                "age_anchor_date": date(2025, 12, 1),
                "age_days": 65,
                "bucket": "61-90",
                "reset_reason": "continued",
                "inventory_value": 10.0,
            },
        ]
    )
    service = InventoryAgingService(db)

    history_rows = await service.list_aging_history(platform="miaoshou", platform_sku="SKU-A")

    assert len(history_rows) == 2
    assert history_rows[1].age_days == 65
    assert history_rows[1].reset_reason == "continued"
    assert "mart.inventory_age_history" in db.calls[0][0]


def test_inventory_domain_router_exposes_aging_routes():
    paths = {route.path for route in router.routes}
    assert "/api/inventory/aging" in paths
    assert "/api/inventory/aging/buckets" in paths
    assert "/api/inventory/aging/history" in paths
