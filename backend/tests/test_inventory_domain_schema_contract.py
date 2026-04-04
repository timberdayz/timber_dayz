import backend.schemas as schemas
from modules.core.db import Base


def test_inventory_adjustment_tables_are_registered():
    assert "finance.inventory_adjustment_headers" in Base.metadata.tables
    assert "finance.inventory_adjustment_lines" in Base.metadata.tables


def test_inventory_adjustment_request_requires_lines():
    payload_cls = getattr(schemas, "InventoryAdjustmentCreateRequest", None)

    assert payload_cls is not None

    payload = payload_cls(
        adjustment_date="2026-04-03",
        reason="stock_count",
        lines=[
            {
                "platform_code": "shopee",
                "shop_id": "s1",
                "platform_sku": "SKU1",
                "qty_delta": -2,
            }
        ],
    )

    assert payload.lines[0].platform_sku == "SKU1"
