CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS
SELECT
    'daily'::varchar AS granularity,
    period_date AS period_key,
    platform_code,
    shop_id,
    gmv,
    order_count,
    avg_order_value,
    attach_rate,
    profit
FROM mart.shop_day_kpi
UNION ALL
SELECT
    'weekly'::varchar AS granularity,
    period_week AS period_key,
    platform_code,
    shop_id,
    gmv,
    order_count,
    avg_order_value,
    attach_rate,
    profit
FROM mart.shop_week_kpi
UNION ALL
SELECT
    'monthly'::varchar AS granularity,
    period_month AS period_key,
    platform_code,
    shop_id,
    gmv,
    order_count,
    avg_order_value,
    attach_rate,
    profit
FROM mart.shop_month_kpi;
