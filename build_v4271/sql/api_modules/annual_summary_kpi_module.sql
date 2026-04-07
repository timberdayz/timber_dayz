CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS
WITH base AS (
    SELECT
        period_month,
        COUNT(*) AS shop_row_count,
        COUNT(gmv) AS gmv_row_count,
        COUNT(order_count) AS order_count_row_count,
        COUNT(visitor_count) AS visitor_count_row_count,
        COUNT(total_cost) AS total_cost_row_count,
        COUNT(profit) AS profit_row_count,
        SUM(gmv) AS gmv,
        SUM(order_count) AS order_count,
        SUM(visitor_count) AS visitor_count,
        SUM(total_cost) AS total_cost,
        SUM(profit) AS profit
    FROM mart.annual_summary_shop_month
    GROUP BY period_month
)
SELECT
    period_month,
    CASE WHEN gmv_row_count = shop_row_count THEN gmv END AS gmv,
    CASE WHEN order_count_row_count = shop_row_count THEN order_count END AS order_count,
    CASE WHEN visitor_count_row_count = shop_row_count THEN visitor_count END AS visitor_count,
    CASE WHEN total_cost_row_count = shop_row_count THEN total_cost END AS total_cost,
    CASE WHEN profit_row_count = shop_row_count THEN profit END AS profit,
    CASE
        WHEN gmv_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND gmv > 0
        THEN ROUND(profit::numeric * 100.0 / gmv, 2)
        WHEN gmv_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND gmv = 0
         AND profit = 0
        THEN 0
        ELSE NULL
    END AS gross_margin,
    CASE
        WHEN gmv_row_count = shop_row_count
         AND total_cost_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND gmv > 0
        THEN ROUND((profit - total_cost)::numeric * 100.0 / gmv, 2)
        WHEN gmv_row_count = shop_row_count
         AND total_cost_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND gmv = 0
         AND profit = 0
         AND total_cost = 0
        THEN 0
        ELSE NULL
    END AS net_margin,
    CASE
        WHEN total_cost_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND total_cost > 0
        THEN ROUND((profit - total_cost)::numeric / total_cost, 2)
        WHEN total_cost_row_count = shop_row_count
         AND profit_row_count = shop_row_count
         AND total_cost = 0
         AND profit = 0
        THEN 0
        ELSE NULL
    END AS roi
FROM base;
