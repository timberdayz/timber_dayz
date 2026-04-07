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
        -- 查看日期（累计达成的截止日期）：使用传入日期与今天的较小值
        -- 确保不会查询未来的数据
        LEAST({{month}}::date, CURRENT_DATE) AS target_date,
        -- 今日查询日期：直接使用传入的日期（前端传递的是用户选择的具体日期）
        -- 如果日期超过今天，则使用今天（因为未来的数据还没有）
        LEAST({{month}}::date, CURRENT_DATE) AS today_query_date
),

-- B类数据：当月总达成（使用 paid_amount，因为 sales_amount 没有数据）
b_monthly AS (
    SELECT
        COALESCE(SUM(o.paid_amount), 0) AS total_sales,
        COALESCE(SUM(o.profit), 0) AS total_profit,
        COUNT(DISTINCT o.order_id) AS total_orders
    FROM {{MODEL:Orders Model}} AS o
    CROSS JOIN scope s
    WHERE o.metric_date >= s.month_start
      AND o.metric_date <= s.target_date
      [[AND o.platform_code = {{platform}}]]
),

-- B类数据：指定日期销售
-- today_query_date = 用户选择的日期（如果超过今天则使用今天）
-- today_sales 显示该具体日期的销售额
b_today AS (
    SELECT
        COALESCE(SUM(o.paid_amount), 0) AS today_sales,
        COUNT(DISTINCT o.order_id) AS today_orders
    FROM {{MODEL:Orders Model}} AS o
    CROSS JOIN scope s
    WHERE o.metric_date = s.today_query_date
      [[AND o.platform_code = {{platform}}]]
),

-- A类数据：月目标（使用中文字段名）
-- 注意：目标应该独立于订单数据存在，直接按年月汇总所有目标
-- 如果提供了平台参数，通过 dim_shops 表关联平台筛选
a_targets AS (
    SELECT COALESCE(SUM(t."目标销售额"), 0) AS monthly_target
    FROM a_class.sales_targets_a t
    CROSS JOIN scope s
    WHERE t."年月" = to_char(s.month_start, 'YYYY-MM')
      -- 如果提供了平台参数，通过 dim_shops 关联筛选
      [[AND EXISTS (
          SELECT 1 FROM core.dim_shops ds 
          WHERE ds.shop_id = t."店铺ID" 
            AND LOWER(ds.platform_code) = LOWER({{platform}})
      )]]
),

-- A类数据：预估费用（使用中文字段名）
a_costs AS (
    SELECT COALESCE(SUM(c."租金" + c."工资" + c."水电费" + c."其他成本"), 0) AS estimated_expenses
    FROM a_class.operating_costs c
    CROSS JOIN scope s
    WHERE c."年月" = to_char(s.month_start, 'YYYY-MM')
      -- 如果提供了平台参数，通过 dim_shops 关联筛选
      [[AND EXISTS (
          SELECT 1 FROM core.dim_shops ds 
          WHERE ds.shop_id = c."店铺ID" 
            AND LOWER(ds.platform_code) = LOWER({{platform}})
      )]]
),

-- 时间进度计算
-- 使用日期差计算：已过天数 / 总天数 * 100
-- 公式：(target_date - month_start + 1) / (month_end - month_start + 1) * 100
time_metrics AS (
    SELECT
        ROUND(
            ((SELECT target_date FROM scope) - (SELECT month_start FROM scope) + 1)::numeric * 100.0
            / NULLIF(((SELECT month_end FROM scope) - (SELECT month_start FROM scope) + 1)::numeric, 0),
            2
        ) AS time_progress_pct
    FROM scope
)

-- 最终输出
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
