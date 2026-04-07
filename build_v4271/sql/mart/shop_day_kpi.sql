CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_day_kpi AS
WITH daily_orders AS (
    SELECT
        metric_date::date AS period_date,
        platform_code,
        shop_id,
        SUM(paid_amount) AS gmv,
        CASE
            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)
            ELSE NULL
        END AS order_count,
        SUM(product_quantity) AS total_items,
        SUM(profit) AS profit,
        COUNT(*) AS source_row_count
    FROM semantic.fact_orders_atomic
    WHERE granularity = 'daily'
    GROUP BY metric_date::date, platform_code, shop_id
),
daily_traffic AS (
    SELECT
        metric_date::date AS period_date,
        platform_code,
        shop_id,
        SUM(visitor_count) AS visitor_count,
        SUM(page_views) AS page_views,
        COUNT(*) AS source_row_count
    FROM semantic.fact_analytics_atomic
    WHERE granularity = 'daily'
    GROUP BY metric_date::date, platform_code, shop_id
)
SELECT
    COALESCE(o.period_date, t.period_date) AS period_date,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    COALESCE(o.shop_id, t.shop_id) AS shop_id,
    CASE WHEN o.source_row_count > 0 THEN o.gmv END AS gmv,
    CASE WHEN o.source_row_count > 0 THEN o.order_count END AS order_count,
    CASE WHEN t.source_row_count > 0 THEN t.visitor_count END AS visitor_count,
    CASE WHEN t.source_row_count > 0 THEN t.page_views END AS page_views,
    CASE
        WHEN o.source_row_count > 0 AND t.source_row_count > 0 AND t.visitor_count > 0
        THEN ROUND(o.order_count * 100.0 / t.visitor_count, 2)
        WHEN o.source_row_count > 0 AND t.source_row_count > 0 AND t.visitor_count = 0 AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    CASE
        WHEN o.source_row_count > 0 AND o.order_count > 0
        THEN ROUND(o.gmv::numeric / o.order_count, 2)
        WHEN o.source_row_count > 0 AND o.order_count = 0 AND o.gmv = 0
        THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN o.source_row_count > 0 AND o.order_count > 0
        THEN ROUND(o.total_items::numeric / o.order_count, 2)
        WHEN o.source_row_count > 0 AND o.order_count = 0 AND o.total_items = 0
        THEN 0
        ELSE NULL
    END AS attach_rate,
    CASE WHEN o.source_row_count > 0 THEN o.total_items END AS total_items,
    CASE WHEN o.source_row_count > 0 THEN o.profit END AS profit
FROM daily_orders o
FULL OUTER JOIN daily_traffic t
    ON o.period_date = t.period_date
   AND o.platform_code = t.platform_code
   AND COALESCE(o.shop_id, '') = COALESCE(t.shop_id, '');
