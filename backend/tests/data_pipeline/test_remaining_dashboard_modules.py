from pathlib import Path


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text


def test_business_overview_shop_racing_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_shop_racing_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS",
        (
            "mart.shop_day_kpi",
            "mart.shop_week_kpi",
            "mart.shop_month_kpi",
            "a_class.target_breakdown",
            "a_class.sales_targets",
            "gmv",
            "order_count",
            "avg_order_value",
            "target_amount",
            "achievement_rate",
        ),
    )


def test_business_overview_traffic_ranking_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_traffic_ranking_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_traffic_ranking_module AS",
        (
            "mart.shop_day_kpi",
            "mart.shop_week_kpi",
            "mart.shop_month_kpi",
            "visitor_count",
            "page_views",
            "conversion_rate",
        ),
    )
    sql_text = Path("sql/api_modules/business_overview_traffic_ranking_module.sql").read_text(encoding="utf-8")
    assert "0::numeric AS page_views" not in sql_text


def test_business_overview_operational_metrics_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_operational_metrics_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS",
        (
            "mart.shop_month_kpi",
            "mart.shop_day_kpi",
            "a_class.sales_targets_a",
            "a_class.operating_costs",
            "monthly_target",
            "monthly_total_achieved",
            "estimated_expenses",
        ),
    )
    sql_text = Path("sql/api_modules/business_overview_operational_metrics_module.sql").read_text(encoding="utf-8")
    assert "m.gmv AS today_sales" not in sql_text
    assert "m.order_count AS today_order_count" not in sql_text
    assert "0::numeric AS time_gap" not in sql_text
