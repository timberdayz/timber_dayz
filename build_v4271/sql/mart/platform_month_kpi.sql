CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.platform_month_kpi AS
WITH base AS (
    SELECT
        period_month,
        platform_code,
        COUNT(*) AS shop_row_count,
        COUNT(gmv) AS gmv_row_count,
        COUNT(order_count) AS order_count_row_count,
        COUNT(visitor_count) AS visitor_count_row_count,
        COUNT(total_items) AS total_items_row_count,
        COUNT(profit) AS profit_row_count,
        SUM(gmv) AS gmv,
        SUM(order_count) AS order_count,
        SUM(visitor_count) AS visitor_count,
        SUM(total_items) AS total_items,
        SUM(profit) AS profit
    FROM mart.shop_month_kpi
    GROUP BY period_month, platform_code
)
SELECT
    period_month,
    platform_code,
    CASE WHEN gmv_row_count = shop_row_count THEN gmv END AS gmv,
    CASE WHEN order_count_row_count = shop_row_count THEN order_count END AS order_count,
    CASE WHEN visitor_count_row_count = shop_row_count THEN visitor_count END AS visitor_count,
    CASE
        WHEN order_count_row_count = shop_row_count
         AND visitor_count_row_count = shop_row_count
         AND visitor_count > 0
        THEN ROUND(order_count::numeric * 100.0 / visitor_count, 2)
        WHEN order_count_row_count = shop_row_count
         AND visitor_count_row_count = shop_row_count
         AND visitor_count = 0
         AND order_count = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    CASE
        WHEN gmv_row_count = shop_row_count
         AND order_count_row_count = shop_row_count
         AND order_count > 0
        THEN ROUND(gmv::numeric / order_count, 2)
        WHEN gmv_row_count = shop_row_count
         AND order_count_row_count = shop_row_count
         AND order_count = 0
         AND gmv = 0
        THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN total_items_row_count = shop_row_count
         AND order_count_row_count = shop_row_count
         AND order_count > 0
        THEN ROUND(total_items::numeric / order_count, 2)
        WHEN total_items_row_count = shop_row_count
         AND order_count_row_count = shop_row_count
         AND order_count = 0
         AND total_items = 0
        THEN 0
        ELSE NULL
    END AS attach_rate,
    CASE WHEN total_items_row_count = shop_row_count THEN total_items END AS total_items,
    CASE WHEN profit_row_count = shop_row_count THEN profit END AS profit
FROM base;
