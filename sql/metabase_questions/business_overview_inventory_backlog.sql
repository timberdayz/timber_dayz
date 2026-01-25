-- =====================================================
-- Question: business_overview_inventory_backlog
-- 业务概览 - 库存积压
-- =====================================================
-- 用途：库存积压分析（积压商品、积压天数）
-- 数据源：Inventory Model
-- 参数：
--   {{days}} - 积压天数阈值（默认 30）
--   {{platforms}} - 平台筛选（可选）
--   {{shops}} - 店铺筛选（可选）
-- =====================================================

WITH latest_inventory AS (
    -- 获取最新库存快照
    SELECT DISTINCT ON (platform_code, shop_id, sku)
        platform_code,
        shop_id,
        sku,
        product_name,
        available_stock,
        on_hand_stock,
        inventory_value,
        metric_date AS snapshot_date
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

-- 关联最近销售数据计算周转天数
inventory_with_sales AS (
    SELECT
        i.platform_code,
        i.shop_id,
        i.sku,
        i.product_name,
        i.available_stock,
        i.on_hand_stock,
        i.inventory_value,
        i.snapshot_date,
        -- 假设日均销量从 Orders Model 计算（这里简化为估算）
        COALESCE(i.available_stock, 0) AS current_stock,
        -- 积压天数 = 当前库存 / 日均销量（这里简化处理）
        CASE 
            WHEN COALESCE(i.available_stock, 0) > 0 
            THEN GREATEST(30, COALESCE(i.available_stock, 0) / GREATEST(1, COALESCE(i.available_stock, 0) / 90))
            ELSE 0 
        END AS estimated_days
    FROM latest_inventory i
),

-- 筛选积压商品
backlog_items AS (
    SELECT
        platform_code AS "平台",
        shop_id AS "店铺ID",
        sku AS "SKU",
        product_name AS "商品名称",
        available_stock AS "可用库存",
        on_hand_stock AS "在库库存",
        inventory_value AS "库存价值",
        snapshot_date AS "快照日期",
        ROUND(estimated_days, 0) AS "预估积压天数"
    FROM inventory_with_sales
    WHERE estimated_days >= COALESCE({{days}}, 30)
)

-- 最终输出
SELECT
    "平台",
    "店铺ID",
    "SKU",
    "商品名称",
    "可用库存",
    "在库库存",
    "库存价值",
    "快照日期",
    "预估积压天数",
    ROW_NUMBER() OVER (ORDER BY "库存价值" DESC) AS "排名"
FROM backlog_items
ORDER BY "库存价值" DESC
LIMIT 100
