from pathlib import Path


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> str:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text
    return sql_text


def test_shop_hour_traffic_kpi_sql_asset():
    sql_text = _assert_sql_asset(
        "sql/mart/shop_hour_traffic_kpi.sql",
        "CREATE OR REPLACE VIEW mart.shop_hour_traffic_kpi AS",
        (
            "semantic.fact_analytics_atomic",
            "platform_code",
            "shop_id",
            "metric_date",
            "period_hour",
            "visitor_count",
            "page_views",
            "source_row_count",
        ),
    )
    assert "period_start_time IS NOT NULL" in sql_text
    assert "platform_code = 'shopee'" in sql_text
    assert "SELECT DISTINCT" in sql_text


def test_store_analysis_capability_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/store_analysis_capability_module.sql",
        "CREATE OR REPLACE VIEW api.store_analysis_capability_module AS",
        (
            "platform_code",
            "shop_id",
            "supports_hourly_daily",
            "supported_daily_mode",
            "supported_long_range_mode",
        ),
    )


def test_store_analysis_traffic_summary_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/store_analysis_traffic_summary_module.sql",
        "CREATE OR REPLACE VIEW api.store_analysis_traffic_summary_module AS",
        (
            "platform_code",
            "shop_id",
            "period_start",
            "period_end",
            "visitor_count",
            "page_views",
            "conversion_rate",
            "page_views_per_visitor",
        ),
    )


def test_store_analysis_traffic_trend_module_sql_asset():
    sql_text = _assert_sql_asset(
        "sql/api_modules/store_analysis_traffic_trend_module.sql",
        "CREATE OR REPLACE VIEW api.store_analysis_traffic_trend_module AS",
        (
            "requested_granularity",
            "effective_granularity",
            "period_key",
            "visitor_count",
            "page_views",
            "conversion_rate",
            "mart.shop_hour_traffic_kpi",
            "mart.shop_day_kpi",
            "mart.shop_month_kpi",
        ),
    )
    assert "hourly" in sql_text
    assert "daily" in sql_text
    assert "monthly" in sql_text


def test_refresh_registry_registers_store_analysis_targets():
    text = Path("backend/services/data_pipeline/refresh_registry.py").read_text(encoding="utf-8")
    assert "mart.shop_hour_traffic_kpi" in text
    assert "api.store_analysis_capability_module" in text
    assert "api.store_analysis_traffic_summary_module" in text
    assert "api.store_analysis_traffic_trend_module" in text
