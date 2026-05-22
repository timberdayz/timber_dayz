CREATE SCHEMA IF NOT EXISTS mart;

-- Canonical schema contract:
-- - a_class.operating_costs columns: year_month (YYYY-MM), shop_id, rent, marketing_fee, marketing, logistics, utilities, other, total
-- Legacy column-name compatibility should be handled at ingestion/semantic layer instead of dynamic SQL.

CREATE OR REPLACE VIEW mart.annual_summary_shop_month AS
WITH monthly_costs AS (
    SELECT
        to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
        shop_id AS shop_id,
        SUM(COALESCE(total, 0)) AS total_cost
    FROM a_class.operating_costs
    GROUP BY to_date(year_month || '-01', 'YYYY-MM-DD'), shop_id
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    m.gmv,
    m.order_count,
    COALESCE(m.page_views, m.visitor_count) AS visitor_count,
    m.conversion_rate,
    m.avg_order_value,
    m.attach_rate,
    m.profit,
    c.total_cost,
    CASE
        WHEN m.gmv IS NULL OR m.profit IS NULL THEN NULL
        WHEN m.gmv > 0 THEN ROUND(m.profit::numeric * 100.0 / m.gmv, 2)
        WHEN m.gmv = 0 AND m.profit = 0 THEN 0
        ELSE NULL
    END AS gross_margin,
    CASE
        WHEN m.gmv IS NULL OR m.profit IS NULL OR c.total_cost IS NULL THEN NULL
        WHEN m.gmv > 0 THEN ROUND((m.profit - c.total_cost)::numeric * 100.0 / m.gmv, 2)
        WHEN m.gmv = 0 AND m.profit = 0 AND c.total_cost = 0 THEN 0
        ELSE NULL
    END AS net_margin,
    CASE
        WHEN m.profit IS NULL OR c.total_cost IS NULL THEN NULL
        WHEN c.total_cost > 0 THEN ROUND((m.profit - c.total_cost)::numeric / c.total_cost, 2)
        WHEN c.total_cost = 0 AND m.profit = 0 THEN 0
        ELSE NULL
    END AS roi
FROM mart.shop_month_kpi m
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '');

