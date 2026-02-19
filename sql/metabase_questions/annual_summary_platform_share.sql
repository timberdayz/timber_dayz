-- =====================================================
-- Question: annual_summary_platform_share
-- 年度数据总结 - 平台 GMV 占比（仅月度粒度）
-- =====================================================
-- 用途：工作台年度数据总结饼图，按平台汇总 GMV
-- 数据源：Orders Model，**仅使用 granularity = 'monthly'**
-- 参数：{{granularity}} (monthly|yearly)、{{period}} (日期，月度=该月/年度=该年)
-- 返回：多行 platform, gmv
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
by_platform AS (
    SELECT
        COALESCE(NULLIF(TRIM(o.platform_code), ''), '其他') AS platform,
        COALESCE(SUM(o.paid_amount), 0) AS gmv
    FROM {{MODEL:Orders Model}} o
    CROSS JOIN period_dates p
    WHERE o.granularity = 'monthly'
      AND o.metric_date >= p.period_start
      AND o.metric_date < p.end_dt
    GROUP BY COALESCE(NULLIF(TRIM(o.platform_code), ''), '其他')
)
SELECT
    platform,
    ROUND(gmv::numeric, 2) AS gmv
FROM by_platform
ORDER BY gmv DESC
