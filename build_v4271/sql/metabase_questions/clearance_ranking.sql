-- =====================================================
-- Question: clearance_ranking
-- 清仓排名
-- =====================================================
-- 用途：清仓商品排名（滞销商品分析）
-- 数据源：Products Model + Inventory Model
-- 参数：
--   {{start_date}} - 开始日期（必填）
--   {{end_date}} - 结束日期（必填）
--   {{platforms}} - 平台筛选（可选）
--   {{shops}} - 店铺筛选（可选）
--   {{limit}} - 返回数量（默认 100）
-- =====================================================

WITH product_sales AS (
    -- 获取产品销售数据
    SELECT
        platform_code,
        shop_id,
        sku,
        product_name,
        COALESCE(SUM(sales_amount), 0) AS total_sales,
        COALESCE(SUM(order_count), 0) AS total_orders,
        COUNT(DISTINCT metric_date) AS active_days
    FROM {{#3}}  -- Products Model
    WHERE granularity = 'daily'
        AND metric_date >= {{start_date}}
        AND metric_date <= {{end_date}}
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
    GROUP BY platform_code, shop_id, sku, product_name
),

latest_inventory AS (
    -- 获取最新库存
    SELECT DISTINCT ON (platform_code, shop_id, sku)
        platform_code,
        shop_id,
        sku,
        available_stock,
        inventory_value
    FROM {{#4}}  -- Inventory Model
    WHERE 1=1
        {% if platforms %}
        AND platform_code IN ({{platforms}})
        {% endif %}
        {% if shops %}
        AND shop_id IN ({{shops}})
        {% endif %}
    ORDER BY platform_code, shop_id, sku, metric_date DESC
),

-- 计算滞销指标
clearance_analysis AS (
    SELECT
        COALESCE(p.platform_code, i.platform_code) AS platform_code,
        COALESCE(p.shop_id, i.shop_id) AS shop_id,
        COALESCE(p.sku, i.sku) AS sku,
        COALESCE(p.product_name, '') AS product_name,
        COALESCE(p.total_sales, 0) AS total_sales,
        COALESCE(p.total_orders, 0) AS total_orders,
        COALESCE(p.active_days, 0) AS active_days,
        COALESCE(i.available_stock, 0) AS current_stock,
        COALESCE(i.inventory_value, 0) AS inventory_value,
        -- 日均销量
        CASE 
            WHEN COALESCE(p.active_days, 0) > 0 
            THEN ROUND(COALESCE(p.total_orders, 0)::NUMERIC / p.active_days, 2)
            ELSE 0 
        END AS daily_avg_sales,
        -- 预估周转天数
        CASE 
            WHEN COALESCE(p.total_orders, 0) > 0 AND COALESCE(p.active_days, 0) > 0
            THEN ROUND(
                COALESCE(i.available_stock, 0) / 
                (COALESCE(p.total_orders, 0)::NUMERIC / p.active_days), 
                0
            )
            ELSE 9999  -- 无销售记录，标记为超长周转
        END AS estimated_turnover_days
    FROM product_sales p
    FULL OUTER JOIN latest_inventory i 
        ON p.platform_code = i.platform_code 
        AND p.shop_id = i.shop_id 
        AND p.sku = i.sku
    WHERE COALESCE(i.available_stock, 0) > 0  -- 只看有库存的
)

-- 最终输出：按滞销程度排序
SELECT
    platform_code AS "平台",
    shop_id AS "店铺ID",
    sku AS "SKU",
    product_name AS "商品名称",
    current_stock AS "当前库存",
    inventory_value AS "库存价值",
    total_sales AS "期间销售额",
    total_orders AS "期间销量",
    daily_avg_sales AS "日均销量",
    estimated_turnover_days AS "预估周转天数",
    CASE 
        WHEN estimated_turnover_days >= 180 THEN '严重滞销'
        WHEN estimated_turnover_days >= 90 THEN '中度滞销'
        WHEN estimated_turnover_days >= 60 THEN '轻度滞销'
        ELSE '正常'
    END AS "滞销等级",
    ROW_NUMBER() OVER (ORDER BY estimated_turnover_days DESC, inventory_value DESC) AS "排名"
FROM clearance_analysis
WHERE estimated_turnover_days >= 30  -- 周转天数 >= 30 天的商品
ORDER BY estimated_turnover_days DESC, inventory_value DESC
LIMIT COALESCE({{limit}}, 100)
