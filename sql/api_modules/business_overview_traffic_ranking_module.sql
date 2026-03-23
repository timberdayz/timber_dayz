CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_traffic_ranking_module AS
WITH daily AS (
    SELECT
        'daily'::varchar AS granularity,
        period_date AS period_key,
        platform_code,
        shop_id,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
),
weekly AS (
    SELECT
        'weekly'::varchar AS granularity,
        period_week AS period_key,
        platform_code,
        shop_id,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_week_kpi
),
monthly AS (
    SELECT
        'monthly'::varchar AS granularity,
        period_month AS period_key,
        platform_code,
        shop_id,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_month_kpi
)
SELECT * FROM daily
UNION ALL
SELECT * FROM weekly
UNION ALL
SELECT * FROM monthly;
