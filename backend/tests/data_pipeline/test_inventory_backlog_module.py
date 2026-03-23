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
            "mart.inventory_current",
            "semantic.fact_orders_atomic",
            "estimated_turnover_days",
            "daily_avg_sales",
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
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )


def test_clearance_ranking_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/clearance_ranking_module.sql",
        "CREATE OR REPLACE VIEW api.clearance_ranking_module AS",
        (
            "mart.inventory_backlog_base",
            "mart.product_day_kpi",
            "estimated_turnover_days",
            "daily_avg_sales",
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )
