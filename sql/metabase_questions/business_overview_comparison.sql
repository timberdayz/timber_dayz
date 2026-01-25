-- =====================================================
-- Question: business_overview_comparison
-- 业务概览 - 数据对比（同比、环比）
-- =====================================================
-- 用途：提供日/周/月度数据对比
-- 数据源：Orders Model
-- 参数：
--   {{granularity}} - 粒度（daily/weekly/monthly）
--   {{date}} - 对比日期（必填）
--   {{platforms}} - 平台筛选（可选）
--   {{shops}} - 店铺筛选（可选）
-- =====================================================

WITH params AS (
    SELECT
        {{date}}::DATE AS target_date,
        {{granularity}} AS granularity
),

-- 当期数据
current_period AS (
    SELECT
        COALESCE(SUM(sales_amount), 0) AS gmv,
        COALESCE(SUM(order_count), 0) AS orders,
        COALESCE(SUM(buyer_count), 0) AS buyers
    FROM {{#1}}  -- Orders Model
    WHERE granularity = (SELECT granularity FROM params)
        AND metric_date = (SELECT target_date FROM params)
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
),

-- 环比数据（上一期）
previous_period AS (
    SELECT
        COALESCE(SUM(sales_amount), 0) AS gmv,
        COALESCE(SUM(order_count), 0) AS orders,
        COALESCE(SUM(buyer_count), 0) AS buyers
    FROM {{#1}}  -- Orders Model
    WHERE granularity = (SELECT granularity FROM params)
        AND metric_date = CASE 
            WHEN (SELECT granularity FROM params) = 'daily' 
                THEN (SELECT target_date FROM params) - INTERVAL '1 day'
            WHEN (SELECT granularity FROM params) = 'weekly' 
                THEN (SELECT target_date FROM params) - INTERVAL '7 days'
            WHEN (SELECT granularity FROM params) = 'monthly' 
                THEN (SELECT target_date FROM params) - INTERVAL '1 month'
            ELSE (SELECT target_date FROM params) - INTERVAL '1 day'
        END
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
),

-- 同比数据（去年同期）
yoy_period AS (
    SELECT
        COALESCE(SUM(sales_amount), 0) AS gmv,
        COALESCE(SUM(order_count), 0) AS orders,
        COALESCE(SUM(buyer_count), 0) AS buyers
    FROM {{#1}}  -- Orders Model
    WHERE granularity = (SELECT granularity FROM params)
        AND metric_date = (SELECT target_date FROM params) - INTERVAL '1 year'
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
)

-- 最终输出
SELECT
    '当期' AS "时间段",
    c.gmv AS "GMV",
    c.orders AS "订单数",
    c.buyers AS "买家数",
    NULL AS "环比增长率(%)",
    NULL AS "同比增长率(%)"
FROM current_period c

UNION ALL

SELECT
    '环比' AS "时间段",
    p.gmv AS "GMV",
    p.orders AS "订单数",
    p.buyers AS "买家数",
    CASE 
        WHEN p.gmv > 0 
        THEN ROUND((c.gmv - p.gmv) / p.gmv * 100, 2)
        ELSE NULL 
    END AS "环比增长率(%)",
    NULL AS "同比增长率(%)"
FROM previous_period p
CROSS JOIN current_period c

UNION ALL

SELECT
    '同比' AS "时间段",
    y.gmv AS "GMV",
    y.orders AS "订单数",
    y.buyers AS "买家数",
    NULL AS "环比增长率(%)",
    CASE 
        WHEN y.gmv > 0 
        THEN ROUND((c.gmv - y.gmv) / y.gmv * 100, 2)
        ELSE NULL 
    END AS "同比增长率(%)"
FROM yoy_period y
CROSS JOIN current_period c
