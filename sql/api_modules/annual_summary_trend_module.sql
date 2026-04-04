CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_trend_module AS
SELECT
    period_month,
    CASE WHEN COUNT(gmv) = COUNT(*) THEN SUM(gmv) END AS gmv,
    CASE WHEN COUNT(total_cost) = COUNT(*) THEN SUM(total_cost) END AS total_cost,
    CASE WHEN COUNT(profit) = COUNT(*) THEN SUM(profit) END AS profit
FROM mart.annual_summary_shop_month
GROUP BY period_month;
