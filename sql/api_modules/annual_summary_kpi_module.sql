CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS
SELECT
    period_month,
    COALESCE(SUM(gmv), 0) AS gmv,
    COALESCE(SUM(order_count), 0) AS order_count,
    COALESCE(SUM(visitor_count), 0) AS visitor_count,
    COALESCE(SUM(total_cost), 0) AS total_cost,
    COALESCE(SUM(profit), 0) AS profit,
    CASE
        WHEN COALESCE(SUM(gmv), 0) > 0
        THEN ROUND(COALESCE(SUM(profit), 0)::numeric * 100.0 / SUM(gmv), 2)
        ELSE 0
    END AS gross_margin,
    CASE
        WHEN COALESCE(SUM(gmv), 0) > 0
        THEN ROUND((COALESCE(SUM(profit), 0) - COALESCE(SUM(total_cost), 0))::numeric * 100.0 / SUM(gmv), 2)
        ELSE 0
    END AS net_margin,
    CASE
        WHEN COALESCE(SUM(total_cost), 0) > 0
        THEN ROUND((COALESCE(SUM(profit), 0) - COALESCE(SUM(total_cost), 0))::numeric / SUM(total_cost), 2)
        ELSE 0
    END AS roi
FROM mart.annual_summary_shop_month
GROUP BY period_month;
