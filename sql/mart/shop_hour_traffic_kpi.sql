CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_hour_traffic_kpi AS
WITH hourly_source AS (
    SELECT
        platform_code,
        shop_id,
        metric_date::date AS metric_date,
        date_trunc('hour', period_start_time) AS period_hour,
        visitor_count,
        page_views
    FROM semantic.fact_analytics_atomic
    WHERE platform_code = 'shopee'
      AND granularity = 'daily'
      AND period_start_time IS NOT NULL
),
hourly_deduplicated AS (
    SELECT DISTINCT
        platform_code,
        shop_id,
        metric_date,
        period_hour,
        visitor_count,
        page_views
    FROM hourly_source
)
SELECT
    platform_code,
    shop_id,
    metric_date,
    period_hour,
    SUM(visitor_count) AS visitor_count,
    SUM(page_views) AS page_views,
    CASE
        WHEN SUM(visitor_count) > 0
        THEN ROUND(SUM(page_views) * 100.0 / SUM(visitor_count), 2)
        WHEN SUM(visitor_count) = 0 AND SUM(page_views) = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    COUNT(*) AS source_row_count
FROM hourly_deduplicated
GROUP BY platform_code, shop_id, metric_date, period_hour;
