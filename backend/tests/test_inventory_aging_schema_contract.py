from datetime import date

import backend.schemas as schemas
from modules.core.db import Base, OpeningBalance


def test_inventory_aging_tables_are_registered():
    assert "finance.inventory_layers" in Base.metadata.tables
    assert "finance.inventory_layer_consumptions" in Base.metadata.tables


def test_opening_balance_tracks_received_date_or_age():
    columns = OpeningBalance.__table__.columns.keys()
    assert "received_date" in columns or "opening_age_days" in columns


def test_inventory_aging_contracts_are_exported():
    assert hasattr(schemas, "InventoryAgingRowResponse")
    assert hasattr(schemas, "InventoryAgingBucketResponse")
    assert hasattr(schemas, "InventoryAgingHistoryPointResponse")


def test_inventory_aging_row_response_accepts_snapshot_fields():
    row = schemas.InventoryAgingRowResponse(
        snapshot_date=date(2025, 12, 8),
        platform_code="miaoshou",
        sku_key="SKU-A",
        platform_sku="SKU-A",
        product_name="Product A",
        current_qty=12,
        age_anchor_date=date(2025, 10, 8),
        age_days=61,
        reset_reason="continued",
        inventory_value=120.5,
        bucket="61-90",
    )

    assert row.platform_sku == "SKU-A"
    assert row.current_qty == 12
    assert row.bucket == "61-90"


def test_inventory_aging_summary_response_tracks_total_sku_count():
    summary = schemas.InventoryAgingSummaryResponse(
        total_sku_count=3,
        total_quantity=18,
        total_value=420.0,
    )

    assert summary.total_sku_count == 3
    assert summary.total_quantity == 18
