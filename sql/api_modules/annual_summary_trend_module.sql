CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_trend_module AS
SELECT
    period_month,
    COALESCE(SUM(gmv), 0) AS gmv,
    COALESCE(SUM(total_cost), 0) AS total_cost,
    COALESCE(SUM(profit), 0) AS profit
FROM mart.annual_summary_shop_month
GROUP BY period_month;
