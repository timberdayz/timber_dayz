-- =====================================================
-- Question: business_overview_shop_racing
-- 业务概览 - 店铺赛马
-- =====================================================
-- 用途：店铺/平台排名对比（按GMV排序）
-- 数据源：Orders Model
-- 参数：
--   {{granularity}} - 粒度（daily/weekly/monthly）
--   {{date}} - 日期（必填）
--   {{group_by}} - 分组维度（shop/platform，默认 shop）
--   {{platforms}} - 平台筛选（可选）
-- =====================================================

WITH filtered_data AS (
    SELECT
        platform_code,
        shop_id,
        sales_amount,
        order_count,
        buyer_count
    FROM {{#1}}  -- Orders Model
    WHERE granularity = {{granularity}}
        AND metric_date = {{date}}
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
),

-- 按店铺分组
shop_ranking AS (
    SELECT
        platform_code AS "平台",
        shop_id AS "店铺ID",
        COALESCE(SUM(sales_amount), 0) AS "GMV",
        COALESCE(SUM(order_count), 0) AS "订单数",
        COALESCE(SUM(buyer_count), 0) AS "买家数",
        CASE 
            WHEN SUM(order_count) > 0 
            THEN ROUND(SUM(sales_amount) / SUM(order_count), 2)
            ELSE 0 
        END AS "客单价",
        ROW_NUMBER() OVER (ORDER BY SUM(sales_amount) DESC) AS "排名"
    FROM filtered_data
    GROUP BY platform_code, shop_id
),

-- 按平台分组
platform_ranking AS (
    SELECT
        platform_code AS "平台",
        'ALL' AS "店铺ID",
        COALESCE(SUM(sales_amount), 0) AS "GMV",
        COALESCE(SUM(order_count), 0) AS "订单数",
        COALESCE(SUM(buyer_count), 0) AS "买家数",
        CASE 
            WHEN SUM(order_count) > 0 
            THEN ROUND(SUM(sales_amount) / SUM(order_count), 2)
            ELSE 0 
        END AS "客单价",
        ROW_NUMBER() OVER (ORDER BY SUM(sales_amount) DESC) AS "排名"
    FROM filtered_data
    GROUP BY platform_code
)

-- 根据 group_by 参数选择输出
SELECT * FROM (
    SELECT * FROM shop_ranking
    WHERE {{group_by}} = 'shop' OR {{group_by}} IS NULL
    
    UNION ALL
    
    SELECT * FROM platform_ranking
    WHERE {{group_by}} = 'platform'
) combined
ORDER BY "排名"
LIMIT 50
