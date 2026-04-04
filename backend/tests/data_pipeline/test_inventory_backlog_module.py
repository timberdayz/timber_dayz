from pathlib import Path


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text


def test_product_day_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/product_day_kpi.sql",
        "CREATE OR REPLACE VIEW mart.product_day_kpi AS",
        (
            "semantic.fact_products_atomic",
            "metric_date",
            "platform_code",
            "shop_id",
            "platform_sku",
            "sales_amount",
            "order_count",
        ),
    )


def test_inventory_current_sql_asset():
    _assert_sql_asset(
        "sql/mart/inventory_current.sql",
        "CREATE OR REPLACE VIEW mart.inventory_current AS",
        (
            "semantic.fact_inventory_snapshot",
            "ROW_NUMBER() OVER",
            "available_stock",
            "inventory_value",
            "snapshot_date",
        ),
    )


def test_inventory_backlog_base_sql_asset():
    _assert_sql_asset(
        "sql/mart/inventory_backlog_base.sql",
        "CREATE OR REPLACE VIEW mart.inventory_backlog_base AS",
        (
            "mart.inventory_snapshot_latest",
            "mart.inventory_snapshot_change",
            "semantic.fact_orders_atomic",
            "estimated_turnover_days",
            "daily_avg_sales",
            "stagnant_snapshot_count",
            "estimated_stagnant_days",
            "risk_level",
            "clearance_priority_score",
            "available_stock",
            "inventory_value",
        ),
    )


def test_inventory_backlog_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_inventory_backlog_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_inventory_backlog_module AS",
        (
            "mart.inventory_backlog_base",
            "estimated_turnover_days",
            "stagnant_snapshot_count",
            "estimated_stagnant_days",
            "risk_level",
            "clearance_priority_score",
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )


def test_inventory_backlog_summary_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/inventory_backlog_summary_module.sql",
        "CREATE OR REPLACE VIEW api.inventory_backlog_summary_module AS",
        (
            "mart.inventory_backlog_base",
            "backlog_30d_value",
            "backlog_60d_value",
            "backlog_90d_value",
            "high_risk_sku_count",
            "avg_clearance_priority_score",
        ),
    )


def test_clearance_ranking_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/clearance_ranking_module.sql",
        "CREATE OR REPLACE VIEW api.clearance_ranking_module AS",
        (
            "mart.inventory_backlog_base",
            "estimated_turnover_days",
            "daily_avg_sales",
            "stagnant_snapshot_count",
            "estimated_stagnant_days",
            "risk_level",
            "clearance_priority_score",
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )
