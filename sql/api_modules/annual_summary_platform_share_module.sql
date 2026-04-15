CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_platform_share_module AS
SELECT
    period_month,
    platform_code,
    gmv
FROM mart.platform_month_kpi;
