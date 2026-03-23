from pathlib import Path


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text


def test_annual_summary_shop_month_sql_asset():
    _assert_sql_asset(
        "sql/mart/annual_summary_shop_month.sql",
        "CREATE OR REPLACE VIEW mart.annual_summary_shop_month AS",
        (
            "mart.shop_month_kpi",
            "a_class.operating_costs",
            "gmv",
            "total_cost",
            "gross_margin",
            "net_margin",
            "roi",
        ),
    )


def test_annual_summary_kpi_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/annual_summary_kpi_module.sql",
        "CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS",
        (
            "mart.annual_summary_shop_month",
            "gmv",
            "total_cost",
            "gross_margin",
            "net_margin",
            "roi",
        ),
    )


def test_annual_summary_trend_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/annual_summary_trend_module.sql",
        "CREATE OR REPLACE VIEW api.annual_summary_trend_module AS",
        (
            "mart.annual_summary_shop_month",
            "period_month",
            "gmv",
            "total_cost",
            "profit",
        ),
    )


def test_annual_summary_platform_share_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/annual_summary_platform_share_module.sql",
        "CREATE OR REPLACE VIEW api.annual_summary_platform_share_module AS",
        (
            "mart.annual_summary_shop_month",
            "platform_code",
            "gmv",
        ),
    )


def test_annual_summary_by_shop_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/annual_summary_by_shop_module.sql",
        "CREATE OR REPLACE VIEW api.annual_summary_by_shop_module AS",
        (
            "mart.annual_summary_shop_month",
            "shop_id",
            "platform_code",
            "gmv",
            "total_cost",
            "roi",
        ),
    )
