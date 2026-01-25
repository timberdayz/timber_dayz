-- =====================================================
-- Question: business_overview_operational_metrics
-- 业务概览 - 经营指标（A类目标 + B类达成，与核心KPI 同参数）
-- =====================================================
-- 用途：单行汇总的月目标、当月达成、今日销售、达成率、时间GAP、费用、毛利、经营结果
-- 数据源：
--   - A类：a_class.sales_targets_a（月目标）、a_class.operating_costs（预估费用）
--   - B类：{{MODEL:Orders Model}}（当月总达成、今日销售额、订单数、毛利）
-- 参数（与核心KPI一致）：
--   {{month}} - 月份（必填，格式 YYYY-MM-DD 月初）
--   {{platform}} - 平台（可选，空=全部）
-- 说明：查看日期 = 所选月内“到今天为止”（若未到月末则今日，否则月末）
-- 返回：单行，列名与 API 一致（monthly_target 等），金额为元
-- =====================================================

WITH
scope AS (
    SELECT
        DATE_TRUNC('month', {{month}}::date)::date AS month_start,
        (DATE_TRUNC('month', {{month}}::date) + INTERVAL '1 month' - INTERVAL '1 day')::date AS month_end,
        LEAST(
            (DATE_TRUNC('month', {{month}}::date) + INTERVAL '1 month' - INTERVAL '1 day')::date,
            CURRENT_DATE
        ) AS target_date
),

b_monthly AS (
    SELECT
        COALESCE(SUM(o.sales_amount), 0) AS total_sales,
        COALESCE(SUM(o.profit), 0) AS total_profit,
        COALESCE(SUM(o.order_count), 0) AS total_orders
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN scope s
    WHERE o.granularity = 'daily'
      AND o.metric_date >= s.month_start
      AND o.metric_date <= s.target_date
      [[AND o.platform_code = {{platform}}]]
),

b_today AS (
    SELECT
        COALESCE(SUM(o.sales_amount), 0) AS today_sales,
        COALESCE(SUM(o.order_count), 0) AS today_orders
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN scope s
    WHERE o.granularity = 'daily'
      AND o.metric_date = s.target_date
      [[AND o.platform_code = {{platform}}]]
),

shops_in_scope AS (
    SELECT DISTINCT o.shop_id
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN scope s
    WHERE o.granularity = 'daily'
      AND o.metric_date >= s.month_start
      AND o.metric_date <= s.target_date
      [[AND o.platform_code = {{platform}}]]
),

a_targets AS (
    SELECT COALESCE(SUM(t.target_sales_amount), 0) AS monthly_target
    FROM a_class.sales_targets_a t
    CROSS JOIN scope s
    WHERE t.year_month = to_char(s.month_start, 'YYYY-MM')
      AND EXISTS (SELECT 1 FROM shops_in_scope sh WHERE sh.shop_id = t.shop_id)
),

a_costs AS (
    SELECT COALESCE(SUM(c.rent + c.salary + c.utilities + c.other_costs), 0) AS estimated_expenses
    FROM a_class.operating_costs c
    CROSS JOIN scope s
    WHERE c.year_month = to_char(s.month_start, 'YYYY-MM')
      AND EXISTS (SELECT 1 FROM shops_in_scope sh WHERE sh.shop_id = c.shop_id)
),

time_metrics AS (
    SELECT
        ROUND(
            EXTRACT(DAY FROM (SELECT target_date FROM scope)) * 100.0
            / NULLIF(EXTRACT(DAY FROM (SELECT month_end FROM scope)), 0),
            2
        ) AS time_progress_pct
    FROM scope
)

SELECT
    (SELECT monthly_target FROM a_targets) AS monthly_target,
    (SELECT total_sales FROM b_monthly) AS monthly_total_achieved,
    (SELECT today_sales FROM b_today) AS today_sales,
    CASE
        WHEN (SELECT monthly_target FROM a_targets) > 0
        THEN ROUND((SELECT total_sales FROM b_monthly) * 100.0 / (SELECT monthly_target FROM a_targets), 2)
        ELSE 0
    END AS monthly_achievement_rate,
    CASE
        WHEN (SELECT monthly_target FROM a_targets) > 0
        THEN ROUND(
            (SELECT total_sales FROM b_monthly) * 100.0 / (SELECT monthly_target FROM a_targets)
            - (SELECT time_progress_pct FROM time_metrics),
            2
        )
        ELSE 0
    END AS time_gap,
    (SELECT total_profit FROM b_monthly) AS estimated_gross_profit,
    (SELECT estimated_expenses FROM a_costs) AS estimated_expenses,
    (SELECT total_profit FROM b_monthly) - (SELECT estimated_expenses FROM a_costs) AS operating_result,
    CASE
        WHEN (SELECT total_profit FROM b_monthly) - (SELECT estimated_expenses FROM a_costs) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    (SELECT total_orders FROM b_monthly)::integer AS monthly_order_count,
    (SELECT today_orders FROM b_today)::integer AS today_order_count
