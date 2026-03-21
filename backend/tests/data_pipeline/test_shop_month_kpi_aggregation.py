from pathlib import Path


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text


def test_shop_day_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/shop_day_kpi.sql",
        "CREATE OR REPLACE VIEW mart.shop_day_kpi AS",
        (
            "semantic.fact_orders_atomic",
            "semantic.fact_analytics_atomic",
            "platform_code",
            "shop_id",
            "gmv",
            "order_count",
            "visitor_count",
            "conversion_rate",
        ),
    )


def test_shop_week_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/shop_week_kpi.sql",
        "CREATE OR REPLACE VIEW mart.shop_week_kpi AS",
        (
            "date_trunc('week'",
            "gmv",
            "order_count",
            "visitor_count",
            "attach_rate",
        ),
    )


def test_shop_month_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/shop_month_kpi.sql",
        "CREATE OR REPLACE VIEW mart.shop_month_kpi AS",
        (
            "date_trunc('month'",
            "gmv",
            "order_count",
            "visitor_count",
            "avg_order_value",
            "attach_rate",
            "profit",
        ),
    )


def test_platform_month_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/platform_month_kpi.sql",
        "CREATE OR REPLACE VIEW mart.platform_month_kpi AS",
        (
            "mart.shop_month_kpi",
            "platform_code",
            "period_month",
            "gmv",
            "order_count",
            "visitor_count",
        ),
    )


def test_business_overview_kpi_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_kpi_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_kpi_module AS",
        (
            "mart.platform_month_kpi",
            "period_month",
            "platform_code",
            "gmv",
            "order_count",
            "visitor_count",
            "conversion_rate",
            "avg_order_value",
            "attach_rate",
        ),
    )
