CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.store_analysis_traffic_trend_module AS
WITH shopee_hourly_daily AS (
    SELECT
        platform_code,
        shop_id,
        'daily'::varchar AS requested_granularity,
        'hourly'::varchar AS effective_granularity,
        period_hour AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_hour_traffic_kpi
),
non_shopee_daily AS (
    SELECT
        platform_code,
        shop_id,
        'daily'::varchar AS requested_granularity,
        'daily'::varchar AS effective_granularity,
        period_date AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
    WHERE platform_code <> 'shopee'
),
weekly_daily AS (
    SELECT
        platform_code,
        shop_id,
        'weekly'::varchar AS requested_granularity,
        'daily'::varchar AS effective_granularity,
        period_date AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
),
monthly_daily AS (
    SELECT
        platform_code,
        shop_id,
        'monthly'::varchar AS requested_granularity,
        'daily'::varchar AS effective_granularity,
        period_date AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
),
quarterly_daily AS (
    SELECT
        platform_code,
        shop_id,
        'quarterly'::varchar AS requested_granularity,
        'daily'::varchar AS effective_granularity,
        period_date AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_day_kpi
),
yearly_monthly AS (
    SELECT
        platform_code,
        shop_id,
        'yearly'::varchar AS requested_granularity,
        'monthly'::varchar AS effective_granularity,
        period_month AS period_key,
        visitor_count,
        page_views,
        conversion_rate
    FROM mart.shop_month_kpi
)
SELECT * FROM shopee_hourly_daily
UNION ALL
SELECT * FROM non_shopee_daily
UNION ALL
SELECT * FROM weekly_daily
UNION ALL
SELECT * FROM monthly_daily
UNION ALL
SELECT * FROM quarterly_daily
UNION ALL
SELECT * FROM yearly_monthly;
