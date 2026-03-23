CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_platform_share_module AS
SELECT
    period_month,
    platform_code,
    COALESCE(SUM(gmv), 0) AS gmv
FROM mart.annual_summary_shop_month
GROUP BY period_month, platform_code;
