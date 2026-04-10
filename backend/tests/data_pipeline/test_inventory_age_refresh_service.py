from datetime import date

from backend.services.data_pipeline.inventory_age_refresh_service import (
    InventoryAgeRefreshService,
    compute_age_transition,
    replay_snapshot_rows,
)


def test_stock_increase_resets_age_to_zero():
    result = compute_age_transition(
        previous_qty=1,
        current_qty=3,
        snapshot_date=date(2026, 4, 9),
        previous_anchor_date=date(2026, 4, 1),
    )

    assert result["age_days"] == 0
    assert result["reset_reason"] == "stock_increase"
    assert result["age_anchor_date"] == date(2026, 4, 9)


def test_zero_stock_drops_current_state():
    result = compute_age_transition(
        previous_qty=2,
        current_qty=0,
        snapshot_date=date(2026, 4, 9),
        previous_anchor_date=date(2026, 4, 1),
    )

    assert result["is_active"] is False
    assert result["age_days"] is None
    assert result["reset_reason"] == "zero_stock"


def test_continued_stock_keeps_previous_anchor_date():
    result = compute_age_transition(
        previous_qty=5,
        current_qty=2,
        snapshot_date=date(2026, 4, 9),
        previous_anchor_date=date(2026, 4, 1),
    )

    assert result["is_active"] is True
    assert result["age_days"] == 8
    assert result["reset_reason"] == "continued"
    assert result["age_anchor_date"] == date(2026, 4, 1)


def test_inventory_age_refresh_service_builds_dependency_ordered_targets():
    service = InventoryAgeRefreshService(db=None)

    targets = service.build_refresh_targets()

    assert targets.index("semantic.fact_inventory_snapshot") < targets.index(
        "mart.inventory_snapshot_history"
    )
    assert targets.index("mart.inventory_snapshot_company_daily") < targets.index(
        "mart.inventory_age_history"
    )
    assert targets.index("mart.inventory_age_current") < targets.index(
        "api.inventory_age_list_module"
    )


def test_replay_snapshot_rows_builds_history_and_current_state():
    history_rows, current_row = replay_snapshot_rows(
        [
            {
                "snapshot_date": date(2025, 12, 1),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "sku_id": None,
                "product_id": None,
                "product_name": "Product A",
                "available_qty": 2,
                "on_hand_qty": 2,
                "inventory_value": 20.0,
                "warehouse_count": 1,
                "last_ingest_timestamp": "2026-04-10T00:00:00Z",
            },
            {
                "snapshot_date": date(2026, 2, 4),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "sku_id": None,
                "product_id": None,
                "product_name": "Product A",
                "available_qty": 1,
                "on_hand_qty": 1,
                "inventory_value": 10.0,
                "warehouse_count": 1,
                "last_ingest_timestamp": "2026-04-10T00:00:00Z",
            },
            {
                "snapshot_date": date(2026, 2, 10),
                "platform_code": "miaoshou",
                "sku_key": "SKU-A",
                "platform_sku": "SKU-A",
                "product_sku": "SKU-A",
                "sku_id": None,
                "product_id": None,
                "product_name": "Product A",
                "available_qty": 3,
                "on_hand_qty": 3,
                "inventory_value": 30.0,
                "warehouse_count": 1,
                "last_ingest_timestamp": "2026-04-10T00:00:00Z",
            },
        ]
    )

    assert len(history_rows) == 3
    assert history_rows[0]["reset_reason"] == "first_positive"
    assert history_rows[1]["age_days"] == 65
    assert history_rows[1]["reset_reason"] == "continued"
    assert history_rows[2]["age_days"] == 0
    assert history_rows[2]["reset_reason"] == "stock_increase"
    assert current_row["snapshot_date"] == date(2026, 2, 10)
    assert current_row["current_qty"] == 3
    assert current_row["bucket"] == "0-30"


async def test_inventory_age_refresh_service_detects_changed_keys_from_watermark():
    class _FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _FakeMappingResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, statement, params=None):
            self.calls += 1
            if self.calls == 1:
                return _FakeScalarResult("2026-04-10T00:00:00Z")
            return _FakeMappingResult(
                [
                    {
                        "platform_code": "miaoshou",
                        "sku_key": "SKU-A",
                        "earliest_snapshot_date": date(2025, 12, 1),
                    }
                ]
            )

    service = InventoryAgeRefreshService(db=_FakeSession())

    changed_keys = await service.get_changed_keys()

    assert changed_keys == [
        {
            "platform_code": "miaoshou",
            "sku_key": "SKU-A",
            "earliest_snapshot_date": date(2025, 12, 1),
        }
    ]
