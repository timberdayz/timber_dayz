CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.store_analysis_traffic_summary_module AS
WITH daily AS (
    SELECT
        platform_code,
        shop_id,
        period_date::date AS period_start,
        period_date::date AS period_end,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
),
weekly AS (
    SELECT
        platform_code,
        shop_id,
        period_week::date AS period_start,
        (period_week + INTERVAL '6 day')::date AS period_end,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_week_kpi
),
monthly AS (
    SELECT
        platform_code,
        shop_id,
        period_month::date AS period_start,
        (period_month + INTERVAL '1 month - 1 day')::date AS period_end,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_month_kpi
)
SELECT
    platform_code,
    shop_id,
    period_start,
    period_end,
    visitor_count,
    page_views,
    conversion_rate,
    CASE
        WHEN visitor_count > 0 THEN ROUND(page_views * 1.0 / visitor_count, 2)
        WHEN visitor_count = 0 AND page_views = 0 THEN 0
        ELSE NULL
    END AS page_views_per_visitor
FROM daily
UNION ALL
SELECT
    platform_code,
    shop_id,
    period_start,
    period_end,
    visitor_count,
    page_views,
    conversion_rate,
    CASE
        WHEN visitor_count > 0 THEN ROUND(page_views * 1.0 / visitor_count, 2)
        WHEN visitor_count = 0 AND page_views = 0 THEN 0
        ELSE NULL
    END AS page_views_per_visitor
FROM weekly
UNION ALL
SELECT
    platform_code,
    shop_id,
    period_start,
    period_end,
    visitor_count,
    page_views,
    conversion_rate,
    CASE
        WHEN visitor_count > 0 THEN ROUND(page_views * 1.0 / visitor_count, 2)
        WHEN visitor_count = 0 AND page_views = 0 THEN 0
        ELSE NULL
    END AS page_views_per_visitor
FROM monthly;
