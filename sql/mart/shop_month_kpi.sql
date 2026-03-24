CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_month_kpi AS
WITH monthly_order_candidates AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        COALESCE(SUM(paid_amount), 0) AS gmv,
        COUNT(DISTINCT order_id)::numeric AS order_count,
        COALESCE(SUM(product_quantity), 0) AS total_items,
        COALESCE(SUM(profit), 0) AS profit,
        1 AS priority
    FROM semantic.fact_orders_atomic
    WHERE granularity = 'monthly'
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id
    UNION ALL
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        COALESCE(SUM(paid_amount), 0) AS gmv,
        COUNT(DISTINCT order_id)::numeric AS order_count,
        COALESCE(SUM(product_quantity), 0) AS total_items,
        COALESCE(SUM(profit), 0) AS profit,
        2 AS priority
    FROM semantic.fact_orders_atomic
    WHERE granularity = 'daily'
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id
),
monthly_orders AS (
    SELECT period_month, platform_code, shop_id, gmv, order_count, total_items, profit
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY period_month, platform_code, shop_id
                   ORDER BY priority
               ) AS rn
        FROM monthly_order_candidates
    ) ranked
    WHERE rn = 1
),
monthly_traffic_candidates AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        COALESCE(SUM(visitor_count), 0) AS visitor_count,
        COALESCE(SUM(page_views), 0) AS page_views,
        1 AS priority
    FROM semantic.fact_analytics_atomic
    WHERE granularity = 'monthly'
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id
    UNION ALL
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        COALESCE(SUM(visitor_count), 0) AS visitor_count,
        COALESCE(SUM(page_views), 0) AS page_views,
        2 AS priority
    FROM semantic.fact_analytics_atomic
    WHERE granularity = 'daily'
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id
),
monthly_traffic AS (
    SELECT period_month, platform_code, shop_id, visitor_count, page_views
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY period_month, platform_code, shop_id
                   ORDER BY priority
               ) AS rn
        FROM monthly_traffic_candidates
    ) ranked
    WHERE rn = 1
)
SELECT
    COALESCE(o.period_month, t.period_month) AS period_month,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    COALESCE(o.shop_id, t.shop_id) AS shop_id,
    COALESCE(o.gmv, 0) AS gmv,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(t.visitor_count, 0) AS visitor_count,
    COALESCE(t.page_views, 0) AS page_views,
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
FROM monthly_orders o
FULL OUTER JOIN monthly_traffic t
    ON o.period_month = t.period_month
   AND o.platform_code = t.platform_code
   AND COALESCE(o.shop_id, '') = COALESCE(t.shop_id, '');
