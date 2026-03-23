CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_week_kpi AS
SELECT
    date_trunc('week', period_date)::date AS period_week,
    platform_code,
    shop_id,
    COALESCE(SUM(gmv), 0) AS gmv,
    COALESCE(SUM(order_count), 0) AS order_count,
    COALESCE(SUM(visitor_count), 0) AS visitor_count,
    COALESCE(SUM(page_views), 0) AS page_views,
    CASE
        WHEN COALESCE(SUM(visitor_count), 0) > 0
        THEN ROUND(COALESCE(SUM(order_count), 0)::numeric * 100.0 / SUM(visitor_count), 2)
        ELSE 0
    END AS conversion_rate,
    CASE
        WHEN COALESCE(SUM(order_count), 0) > 0
        THEN ROUND(COALESCE(SUM(gmv), 0)::numeric / SUM(order_count), 2)
        ELSE 0
    END AS avg_order_value,
    CASE
        WHEN COALESCE(SUM(order_count), 0) > 0
        THEN ROUND(COALESCE(SUM(total_items), 0)::numeric / SUM(order_count), 2)
        ELSE 0
    END AS attach_rate,
    COALESCE(SUM(total_items), 0) AS total_items,
    COALESCE(SUM(profit), 0) AS profit
FROM mart.shop_day_kpi
GROUP BY date_trunc('week', period_date)::date, platform_code, shop_id;
