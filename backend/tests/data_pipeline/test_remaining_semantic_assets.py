from pathlib import Path


def _assert_semantic_sql(path_str: str, view_name: str, required_fields: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert f"CREATE OR REPLACE VIEW semantic.{view_name} AS" in sql_text
    for field_name in required_fields:
        assert field_name in sql_text


def test_products_atomic_sql_asset():
    _assert_semantic_sql(
        "sql/semantic/products_atomic.sql",
        "fact_products_atomic",
        (
            "platform_code",
            "shop_id",
            "product_id",
            "product_name",
            "platform_sku",
            "sales_amount",
            "sales_volume",
            "conversion_rate",
            "review_count",
            "currency_code",
            "data_hash",
        ),
    )


def test_inventory_snapshot_sql_asset():
    _assert_semantic_sql(
        "sql/semantic/inventory_snapshot.sql",
        "fact_inventory_snapshot",
        (
            "platform_code",
            "shop_id",
            "product_id",
            "platform_sku",
            "warehouse_name",
            "available_stock",
            "on_hand_stock",
            "inventory_value",
            "currency_code",
            "data_hash",
        ),
    )


def test_services_atomic_sql_asset():
    _assert_semantic_sql(
        "sql/semantic/services_atomic.sql",
        "fact_services_atomic",
        (
            "platform_code",
            "shop_id",
            "sub_domain",
            "service_date",
            "visitor_count",
            "chat_count",
            "order_count",
            "gmv",
            "satisfaction",
            "currency_code",
            "data_hash",
        ),
    )
