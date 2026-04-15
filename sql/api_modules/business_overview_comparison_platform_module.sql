CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_comparison_platform_module AS
SELECT
    'daily'::varchar AS granularity,
    period_date AS period_key,
    platform_code,
    gmv AS sales_amount,
    order_count AS sales_quantity,
    COALESCE(page_views, visitor_count) AS traffic,
    conversion_rate,
    avg_order_value,
    attach_rate,
    profit
FROM mart.platform_day_kpi
UNION ALL
SELECT
    'weekly'::varchar AS granularity,
    period_week AS period_key,
    platform_code,
    gmv AS sales_amount,
    order_count AS sales_quantity,
    COALESCE(page_views, visitor_count) AS traffic,
    conversion_rate,
    avg_order_value,
    attach_rate,
    profit
FROM mart.platform_week_kpi
UNION ALL
SELECT
    'monthly'::varchar AS granularity,
    period_month AS period_key,
    platform_code,
    gmv AS sales_amount,
    order_count AS sales_quantity,
    COALESCE(page_views, visitor_count) AS traffic,
    conversion_rate,
    avg_order_value,
    attach_rate,
    profit
FROM mart.platform_month_kpi;
