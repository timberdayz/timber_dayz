CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.platform_month_kpi AS
WITH monthly_orders AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        SUM(paid_amount) AS gmv,
        CASE
            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric
            ELSE NULL
        END AS order_count,
        SUM(product_quantity) AS total_items,
        SUM(profit) AS profit
    FROM semantic.fact_orders_monthly_atomic
    GROUP BY date_trunc('month', metric_date)::date, platform_code
),
monthly_traffic AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        SUM(visitor_count) AS visitor_count,
        SUM(page_views) AS page_views,
        SUM(impressions) AS impressions
    FROM semantic.fact_analytics_monthly_atomic
    GROUP BY date_trunc('month', metric_date)::date, platform_code
)
SELECT
    COALESCE(o.period_month, t.period_month) AS period_month,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    o.gmv,
    o.order_count,
    t.visitor_count,
    t.page_views,
    t.impressions,
    CASE
        WHEN o.order_count IS NOT NULL AND t.visitor_count IS NOT NULL AND t.visitor_count > 0
        THEN ROUND(o.order_count::numeric * 100.0 / t.visitor_count, 2)
        WHEN o.order_count IS NOT NULL AND t.visitor_count = 0 AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    CASE
        WHEN o.order_count IS NOT NULL AND t.visitor_count IS NOT NULL AND t.visitor_count > 0
        THEN ROUND(o.order_count::numeric * 100.0 / t.visitor_count, 2)
        WHEN o.order_count IS NOT NULL AND t.visitor_count = 0 AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS uv_conversion_rate,
    CASE
        WHEN o.order_count IS NOT NULL AND t.page_views IS NOT NULL AND t.page_views > 0
        THEN ROUND(o.order_count::numeric * 100.0 / t.page_views, 2)
        WHEN o.order_count IS NOT NULL AND t.page_views = 0 AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS pv_conversion_rate,
    CASE
        WHEN t.visitor_count IS NOT NULL AND t.impressions IS NOT NULL AND t.impressions > 0
        THEN ROUND(t.visitor_count::numeric * 100.0 / t.impressions, 2)
        WHEN t.visitor_count = 0 AND t.impressions = 0
        THEN 0
        ELSE NULL
    END AS visit_rate,
    CASE
        WHEN t.page_views IS NOT NULL AND t.visitor_count IS NOT NULL AND t.visitor_count > 0
        THEN ROUND(t.page_views::numeric / t.visitor_count, 2)
        WHEN t.page_views = 0 AND t.visitor_count = 0
        THEN 0
        ELSE NULL
    END AS browse_depth,
    CASE
        WHEN o.order_count IS NOT NULL AND t.impressions IS NOT NULL AND t.impressions > 0
        THEN ROUND(o.order_count::numeric * 100.0 / t.impressions, 2)
        WHEN o.order_count = 0 AND t.impressions = 0
        THEN 0
        ELSE NULL
    END AS exposure_order_rate,
    CASE
        WHEN o.gmv IS NOT NULL AND o.order_count > 0
        THEN ROUND(o.gmv::numeric / o.order_count, 2)
        WHEN o.gmv IS NOT NULL AND o.order_count = 0 AND o.gmv = 0
        THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN o.total_items IS NOT NULL AND o.order_count > 0
        THEN ROUND(o.total_items::numeric / o.order_count, 2)
        WHEN o.total_items IS NOT NULL AND o.order_count = 0 AND o.total_items = 0
        THEN 0
        ELSE NULL
    END AS attach_rate,
    o.total_items,
    o.profit
FROM monthly_orders o
FULL OUTER JOIN monthly_traffic t
    ON o.period_month = t.period_month
   AND o.platform_code = t.platform_code;
