CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_kpi_module AS
SELECT
    period_month,
    platform_code,
    gmv,
    order_count,
    visitor_count,
    conversion_rate,
    avg_order_value,
    attach_rate,
    total_items,
    profit
FROM mart.platform_month_kpi;
