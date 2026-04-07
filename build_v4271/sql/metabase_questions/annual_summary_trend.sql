-- =====================================================
-- Question: annual_summary_trend
-- 年度数据总结 - 月度/年度趋势（仅月度粒度）
-- =====================================================
-- 用途：工作台年度数据总结趋势折线图，按月份返回 GMV、总成本、利润
-- 数据源：Orders Model（仅 granularity='monthly'），a_class.operating_costs 按年月汇总
-- 参数：{{granularity}} (monthly|yearly)、{{period}} (日期，月度=该月/年度=该年)
-- 返回：多行 month, gmv, total_cost, profit
-- =====================================================

WITH
period_scope AS (
    SELECT
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date
             ELSE date_trunc('month', ({{period}})::date)::date END AS period_start,
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date + INTERVAL '1 year'
             ELSE date_trunc('month', ({{period}})::date)::date + INTERVAL '1 month' END AS period_end_ts
    FROM (SELECT 1) t
),
-- 月度序列：年度时为当年 1～12 月，月度时为单月
months AS (
    SELECT to_char(d, 'YYYY-MM') AS month_label, d::date AS month_start,
           (d + INTERVAL '1 month')::date AS month_end
    FROM generate_series(
        (SELECT period_start FROM period_scope),
        (SELECT period_end_ts - INTERVAL '1 month' FROM period_scope),
        '1 month'
    ) AS d
),
-- 各月 GMV、利润、B 类成本（仅 monthly 粒度）
order_by_month AS (
    SELECT
        to_char(o.metric_date, 'YYYY-MM') AS month_label,
        COALESCE(SUM(o.paid_amount), 0) AS gmv,
        COALESCE(SUM(o.profit), 0) AS profit,
        COALESCE(SUM(o.purchase_amount), 0) + COALESCE(SUM(o.warehouse_operation_fee), 0) + COALESCE(SUM(o.platform_total_cost_derived), 0) AS total_cost_b
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN period_scope s
    WHERE o.granularity = 'monthly'
      AND o.metric_date >= s.period_start
      AND o.metric_date < s.period_end_ts
    GROUP BY to_char(o.metric_date, 'YYYY-MM')
),
-- 各月 A 类运营成本汇总（a_class.operating_costs 按年月汇总）
cost_agg AS (
    SELECT
        oc."年月" AS month_label,
        SUM(COALESCE(oc.租金, 0) + COALESCE(oc.工资, 0) + COALESCE(oc.水电费, 0) + COALESCE(oc.其他成本, 0)) AS total_cost_a
    FROM a_class.operating_costs oc
    CROSS JOIN period_scope s
    WHERE oc."年月" >= to_char(s.period_start, 'YYYY-MM')
      AND oc."年月" <= to_char((SELECT period_end_ts FROM period_scope) - INTERVAL '1 day', 'YYYY-MM')
    GROUP BY oc."年月"
)
SELECT
    m.month_label AS month,
    ROUND(COALESCE(obm.gmv, 0)::numeric, 2) AS gmv,
    ROUND((COALESCE(c.total_cost_a, 0) + COALESCE(obm.total_cost_b, 0))::numeric, 2) AS total_cost,
    ROUND(COALESCE(obm.profit, 0)::numeric, 2) AS profit
FROM months m
LEFT JOIN order_by_month obm ON obm.month_label = m.month_label
LEFT JOIN cost_agg c ON c.month_label = m.month_label
ORDER BY m.month_label
