-- ====================================================
-- Inventory Model - 库存数据域模型（CTE分层架构）
-- ====================================================
-- 用途：整合所有平台的库存数据，统一字段名，为前端提供完整数据支持
-- 数据源：b_class schema 下的所有 inventory 相关表
-- 平台：shopee, tiktok, miaoshou
-- 粒度：snapshot（库存数据只有快照，无 daily/weekly/monthly）
-- 去重策略：基于 data_hash，按 ingest_timestamp 降序（最新优先）
-- 优化：CTE分层架构，提升可读性和维护性
-- ====================================================

WITH 
-- ====================================================
-- 第1层：字段映射（提取所有候选字段，不做格式化）
-- ====================================================
field_mapping AS (
  -- Shopee 库存快照数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'仓库', raw_data->>'仓库名称', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'仓库编码', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'可用库存', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'在库库存', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'锁定库存', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'在途库存', raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缺货数量', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'补货点', raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'安全库存', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'成本', raw_data->>'成本价', raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'库存金额', raw_data->>'库存价值', raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_inventory_snapshot
  
  UNION ALL
  
  -- TikTok 库存快照数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'仓库', raw_data->>'仓库名称', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'仓库编码', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'可用库存', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'在库库存', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'锁定库存', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'在途库存', raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缺货数量', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'补货点', raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'安全库存', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'成本', raw_data->>'成本价', raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'库存金额', raw_data->>'库存价值', raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_inventory_snapshot
  
  UNION ALL
  
  -- 妙手ERP 库存快照数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'仓库', raw_data->>'仓库名称', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'仓库编码', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'可用库存', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'在库库存', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'锁定库存', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'在途库存', raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缺货数量', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'补货点', raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'安全库存', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'成本', raw_data->>'成本价', raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'库存金额', raw_data->>'库存价值', raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_inventory_snapshot
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，处理破折号等特殊字符）
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    product_id_raw AS product_id,
    product_name_raw AS product_name,
    platform_sku_raw AS platform_sku,
    sku_id_raw AS sku_id,
    product_sku_raw AS product_sku,
    warehouse_name_raw AS warehouse_name,
    warehouse_code_raw AS warehouse_code,
    -- 安全数值转换：仅合法数值才 ::NUMERIC，畸形数据兜底为 NULL
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(available_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS available_stock,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(on_hand_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS on_hand_stock,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(reserved_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS reserved_stock,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(in_transit_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS in_transit_stock,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stockout_qty_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS stockout_qty,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(reorder_point_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS reorder_point,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(safety_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS safety_stock,
    currency_raw AS currency,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unit_cost_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS unit_cost,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(inventory_value_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS inventory_value,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM field_mapping
),

-- ====================================================
-- 第3层：去重（基于 data_hash，按 ingest_timestamp 降序，最新优先）
-- ====================================================
deduplicated AS (
  SELECT 
    *,
    ROW_NUMBER() OVER (
      PARTITION BY platform_code, shop_id, data_hash 
      ORDER BY ingest_timestamp DESC
    ) AS rn
  FROM cleaned
)

-- ====================================================
-- 第4层：最终输出（只保留去重后的数据，设置默认值）
-- ====================================================
SELECT 
  platform_code, shop_id, data_domain, granularity,
  metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
  product_id, product_name, platform_sku, sku_id, product_sku,
  warehouse_name, warehouse_code,
  COALESCE(available_stock, 0) AS available_stock,
  COALESCE(on_hand_stock, 0) AS on_hand_stock,
  COALESCE(reserved_stock, 0) AS reserved_stock,
  COALESCE(in_transit_stock, 0) AS in_transit_stock,
  COALESCE(stockout_qty, 0) AS stockout_qty,
  COALESCE(reorder_point, 0) AS reorder_point,
  COALESCE(safety_stock, 0) AS safety_stock,
  currency,
  COALESCE(unit_cost, 0) AS unit_cost,
  COALESCE(inventory_value, 0) AS inventory_value,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1
