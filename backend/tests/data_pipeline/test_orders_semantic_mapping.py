from pathlib import Path


def test_orders_atomic_sql_exists_and_creates_semantic_view():
    sql_path = Path("sql/semantic/orders_atomic.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.fact_orders_atomic AS" in sql_text


def test_orders_atomic_sql_exposes_core_standard_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(encoding="utf-8")
    for field_name in (
        "platform_code",
        "shop_id",
        "order_id",
        "order_status",
        "sales_amount",
        "paid_amount",
        "profit",
        "product_quantity",
        "platform_total_cost_itemized",
        "currency_code",
        "data_hash",
        "ingest_timestamp",
    ):
        assert field_name in sql_text
