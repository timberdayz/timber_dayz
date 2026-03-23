CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.annual_summary_shop_month AS
WITH monthly_costs AS (
    SELECT
        to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
        shop_id AS shop_id,
        COALESCE(SUM(rent + salary + utilities + other_costs), 0) AS total_cost
    FROM a_class.operating_costs
    GROUP BY to_date(year_month || '-01', 'YYYY-MM-DD'), shop_id
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    m.gmv,
    m.order_count,
    m.visitor_count,
    m.conversion_rate,
    m.avg_order_value,
    m.attach_rate,
    m.profit,
    COALESCE(c.total_cost, 0) AS total_cost,
    CASE
        WHEN COALESCE(m.gmv, 0) > 0
        THEN ROUND(COALESCE(m.profit, 0)::numeric * 100.0 / m.gmv, 2)
        ELSE 0
    END AS gross_margin,
    CASE
        WHEN COALESCE(m.gmv, 0) > 0
        THEN ROUND((COALESCE(m.profit, 0) - COALESCE(c.total_cost, 0))::numeric * 100.0 / m.gmv, 2)
        ELSE 0
    END AS net_margin,
    CASE
        WHEN COALESCE(c.total_cost, 0) > 0
        THEN ROUND((COALESCE(m.profit, 0) - COALESCE(c.total_cost, 0))::numeric / c.total_cost, 2)
        ELSE 0
    END AS roi
FROM mart.shop_month_kpi m
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '');
