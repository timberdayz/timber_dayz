-- =====================================================
-- Question: annual_summary_kpi
-- 年度数据总结 - 核心KPI（仅月度粒度）
-- =====================================================
-- 用途：工作台年度数据总结页面，仅用 monthly 粒度，支持月度/年度汇总与环比/同比
-- 数据源：Orders Model、Analytics Model，**仅使用 granularity = 'monthly'**
-- 参数：
--   {{granularity}} - monthly | yearly
--   {{period}} - 日期（type: date），月度=该月，年度=该年
-- 返回：核心 KPI + 对比期 KPI + 环比/同比（月度=较上月，年度=较去年）
-- 成本与产出由后端聚合后合并返回，本 SQL 仅返回 KPI
-- =====================================================

WITH
-- 根据粒度与周期日期计算本期与对比期（左闭右开）
period_scope AS (
    SELECT
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date
             ELSE date_trunc('month', ({{period}})::date)::date END AS period_start,
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date + INTERVAL '1 year'
             ELSE date_trunc('month', ({{period}})::date)::date + INTERVAL '1 month' END AS period_end_ts,
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date - INTERVAL '1 year'
             ELSE date_trunc('month', ({{period}})::date)::date - INTERVAL '1 month' END AS prev_start_ts,
        CASE WHEN {{granularity}} = 'yearly' THEN date_trunc('year', ({{period}})::date)::date
             ELSE date_trunc('month', ({{period}})::date)::date END AS prev_end_ts
    FROM (SELECT 1) t
),
period_dates AS (
    SELECT
        period_start,
        (period_end_ts)::date AS end_dt,
        (prev_start_ts)::date AS prev_start_dt,
        (prev_end_ts)::date AS prev_end_dt
    FROM period_scope
),

-- 在职员工数（人效口径与业务概览一致）
employee_count AS (
    SELECT COUNT(*)::numeric AS active_employee_count
    FROM a_class.employees
    WHERE status = 'active'
),

-- 订单聚合 - 本期（仅 monthly 粒度）
order_metrics AS (
    SELECT
        COALESCE(SUM(paid_amount), 0) AS total_gmv,
        COUNT(DISTINCT order_id) AS total_orders,
        COALESCE(SUM(product_quantity), 0) AS total_items
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN period_dates p
    WHERE o.granularity = 'monthly'
      AND o.metric_date >= p.period_start
      AND o.metric_date < p.end_dt
),

-- 订单聚合 - 对比期
order_metrics_prev AS (
    SELECT
        COALESCE(SUM(paid_amount), 0) AS total_gmv_prev,
        COUNT(DISTINCT order_id) AS total_orders_prev,
        COALESCE(SUM(product_quantity), 0) AS total_items_prev
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN period_dates p
    WHERE o.granularity = 'monthly'
      AND o.metric_date >= p.prev_start_dt
      AND o.metric_date < p.prev_end_dt
),

-- 流量聚合 - 本期（仅 monthly 粒度）
traffic_metrics AS (
    SELECT COALESCE(SUM(visitor_count), 0) AS total_visitors
    FROM {{MODEL:Analytics Model}} a
    CROSS JOIN period_dates p
    WHERE a.granularity = 'monthly'
      AND a.metric_date >= p.period_start
      AND a.metric_date < p.end_dt
),

-- 流量聚合 - 对比期
traffic_metrics_prev AS (
    SELECT COALESCE(SUM(visitor_count), 0) AS total_visitors_prev
    FROM {{MODEL:Analytics Model}} a
    CROSS JOIN period_dates p
    WHERE a.granularity = 'monthly'
      AND a.metric_date >= p.prev_start_dt
      AND a.metric_date < p.prev_end_dt
),

combo AS (
    SELECT
        o.total_gmv,
        o.total_orders,
        o.total_items,
        t.total_visitors,
        op.total_gmv_prev,
        op.total_orders_prev,
        op.total_items_prev,
        tp.total_visitors_prev,
        e.active_employee_count,
        CASE WHEN t.total_visitors > 0 THEN ROUND(o.total_orders::numeric / t.total_visitors * 100, 2) ELSE 0 END AS conversion_rate,
        CASE WHEN tp.total_visitors_prev > 0 THEN ROUND(op.total_orders_prev::numeric / tp.total_visitors_prev * 100, 2) ELSE 0 END AS conversion_rate_prev,
        CASE WHEN o.total_orders > 0 THEN ROUND(o.total_gmv / o.total_orders, 2) ELSE 0 END AS aov,
        CASE WHEN op.total_orders_prev > 0 THEN ROUND(op.total_gmv_prev / op.total_orders_prev, 2) ELSE 0 END AS aov_prev,
        CASE WHEN o.total_orders > 0 THEN ROUND(o.total_items::numeric / o.total_orders, 2) ELSE 0 END AS attach_rate,
        CASE WHEN op.total_orders_prev > 0 THEN ROUND(op.total_items_prev::numeric / op.total_orders_prev, 2) ELSE 0 END AS attach_rate_prev,
        CASE WHEN e.active_employee_count > 0 THEN ROUND(o.total_gmv / e.active_employee_count, 2) ELSE 0 END AS labor_efficiency,
        CASE WHEN e.active_employee_count > 0 THEN ROUND(op.total_gmv_prev / e.active_employee_count, 2) ELSE 0 END AS labor_efficiency_prev
    FROM order_metrics o
    CROSS JOIN traffic_metrics t
    CROSS JOIN order_metrics_prev op
    CROSS JOIN traffic_metrics_prev tp
    CROSS JOIN employee_count e
)

SELECT
    c.total_gmv AS "GMV(元)",
    c.total_orders AS "订单数",
    c.total_visitors AS "访客数",
    c.conversion_rate AS "转化率(%)",
    c.aov AS "客单价(元)",
    c.attach_rate AS "连带率",
    c.labor_efficiency AS "人效(元/人)",
    ROUND((c.total_gmv - c.total_gmv_prev) * 100.0 / NULLIF(c.total_gmv_prev, 0), 2) AS "GMV环比(%)",
    ROUND((c.total_orders - c.total_orders_prev) * 100.0 / NULLIF(c.total_orders_prev, 0), 2) AS "订单数环比(%)",
    ROUND((c.total_visitors - c.total_visitors_prev) * 100.0 / NULLIF(c.total_visitors_prev, 0), 2) AS "访客数环比(%)",
    ROUND((c.conversion_rate - c.conversion_rate_prev) * 100.0 / NULLIF(c.conversion_rate_prev, 0), 2) AS "转化率环比(%)",
    ROUND((c.aov - c.aov_prev) * 100.0 / NULLIF(c.aov_prev, 0), 2) AS "客单价环比(%)",
    ROUND((c.attach_rate - c.attach_rate_prev) * 100.0 / NULLIF(c.attach_rate_prev, 0), 2) AS "连带率环比(%)",
    ROUND((c.labor_efficiency - c.labor_efficiency_prev) * 100.0 / NULLIF(c.labor_efficiency_prev, 0), 2) AS "人效环比(%)"
FROM combo c
