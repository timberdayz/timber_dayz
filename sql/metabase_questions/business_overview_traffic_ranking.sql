-- =====================================================
-- Question: business_overview_traffic_ranking
-- 业务概览 - 流量排名
-- =====================================================
-- 用途：流量相关指标排名（访客数、浏览量）
-- 数据源：Analytics Model
-- 参数：
--   {{granularity}} - 粒度（daily/weekly/monthly）
--   {{dimension}} - 排序维度（visitor/pv，默认 visitor）
--   {{date}} - 日期（必填）
--   {{platforms}} - 平台筛选（可选）
--   {{shops}} - 店铺筛选（可选）
-- =====================================================

WITH filtered_data AS (
    SELECT
        platform_code,
        shop_id,
        visitor_count,
        page_views,
        conversion_rate
    FROM {{#2}}  -- Analytics Model
    WHERE granularity = {{granularity}}
        AND metric_date = {{date}}
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
),

-- 店铺流量汇总
shop_traffic AS (
    SELECT
        platform_code AS "平台",
        shop_id AS "店铺ID",
        COALESCE(SUM(visitor_count), 0) AS "访客数",
        COALESCE(SUM(page_views), 0) AS "浏览量",
        ROUND(AVG(conversion_rate) * 100, 2) AS "转化率(%)",
        CASE 
            WHEN SUM(visitor_count) > 0 
            THEN ROUND(SUM(page_views)::NUMERIC / SUM(visitor_count), 2)
            ELSE 0 
        END AS "人均浏览量"
    FROM filtered_data
    GROUP BY platform_code, shop_id
)

-- 按访客数或浏览量排序
SELECT
    "平台",
    "店铺ID",
    "访客数",
    "浏览量",
    "转化率(%)",
    "人均浏览量",
    CASE 
        WHEN {{dimension}} = 'pv' THEN ROW_NUMBER() OVER (ORDER BY "浏览量" DESC)
        ELSE ROW_NUMBER() OVER (ORDER BY "访客数" DESC)
    END AS "排名"
FROM shop_traffic
ORDER BY 
    CASE 
        WHEN {{dimension}} = 'pv' THEN "浏览量"
        ELSE "访客数"
    END DESC
LIMIT 50
