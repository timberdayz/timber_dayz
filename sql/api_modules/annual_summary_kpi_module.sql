CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS
WITH monthly_costs AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        SUM("租金" + "营销费用" + "水电费" + "其他成本") AS total_cost
    FROM a_class.operating_costs
    GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD')
),
monthly_kpi AS (
    SELECT
        period_month,
        SUM(gmv) AS gmv,
        SUM(order_count) AS order_count,
        SUM(COALESCE(page_views, visitor_count)) AS visitor_count,
        SUM(profit) AS profit
    FROM mart.platform_month_kpi
    GROUP BY period_month
)
SELECT
    k.period_month,
    k.gmv,
    k.order_count,
    k.visitor_count,
    c.total_cost,
    k.profit,
    CASE
        WHEN k.gmv IS NULL OR k.profit IS NULL THEN NULL
        WHEN k.gmv > 0 THEN ROUND(k.profit::numeric * 100.0 / k.gmv, 2)
        WHEN k.gmv = 0 AND k.profit = 0 THEN 0
        ELSE NULL
    END AS gross_margin,
    CASE
        WHEN k.gmv IS NULL OR k.profit IS NULL OR c.total_cost IS NULL THEN NULL
        WHEN k.gmv > 0 THEN ROUND((k.profit - c.total_cost)::numeric * 100.0 / k.gmv, 2)
        WHEN k.gmv = 0 AND k.profit = 0 AND c.total_cost = 0 THEN 0
        ELSE NULL
    END AS net_margin,
    CASE
        WHEN k.profit IS NULL OR c.total_cost IS NULL THEN NULL
        WHEN c.total_cost > 0 THEN ROUND((k.profit - c.total_cost)::numeric / c.total_cost, 2)
        WHEN c.total_cost = 0 AND k.profit = 0 THEN 0
        ELSE NULL
    END AS roi
FROM monthly_kpi k
LEFT JOIN monthly_costs c
    ON k.period_month = c.period_month;
