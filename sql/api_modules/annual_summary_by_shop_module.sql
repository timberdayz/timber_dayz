CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_by_shop_module AS
SELECT
    period_month,
    platform_code,
    shop_id,
    gmv,
    order_count,
    visitor_count,
    total_cost,
    profit,
    gross_margin,
    net_margin,
    roi
FROM mart.annual_summary_shop_month;
