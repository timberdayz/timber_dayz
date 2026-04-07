-- =====================================================
-- Question: business_overview_traffic_ranking
-- 业务概览 - 流量排名
-- =====================================================
-- 用途：流量相关指标排名（访客数、浏览量）+ 本期/上期与环比
-- 数据源：Analytics Model（shop_id 为空时按平台汇总）
-- 参数：
--   {{granularity}} - 粒度（daily/weekly/monthly）
--   {{dimension}} - 排序维度（visitor/pv，默认 visitor）
--   {{date}} - 日期（必填，YYYY-MM-DD）
--   {{platforms}} - 平台筛选（可选）
--   {{shops}} - 店铺筛选（可选）
-- 环比：本期 vs 上期（日=昨日，周=上周，月=上月）；对比期UV/PV = 上期绝对值
-- =====================================================

WITH params AS (
    SELECT {{date}}::date AS target_date, {{granularity}} AS gran
),
period_scope AS (
    SELECT
        (SELECT target_date FROM params) AS target_date,
        (SELECT gran FROM params) AS gran,
        CASE (SELECT gran FROM params)
            WHEN 'daily' THEN (SELECT target_date FROM params)
            WHEN 'weekly' THEN (date_trunc('week', (SELECT target_date FROM params))::date)
            WHEN 'monthly' THEN (date_trunc('month', (SELECT target_date FROM params))::date)
        END AS current_period_start,
        CASE (SELECT gran FROM params)
            WHEN 'daily' THEN (SELECT target_date FROM params)
            WHEN 'weekly' THEN (date_trunc('week', (SELECT target_date FROM params))::date + 6)
            WHEN 'monthly' THEN (date_trunc('month', (SELECT target_date FROM params))::date + interval '1 month' - interval '1 day')
        END::date AS current_period_end,
        CASE (SELECT gran FROM params)
            WHEN 'daily' THEN (SELECT target_date FROM params) - 1
            WHEN 'weekly' THEN (date_trunc('week', (SELECT target_date FROM params))::date - 7)
            WHEN 'monthly' THEN (date_trunc('month', (SELECT target_date FROM params))::date - interval '1 month')::date
        END AS prev_period_start,
        CASE (SELECT gran FROM params)
            WHEN 'daily' THEN (SELECT target_date FROM params) - 1
            WHEN 'weekly' THEN (date_trunc('week', (SELECT target_date FROM params))::date - 1)
            WHEN 'monthly' THEN (date_trunc('month', (SELECT target_date FROM params))::date - interval '1 month' + interval '1 month' - interval '1 day')::date
        END AS prev_period_end
),

current_aggregate AS (
    SELECT
        m.platform_code,
        m.shop_id,
        COALESCE(SUM(m.visitor_count), 0) AS cur_visitors,
        COALESCE(SUM(m.page_views), 0) AS cur_views,
        ROUND(AVG(m.conversion_rate) * 100, 2) AS conversion_pct
    FROM ( {{MODEL:Analytics Model}} ) AS m
    CROSS JOIN period_scope s
    WHERE (
        (s.gran = 'daily' AND m.granularity = 'daily' AND m.metric_date = s.target_date)
        OR (s.gran = 'weekly' AND m.granularity = 'weekly' AND m.metric_date >= s.current_period_start AND m.metric_date <= s.current_period_end)
        OR (s.gran = 'monthly' AND m.granularity = 'monthly' AND m.metric_date >= s.current_period_start AND m.metric_date <= s.current_period_end)
        OR (s.gran = 'monthly' AND m.granularity = 'daily' AND m.metric_date >= s.current_period_start AND m.metric_date <= s.current_period_end)
    )
    [[ AND m.platform_code IN ({{platforms}}) ]]
    [[ AND m.shop_id IN ({{shops}}) ]]
    GROUP BY m.platform_code, m.shop_id
),

prev_aggregate AS (
    SELECT
        m.platform_code,
        m.shop_id,
        COALESCE(SUM(m.visitor_count), 0) AS prev_visitors,
        COALESCE(SUM(m.page_views), 0) AS prev_views
    FROM ( {{MODEL:Analytics Model}} ) AS m
    CROSS JOIN period_scope s
    WHERE (
        (s.gran = 'daily' AND m.granularity = 'daily' AND m.metric_date = s.prev_period_start)
        OR (s.gran = 'weekly' AND m.granularity = 'weekly' AND m.metric_date >= s.prev_period_start AND m.metric_date <= s.prev_period_end)
        OR (s.gran = 'monthly' AND m.granularity = 'monthly' AND m.metric_date >= s.prev_period_start AND m.metric_date <= s.prev_period_end)
        OR (s.gran = 'monthly' AND m.granularity = 'daily' AND m.metric_date >= s.prev_period_start AND m.metric_date <= s.prev_period_end)
    )
    [[ AND m.platform_code IN ({{platforms}}) ]]
    [[ AND m.shop_id IN ({{shops}}) ]]
    GROUP BY m.platform_code, m.shop_id
),

joined AS (
    SELECT
        COALESCE(c.platform_code, p.platform_code) AS platform_code,
        COALESCE(c.shop_id, p.shop_id) AS shop_id,
        COALESCE(c.cur_visitors, 0) AS "访客数",
        COALESCE(c.cur_views, 0) AS "浏览量",
        COALESCE(c.conversion_pct, 0) AS "转化率(%)",
        CASE WHEN COALESCE(c.cur_visitors, 0) > 0
             THEN ROUND(COALESCE(c.cur_views, 0)::numeric / c.cur_visitors, 2)
             ELSE 0 END AS "人均浏览量",
        COALESCE(p.prev_visitors, 0) AS compare_unique_visitors,
        COALESCE(p.prev_views, 0) AS compare_page_views,
        ROUND(
            (COALESCE(c.cur_visitors, 0) - COALESCE(p.prev_visitors, 0)) * 100.0
            / NULLIF(COALESCE(p.prev_visitors, 0), 0),
            2
        ) AS uv_change_rate,
        ROUND(
            (COALESCE(c.cur_views, 0) - COALESCE(p.prev_views, 0)) * 100.0
            / NULLIF(COALESCE(p.prev_views, 0), 0),
            2
        ) AS pv_change_rate
    FROM current_aggregate c
    FULL OUTER JOIN prev_aggregate p
        ON c.platform_code = p.platform_code AND (c.shop_id IS NOT DISTINCT FROM p.shop_id)
)

SELECT
    platform_code AS "平台",
    shop_id AS "店铺ID",
    CASE WHEN shop_id = 'unknown' OR shop_id IS NULL OR TRIM(shop_id::text) = ''
         THEN platform_code
         ELSE COALESCE(shop_id::text, platform_code) END AS "名称",
    "访客数",
    "浏览量",
    "转化率(%)",
    "人均浏览量",
    CASE
        WHEN {{dimension}} = 'pv' THEN ROW_NUMBER() OVER (ORDER BY "浏览量" DESC)
        ELSE ROW_NUMBER() OVER (ORDER BY "访客数" DESC)
    END AS "排名",
    compare_unique_visitors,
    compare_page_views,
    uv_change_rate,
    pv_change_rate
FROM joined
ORDER BY
    CASE WHEN {{dimension}} = 'pv' THEN "浏览量" ELSE "访客数" END DESC
LIMIT 50
