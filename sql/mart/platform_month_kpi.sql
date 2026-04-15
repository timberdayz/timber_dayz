CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.platform_month_kpi AS
WITH monthly_orders AS (
    SELECT
        metric_date AS period_month,
        platform_code,
        SUM(paid_amount) AS gmv,
        CASE
            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric
            ELSE NULL
        END AS order_count,
        SUM(product_quantity) AS total_items,
        SUM(profit) AS profit
    FROM semantic.fact_orders_monthly_atomic
    GROUP BY metric_date, platform_code
),
monthly_traffic AS (
    SELECT
        metric_date AS period_month,
        platform_code,
        SUM(visitor_count) AS visitor_count,
        SUM(page_views) AS page_views
    FROM semantic.fact_analytics_monthly_atomic
    GROUP BY metric_date, platform_code
)
SELECT
    COALESCE(o.period_month, t.period_month) AS period_month,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    o.gmv,
    o.order_count,
    t.visitor_count,
    CASE
        WHEN o.order_count IS NOT NULL
         AND t.visitor_count IS NOT NULL
         AND t.visitor_count > 0
        THEN ROUND(o.order_count::numeric * 100.0 / t.visitor_count, 2)
        WHEN o.order_count IS NOT NULL
         AND t.visitor_count = 0
         AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    CASE
        WHEN o.gmv IS NOT NULL
         AND o.order_count > 0
        THEN ROUND(o.gmv::numeric / o.order_count, 2)
        WHEN o.gmv IS NOT NULL
         AND o.order_count = 0
         AND o.gmv = 0
        THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN o.total_items IS NOT NULL
         AND o.order_count > 0
        THEN ROUND(o.total_items::numeric / o.order_count, 2)
        WHEN o.total_items IS NOT NULL
         AND o.order_count = 0
         AND o.total_items = 0
        THEN 0
        ELSE NULL
    END AS attach_rate,
    o.total_items,
    o.profit,
    t.page_views
FROM monthly_orders o
FULL OUTER JOIN monthly_traffic t
    ON o.period_month = t.period_month
   AND o.platform_code = t.platform_code;
