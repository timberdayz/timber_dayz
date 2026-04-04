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


def test_inventory_aging_row_response_accepts_required_fields():
    row = schemas.InventoryAgingRowResponse(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        remaining_qty=12,
        oldest_age_days=90,
        youngest_age_days=10,
        weighted_avg_age_days=42.5,
    )

    assert row.platform_sku == "SKU1"
    assert row.remaining_qty == 12
