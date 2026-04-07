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
        "gmv",
        "bounce_rate",
        "currency_code",
        "data_hash",
        "ingest_timestamp",
    ):
        assert field_name in sql_text
