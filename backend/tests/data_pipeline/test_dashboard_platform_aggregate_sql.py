from pathlib import Path


def _read_sql(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def test_platform_day_kpi_sql_asset_exists():
    sql_text = _read_sql("sql/mart/platform_day_kpi.sql")

    assert "CREATE OR REPLACE VIEW mart.platform_day_kpi AS" in sql_text
    assert "semantic.fact_orders_atomic" in sql_text
    assert "semantic.fact_analytics_atomic" in sql_text
    assert "GROUP BY" in sql_text
    assert "platform_code" in sql_text


def test_platform_week_kpi_sql_asset_exists():
    sql_text = _read_sql("sql/mart/platform_week_kpi.sql")

    assert "CREATE OR REPLACE VIEW mart.platform_week_kpi AS" in sql_text
    assert "semantic.fact_orders_atomic" in sql_text
    assert "semantic.fact_analytics_atomic" in sql_text
    assert "platform_code" in sql_text


def test_platform_month_kpi_no_longer_requires_full_shop_completeness():
    sql_text = _read_sql("sql/mart/platform_month_kpi.sql")

    assert "COUNT(gmv) AS gmv_row_count" not in sql_text
    assert "COUNT(order_count) AS order_count_row_count" not in sql_text
    assert "COUNT(visitor_count) AS visitor_count_row_count" not in sql_text
    assert "CASE WHEN gmv_row_count = shop_row_count THEN gmv END" not in sql_text
    assert "semantic.fact_orders_monthly_atomic" in sql_text or "mart.shop_month_kpi" not in sql_text


def test_annual_summary_modules_do_not_use_strict_shop_null_gating():
    kpi_sql = _read_sql("sql/api_modules/annual_summary_kpi_module.sql")
    trend_sql = _read_sql("sql/api_modules/annual_summary_trend_module.sql")
    share_sql = _read_sql("sql/api_modules/annual_summary_platform_share_module.sql")

    assert "COUNT(*) AS shop_row_count" not in kpi_sql
    assert "CASE WHEN COUNT(gmv) = COUNT(*) THEN SUM(gmv) END" not in trend_sql
    assert "CASE WHEN COUNT(gmv) = COUNT(*) THEN SUM(gmv) END" not in share_sql
    assert "platform_month_kpi" in kpi_sql or "platform_month_cost" in kpi_sql
