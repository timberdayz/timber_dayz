CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_inventory_snapshot AS
-- ====================================================
-- Inventory Model - 搴撳瓨鏁版嵁鍩熸ā鍨嬶紙CTE鍒嗗眰鏋舵瀯锛?
-- ====================================================
-- 鐢ㄩ€旓細鏁村悎鎵€鏈夊钩鍙扮殑搴撳瓨鏁版嵁锛岀粺涓€瀛楁鍚嶏紝涓哄墠绔彁渚涘畬鏁存暟鎹敮鎸?
-- 鏁版嵁婧愶細b_class schema 涓嬬殑鎵€鏈?inventory 鐩稿叧琛?
-- 骞冲彴锛歴hopee, tiktok, miaoshou
-- 绮掑害锛歴napshot锛堝簱瀛樻暟鎹彧鏈夊揩鐓э紝鏃?daily/weekly/monthly锛?
-- 鍘婚噸绛栫暐锛氬熀浜?data_hash锛屾寜 ingest_timestamp 闄嶅簭锛堟渶鏂颁紭鍏堬級
-- 浼樺寲锛欳TE鍒嗗眰鏋舵瀯锛屾彁鍗囧彲璇绘€у拰缁存姢鎬?
-- ====================================================

WITH 
-- ====================================================
-- 绗?灞傦細瀛楁鏄犲皠锛堟彁鍙栨墍鏈夊€欓€夊瓧娈碉紝涓嶅仛鏍煎紡鍖栵級
-- ====================================================
field_mapping AS (
  -- Shopee 搴撳瓨蹇収鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'浠撳簱', raw_data->>'浠撳簱鍚嶇О', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'浠撳簱缂栫爜', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'鍙敤搴撳瓨', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'鍦ㄥ簱搴撳瓨', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'閿佸畾搴撳瓨', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'鍦ㄩ€斿簱瀛?, raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缂鸿揣鏁伴噺', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'琛ヨ揣鐐?, raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'瀹夊叏搴撳瓨', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'鎴愭湰', raw_data->>'鎴愭湰浠?, raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'搴撳瓨閲戦', raw_data->>'搴撳瓨浠峰€?, raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_inventory_snapshot
  
  UNION ALL
  
  -- TikTok 搴撳瓨蹇収鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'浠撳簱', raw_data->>'浠撳簱鍚嶇О', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'浠撳簱缂栫爜', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'鍙敤搴撳瓨', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'鍦ㄥ簱搴撳瓨', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'閿佸畾搴撳瓨', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'鍦ㄩ€斿簱瀛?, raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缂鸿揣鏁伴噺', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'琛ヨ揣鐐?, raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'瀹夊叏搴撳瓨', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'鎴愭湰', raw_data->>'鎴愭湰浠?, raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'搴撳瓨閲戦', raw_data->>'搴撳瓨浠峰€?, raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_inventory_snapshot
  
  UNION ALL
  
  -- 濡欐墜ERP 搴撳瓨蹇収鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'浠撳簱', raw_data->>'浠撳簱鍚嶇О', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name_raw,
    COALESCE(raw_data->>'浠撳簱缂栫爜', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code_raw,
    COALESCE(raw_data->>'鍙敤搴撳瓨', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
    COALESCE(raw_data->>'鍦ㄥ簱搴撳瓨', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
    COALESCE(raw_data->>'閿佸畾搴撳瓨', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
    COALESCE(raw_data->>'鍦ㄩ€斿簱瀛?, raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
    COALESCE(raw_data->>'缂鸿揣鏁伴噺', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
    COALESCE(raw_data->>'琛ヨ揣鐐?, raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
    COALESCE(raw_data->>'瀹夊叏搴撳瓨', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'鎴愭湰', raw_data->>'鎴愭湰浠?, raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
    COALESCE(raw_data->>'搴撳瓨閲戦', raw_data->>'搴撳瓨浠峰€?, raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_inventory_snapshot
),

-- ====================================================
-- 绗?灞傦細鏁版嵁娓呮礂锛堢粺涓€鏍煎紡鍖栭€昏緫锛屽鐞嗙牬鎶樺彿绛夌壒娈婂瓧绗︼級
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
    -- 瀹夊叏鏁板€艰浆鎹細浠呭悎娉曟暟鍊兼墠 ::NUMERIC锛岀暩褰㈡暟鎹厹搴曚负 NULL
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
-- 绗?灞傦細鍘婚噸锛堝熀浜?data_hash锛屾寜 ingest_timestamp 闄嶅簭锛屾渶鏂颁紭鍏堬級
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
-- 绗?灞傦細鏈€缁堣緭鍑猴紙鍙繚鐣欏幓閲嶅悗鐨勬暟鎹紝璁剧疆榛樿鍊硷級
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

