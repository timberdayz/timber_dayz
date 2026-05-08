CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS
WITH monthly AS (
    SELECT
        period_month,
        SUM(gmv) AS gmv,
        SUM(order_count) AS order_count,
        SUM(visitor_count) AS visitor_count,
        SUM(profit) AS profit,
        SUM(total_cost) AS total_cost
    FROM mart.annual_summary_shop_month
    GROUP BY period_month
)
SELECT
    period_month,
    gmv,
    order_count,
    visitor_count,
    total_cost,
    profit,
    CASE
        WHEN gmv IS NULL OR profit IS NULL THEN NULL
        WHEN gmv > 0 THEN ROUND(profit::numeric * 100.0 / gmv, 2)
        WHEN gmv = 0 AND profit = 0 THEN 0
        ELSE NULL
    END AS gross_margin,
    CASE
        WHEN gmv IS NULL OR profit IS NULL OR total_cost IS NULL THEN NULL
        WHEN gmv > 0 THEN ROUND((profit - total_cost)::numeric * 100.0 / gmv, 2)
        WHEN gmv = 0 AND profit = 0 AND total_cost = 0 THEN 0
        ELSE NULL
    END AS net_margin,
    CASE
        WHEN profit IS NULL OR total_cost IS NULL THEN NULL
        WHEN total_cost > 0 THEN ROUND((profit - total_cost)::numeric / total_cost, 2)
        WHEN total_cost = 0 AND profit = 0 THEN 0
        ELSE NULL
    END AS roi
FROM monthly;

