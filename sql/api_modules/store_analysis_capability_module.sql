CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.store_analysis_capability_module AS
WITH distinct_shops AS (
    SELECT DISTINCT platform_code, shop_id
    FROM mart.shop_month_kpi
)
SELECT
    platform_code,
    shop_id,
    CASE WHEN platform_code = 'shopee' THEN TRUE ELSE FALSE END AS supports_hourly_daily,
    CASE WHEN platform_code = 'shopee' THEN 'hourly' ELSE 'daily' END AS supported_daily_mode,
    'monthly'::varchar AS supported_long_range_mode
FROM distinct_shops;
