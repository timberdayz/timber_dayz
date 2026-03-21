CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_day_kpi AS
WITH daily_orders AS (
    SELECT
        metric_date::date AS period_date,
        platform_code,
        shop_id,
        COALESCE(SUM(paid_amount), 0) AS gmv,
        COUNT(DISTINCT order_id) AS order_count,
        COALESCE(SUM(product_quantity), 0) AS total_items,
        COALESCE(SUM(profit), 0) AS profit
    FROM semantic.fact_orders_atomic
    WHERE granularity = 'daily'
    GROUP BY metric_date::date, platform_code, shop_id
),
daily_traffic AS (
    SELECT
        metric_date::date AS period_date,
        platform_code,
        shop_id,
        COALESCE(SUM(visitor_count), 0) AS visitor_count
    FROM semantic.fact_analytics_atomic
    WHERE granularity = 'daily'
    GROUP BY metric_date::date, platform_code, shop_id
)
SELECT
    COALESCE(o.period_date, t.period_date) AS period_date,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    COALESCE(o.shop_id, t.shop_id) AS shop_id,
    COALESCE(o.gmv, 0) AS gmv,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(t.visitor_count, 0) AS visitor_count,
    CASE
        WHEN COALESCE(t.visitor_count, 0) > 0
        THEN ROUND(COALESCE(o.order_count, 0)::numeric * 100.0 / t.visitor_count, 2)
        ELSE 0
    END AS conversion_rate,
    CASE
        WHEN COALESCE(o.order_count, 0) > 0
        THEN ROUND(COALESCE(o.gmv, 0)::numeric / o.order_count, 2)
        ELSE 0
    END AS avg_order_value,
    CASE
        WHEN COALESCE(o.order_count, 0) > 0
        THEN ROUND(COALESCE(o.total_items, 0)::numeric / o.order_count, 2)
        ELSE 0
    END AS attach_rate,
    COALESCE(o.total_items, 0) AS total_items,
    COALESCE(o.profit, 0) AS profit
FROM daily_orders o
FULL OUTER JOIN daily_traffic t
    ON o.period_date = t.period_date
   AND o.platform_code = t.platform_code
   AND COALESCE(o.shop_id, '') = COALESCE(t.shop_id, '');
