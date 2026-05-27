from pathlib import Path


def test_analytics_atomic_sql_exists_and_creates_semantic_view():
    sql_path = Path("sql/semantic/analytics_atomic.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.fact_analytics_atomic AS" in sql_text


def test_analytics_atomic_sql_exposes_core_standard_fields():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    for field_name in (
        "platform_code",
        "shop_id",
        "metric_date",
        "visitor_count",
        "page_views",
        "impressions",
        "clicks",
        "click_rate",
        "conversion_rate",
        "order_count",
        "sku_order_count",
        "gmv",
        "total_transaction_amount",
        "product_visitor_count",
        "bounce_rate",
        "currency_code",
        "data_hash",
        "ingest_timestamp",
    ):
        assert field_name in sql_text


def test_analytics_sql_supports_shopee_and_tiktok_page_view_aliases():
    daily_sql = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    monthly_sql = Path("sql/semantic/analytics_monthly_atomic.sql").read_text(encoding="utf-8")

    page_view_shopee = "".join(chr(c) for c in [39029, 38754, 27983, 35272, 25968])
    page_view_tiktok = "".join(chr(c) for c in [39029, 38754, 27983, 35272, 27425, 25968])
    for sql_text in (daily_sql, monthly_sql):
        assert page_view_shopee in sql_text
        assert page_view_tiktok in sql_text


def test_analytics_sql_supports_tiktok_store_page_visit_as_unique_visitors():
    daily_sql = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")
    monthly_sql = Path("sql/semantic/analytics_monthly_atomic.sql").read_text(encoding="utf-8")

    tiktok_store_page_visit = "".join(chr(c) for c in [24215, 38138, 39029, 38754, 35775, 38382, 37327])
    for sql_text in (daily_sql, monthly_sql):
        assert tiktok_store_page_visit in sql_text
