import re
from pathlib import Path


def _assert_sql_asset(
    path_str: str, expected_prefix: str, required_terms: tuple[str, ...]
) -> None:
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
            "semantic.fact_orders_atomic",
            "semantic.fact_analytics_atomic",
            "granularity = 'weekly'",
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
            "semantic.fact_orders_monthly_atomic",
            "semantic.fact_analytics_monthly_atomic",
            "date_trunc('month', metric_date)::date AS period_month",
            "gmv",
            "order_count",
            "visitor_count",
            "avg_order_value",
            "attach_rate",
            "profit",
        ),
    )
    sql_text = Path("sql/mart/shop_month_kpi.sql").read_text(encoding="utf-8")
    assert "metric_date AS period_month" not in sql_text


def test_orders_monthly_atomic_sql_asset():
    _assert_sql_asset(
        "sql/semantic/orders_monthly_atomic.sql",
        "CREATE OR REPLACE VIEW semantic.fact_orders_monthly_atomic AS",
        (
            "semantic.fact_orders_monthly_atomic_mv",
            "paid_amount",
            "product_quantity",
            "profit",
        ),
    )
    sql_text = Path("sql/semantic/orders_monthly_atomic.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP VIEW IF EXISTS semantic.fact_orders_monthly_atomic" not in sql_text


def test_orders_monthly_atomic_mv_sql_asset():
    _assert_sql_asset(
        "sql/semantic/orders_monthly_atomic_mv.sql",
        "CREATE MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv AS",
        (
            "mapped_monthly_orders AS MATERIALIZED",
            "normalized_monthly_orders AS MATERIALIZED",
            "resolved_monthly_orders AS MATERIALIZED",
            "deduplicated_monthly_orders AS",
            "b_class.fact_shopee_orders_monthly",
            "b_class.fact_tiktok_orders_monthly",
            "b_class.fact_miaoshou_orders_monthly",
            "semantic.shop_identity_resolution_candidates",
            "order_time_raw",
            "paid_amount_raw",
            "profit_raw",
            "product_quantity_raw",
            "normalized_source_shop_id",
            "normalized_store_label_raw",
            "normalized_source_platform_shop_id",
            "normalized_source_shop_account_id",
            "normalized_identity_candidates",
            "paid_amount",
            "product_quantity",
            "profit",
            "ix_fact_orders_monthly_atomic_mv_period_platform_shop",
        ),
    )
    sql_text = Path("sql/semantic/orders_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv" not in sql_text
    assert (
        "DROP MATERIALIZED VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv CASCADE"
        in sql_text
    )
    assert "REGEXP_REPLACE(LOWER(TRIM(COALESCE(m.source_shop_id, '')))" not in sql_text
    assert "REGEXP_REPLACE(LOWER(TRIM(COALESCE(m.store_label_raw, '')))" not in sql_text


def test_analytics_monthly_atomic_sql_asset():
    _assert_sql_asset(
        "sql/semantic/analytics_monthly_atomic.sql",
        "CREATE OR REPLACE VIEW semantic.fact_analytics_monthly_atomic AS",
        (
            "semantic.fact_analytics_monthly_atomic_mv",
            "gmv",
            "order_count",
            "sku_order_count",
            "total_transaction_amount",
            "product_visitor_count",
            "visitor_count",
            "page_views",
            "impressions",
        ),
    )


def test_analytics_monthly_atomic_mv_sql_asset():
    _assert_sql_asset(
        "sql/semantic/analytics_monthly_atomic_mv.sql",
        "CREATE MATERIALIZED VIEW semantic.fact_analytics_monthly_atomic_mv AS",
        (
            "mapped_monthly_traffic AS MATERIALIZED",
            "normalized_monthly_traffic AS MATERIALIZED",
            "resolved_monthly_traffic AS MATERIALIZED",
            "b_class.fact_shopee_analytics_monthly",
            "b_class.fact_tiktok_analytics_monthly",
            "b_class.fact_miaoshou_analytics_monthly",
            "visitor_count_raw",
            "product_visitor_count_raw",
            "page_views_raw",
            "impressions_raw",
            "order_count_raw",
            "sku_order_count_raw",
            "gmv_raw",
            "total_transaction_amount_raw",
            "normalized_identity_candidates",
            "ix_fact_analytics_monthly_atomic_mv_period_platform_shop",
        ),
    )
    sql_text = Path("sql/semantic/analytics_monthly_atomic_mv.sql").read_text(
        encoding="utf-8"
    )
    # 2026-11-08: 月度链取数改走别名表 ⇒ 资产里**不许**再内联字面量表头
    # （内联表头对不上真实表头时, 出口的 COALESCE(x, 0) 会把「取不到」伪装成 0）。
    # 旧断言盯的是「出现 raw_data->>'曝光次数'」, 新断言盯的是它的反面 + 别名表取数,
    # 后者严格更强。
    for literal in (
        "raw_data->>'曝光次数'",
        "raw_data->>'访客数'",
        "raw_data->>'商品访客数'",
        "raw_data->>'页面浏览次数'",
        "raw_data->>'订单数'",
        "raw_data->>'SKU 订单数'",
        "raw_data->>'GMV'",
        "raw_data->>'总成交额'",
    ):
        assert literal not in sql_text, "月度链仍在内联取 {0}".format(literal)
    # 取数必须走别名表(单一事实源)
    assert "semantic.resolve_alias(" in sql_text
    for field in (
        "visitor_count",
        "product_visitor_count",
        "page_views",
        "impressions",
        "order_count",
        "sku_order_count",
        "gmv",
        "total_transaction_amount",
    ):
        assert "'{field}'".format(field=field) in sql_text
    # 出口不许再把「取不到」伪装成 0
    assert not re.search(r"COALESCE\(\s*\w+\s*,\s*0\s*\)\s+AS", sql_text)


def test_platform_month_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/platform_month_kpi.sql",
        "CREATE OR REPLACE VIEW mart.platform_month_kpi AS",
        (
            "semantic.fact_orders_monthly_atomic",
            "semantic.fact_analytics_monthly_atomic",
            "date_trunc('month', metric_date)::date AS period_month",
            "platform_code",
            "period_month",
            "gmv",
            "order_count",
            "visitor_count",
            "page_views",
            "impressions",
        ),
    )
    sql_text = Path("sql/mart/platform_month_kpi.sql").read_text(encoding="utf-8")
    assert "metric_date AS period_month" not in sql_text


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
            "page_views",
            "impressions",
            "conversion_rate",
            "uv_conversion_rate",
            "pv_conversion_rate",
            "visit_rate",
            "browse_depth",
            "exposure_order_rate",
            "avg_order_value",
            "attach_rate",
        ),
    )
    sql_text = Path("sql/api_modules/business_overview_kpi_module.sql").read_text(
        encoding="utf-8",
    )
    assert "COALESCE(page_views, visitor_count) AS visitor_count" not in sql_text
