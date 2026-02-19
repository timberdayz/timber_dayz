-- =====================================================
-- Question: annual_summary_by_shop
-- 年度数据总结 - 按店铺下钻（仅月度粒度）
-- =====================================================
-- 用途：工作台年度数据总结按店铺表格，GMV、总成本、成本产出比、毛利率、净利率、ROI
-- 数据源：Orders Model（仅 monthly），a_class.operating_costs 按店铺+年月
-- 参数：{{granularity}} (monthly|yearly)、{{period}} (日期，月度=该月/年度=该年)
-- 返回：多行 shop_name, platform_code, shop_id, gmv, total_cost, cost_to_revenue_ratio, gross_margin, net_margin, roi
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
period_dates AS (
    SELECT period_start, (period_end_ts)::date AS end_dt FROM period_scope
),
-- 按店铺 GMV、利润（仅 monthly）
shop_orders AS (
    SELECT
        o.platform_code,
        COALESCE(NULLIF(TRIM(o.shop_id), ''), 'unknown') AS shop_id,
        COALESCE(SUM(o.paid_amount), 0) AS gmv,
        COALESCE(SUM(o.profit), 0) AS profit
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN period_dates p
    WHERE o.granularity = 'monthly'
      AND o.metric_date >= p.period_start
      AND o.metric_date < p.end_dt
    GROUP BY o.platform_code, COALESCE(NULLIF(TRIM(o.shop_id), ''), 'unknown')
),
-- 按店铺运营成本（a_class.operating_costs 店铺ID + 年月）
shop_costs AS (
    SELECT
        oc."店铺ID" AS shop_id,
        SUM(COALESCE(oc.租金, 0) + COALESCE(oc.工资, 0) + COALESCE(oc.水电费, 0) + COALESCE(oc.其他成本, 0)) AS total_cost
    FROM a_class.operating_costs oc
    CROSS JOIN period_scope s
    WHERE oc."年月" >= to_char(s.period_start, 'YYYY-MM')
      AND oc."年月" <= to_char((SELECT period_end_ts FROM period_scope) - INTERVAL '1 day', 'YYYY-MM')
    GROUP BY oc."店铺ID"
),
combined AS (
    SELECT
        so.platform_code,
        so.shop_id,
        (so.platform_code || '-' || so.shop_id) AS shop_name,
        so.gmv,
        COALESCE(sc.total_cost, 0) AS total_cost,
        so.profit
    FROM shop_orders so
    LEFT JOIN shop_costs sc ON sc.shop_id = so.shop_id
)
SELECT
    shop_name,
    platform_code,
    shop_id,
    ROUND(gmv::numeric, 2) AS gmv,
    ROUND(total_cost::numeric, 2) AS total_cost,
    ROUND(CASE WHEN gmv > 0 THEN total_cost::numeric / gmv ELSE 0 END, 4) AS cost_to_revenue_ratio,
    ROUND(CASE WHEN gmv > 0 THEN (gmv - total_cost)::numeric / gmv ELSE 0 END, 4) AS gross_margin,
    ROUND(CASE WHEN gmv > 0 THEN (gmv - total_cost)::numeric / gmv ELSE 0 END, 4) AS net_margin,
    ROUND(CASE WHEN total_cost > 0 THEN (gmv - total_cost)::numeric / total_cost ELSE 0 END, 4) AS roi
FROM combined
ORDER BY gmv DESC
