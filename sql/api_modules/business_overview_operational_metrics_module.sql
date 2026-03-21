CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
WITH monthly_targets AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        "店铺ID" AS shop_id,
        COALESCE(SUM("目标销售额"), 0) AS monthly_target
    FROM a_class.sales_targets_a
    GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD'), "店铺ID"
),
monthly_costs AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        "店铺ID" AS shop_id,
        COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS estimated_expenses
    FROM a_class.operating_costs
    GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD'), "店铺ID"
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    COALESCE(t.monthly_target, 0) AS monthly_target,
    m.gmv AS monthly_total_achieved,
    m.gmv AS today_sales,
    CASE
        WHEN COALESCE(t.monthly_target, 0) > 0
        THEN ROUND(m.gmv::numeric * 100.0 / t.monthly_target, 2)
        ELSE 0
    END AS monthly_achievement_rate,
    0::numeric AS time_gap,
    m.profit AS estimated_gross_profit,
    COALESCE(c.estimated_expenses, 0) AS estimated_expenses,
    (m.profit - COALESCE(c.estimated_expenses, 0)) AS operating_result,
    CASE
        WHEN (m.profit - COALESCE(c.estimated_expenses, 0)) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    m.order_count AS monthly_order_count,
    m.order_count AS today_order_count
FROM mart.shop_month_kpi m
LEFT JOIN monthly_targets t
    ON m.period_month = t.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '');
