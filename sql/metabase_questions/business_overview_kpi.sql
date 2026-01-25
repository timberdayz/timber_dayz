-- =====================================================
-- Question: business_overview_kpi
-- 业务概览 - 核心KPI指标
-- =====================================================
-- 用途：提供业务概览页面的核心KPI指标（全公司月度汇总）
-- 数据源：
--   - {{MODEL:Orders Model}} - 订单明细数据
--   - {{MODEL:Analytics Model}} - 流量分析数据
-- 参数：
--   {{month}} - 月份选择（必填，格式：YYYY-MM-DD，传入月初日期）
--   {{platform}} - 平台筛选（可选，为空选择全部平台）
-- 返回格式：单行数据，包含所有KPI指标 + 环比（较上月）
-- =====================================================

WITH
-- 本月与上月时间范围
month_scope AS (
    SELECT
        DATE_TRUNC('month', {{month}}::date) AS period_start,
        DATE_TRUNC('month', {{month}}::date) + INTERVAL '1 month' AS period_end,
        DATE_TRUNC('month', {{month}}::date) - INTERVAL '1 month' AS prev_start,
        DATE_TRUNC('month', {{month}}::date) AS prev_end
),

-- 订单数据聚合（从 Orders Model）- 本月
-- 注意：Orders Model 是订单明细数据，granularity 表示数据采集来源，不需要过滤
-- GMV 使用 paid_amount（实付金额）计算
order_metrics AS (
    SELECT
        COALESCE(SUM(paid_amount), 0) AS total_gmv,
        COUNT(DISTINCT order_id) AS total_orders
    FROM {{MODEL:Orders Model}} AS orders_model
    CROSS JOIN month_scope m
    WHERE metric_date >= m.period_start AND metric_date < m.period_end
        [[AND platform_code = {{platform}}]]
),

-- 订单数据聚合 - 上月（用于环比）
order_metrics_prev AS (
    SELECT
        COALESCE(SUM(paid_amount), 0) AS total_gmv_prev,
        COUNT(DISTINCT order_id) AS total_orders_prev
    FROM {{MODEL:Orders Model}} AS orders_model
    CROSS JOIN month_scope m
    WHERE metric_date >= m.prev_start AND metric_date < m.prev_end
        [[AND platform_code = {{platform}}]]
),

-- 流量数据聚合（从 Analytics Model）- 本月
traffic_metrics AS (
    SELECT
        COALESCE(SUM(visitor_count), 0) AS total_visitors
    FROM {{MODEL:Analytics Model}} AS analytics_model
    CROSS JOIN month_scope m
    WHERE granularity = 'daily'
        AND metric_date >= m.period_start AND metric_date < m.period_end
        [[AND platform_code = {{platform}}]]
),

-- 流量数据聚合 - 上月
traffic_metrics_prev AS (
    SELECT
        COALESCE(SUM(visitor_count), 0) AS total_visitors_prev
    FROM {{MODEL:Analytics Model}} AS analytics_model
    CROSS JOIN month_scope m
    WHERE granularity = 'daily'
        AND metric_date >= m.prev_start AND metric_date < m.prev_end
        [[AND platform_code = {{platform}}]]
),

-- 本月与上月汇总（单行）
combo AS (
    SELECT
        o.total_gmv,
        o.total_orders,
        t.total_visitors,
        op.total_gmv_prev,
        op.total_orders_prev,
        tp.total_visitors_prev,
        CASE WHEN t.total_visitors > 0 THEN ROUND(o.total_orders::numeric / t.total_visitors * 100, 2) ELSE 0 END AS conversion_rate,
        CASE WHEN tp.total_visitors_prev > 0 THEN ROUND(op.total_orders_prev::numeric / tp.total_visitors_prev * 100, 2) ELSE 0 END AS conversion_rate_prev,
        CASE WHEN o.total_orders > 0 THEN ROUND(o.total_gmv / o.total_orders, 2) ELSE 0 END AS aov,
        CASE WHEN op.total_orders_prev > 0 THEN ROUND(op.total_gmv_prev / op.total_orders_prev, 2) ELSE 0 END AS aov_prev
    FROM order_metrics o
    CROSS JOIN traffic_metrics t
    CROSS JOIN order_metrics_prev op
    CROSS JOIN traffic_metrics_prev tp
)

-- 最终输出：本月指标 + 环比（环比 = (本月-上月)/上月*100，上月为0时为 NULL）
SELECT
    c.total_gmv AS "GMV(元)",
    c.total_orders AS "订单数",
    c.total_visitors AS "访客数",
    c.conversion_rate AS "转化率(%)",
    c.aov AS "客单价(元)",
    ROUND((c.total_gmv - c.total_gmv_prev) * 100.0 / NULLIF(c.total_gmv_prev, 0), 2) AS "GMV环比(%)",
    ROUND((c.total_orders - c.total_orders_prev) * 100.0 / NULLIF(c.total_orders_prev, 0), 2) AS "订单数环比(%)",
    ROUND((c.total_visitors - c.total_visitors_prev) * 100.0 / NULLIF(c.total_visitors_prev, 0), 2) AS "访客数环比(%)",
    ROUND((c.conversion_rate - c.conversion_rate_prev) * 100.0 / NULLIF(c.conversion_rate_prev, 0), 2) AS "转化率环比(%)",
    ROUND((c.aov - c.aov_prev) * 100.0 / NULLIF(c.aov_prev, 0), 2) AS "客单价环比(%)"
FROM combo c
