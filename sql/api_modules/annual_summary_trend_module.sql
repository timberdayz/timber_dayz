CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_trend_module AS
WITH monthly AS (
    SELECT
        period_month,
        SUM(gmv) AS gmv,
        SUM(profit) AS profit,
        SUM(total_cost) AS total_cost
    FROM mart.annual_summary_shop_month
    GROUP BY period_month
)
SELECT
    period_month,
    gmv,
    total_cost,
    profit
FROM monthly;

