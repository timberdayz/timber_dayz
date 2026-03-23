CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_inventory_snapshot AS
WITH raw_inventory AS (
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_inventory_snapshot
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_inventory_snapshot
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_inventory_snapshot
),
mapped AS (
    SELECT
        platform_code,
        COALESCE(NULLIF(TRIM(COALESCE(shop_id, '')), ''), 'unknown') AS shop_id,
        data_domain,
        granularity,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id,
        COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name,
        COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku,
        COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id,
        COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku,
        COALESCE(raw_data->>'仓库', raw_data->>'仓库名称', raw_data->>'warehouse', raw_data->>'Warehouse', raw_data->>'warehouse_name') AS warehouse_name,
        COALESCE(raw_data->>'仓库编码', raw_data->>'warehouse_code', raw_data->>'Warehouse Code') AS warehouse_code,
        COALESCE(raw_data->>'可用库存', raw_data->>'available_stock', raw_data->>'Available Stock', raw_data->>'available') AS available_stock_raw,
        COALESCE(raw_data->>'在库库存', raw_data->>'on_hand_stock', raw_data->>'On Hand Stock', raw_data->>'on_hand') AS on_hand_stock_raw,
        COALESCE(raw_data->>'锁定库存', raw_data->>'reserved_stock', raw_data->>'Reserved Stock', raw_data->>'reserved') AS reserved_stock_raw,
        COALESCE(raw_data->>'在途库存', raw_data->>'in_transit_stock', raw_data->>'In Transit Stock', raw_data->>'in_transit') AS in_transit_stock_raw,
        COALESCE(raw_data->>'缺货数量', raw_data->>'stockout_qty', raw_data->>'Stockout Qty', raw_data->>'stockout') AS stockout_qty_raw,
        COALESCE(raw_data->>'补货点', raw_data->>'reorder_point', raw_data->>'Reorder Point') AS reorder_point_raw,
        COALESCE(raw_data->>'安全库存', raw_data->>'safety_stock', raw_data->>'Safety Stock') AS safety_stock_raw,
        COALESCE(raw_data->>'成本', raw_data->>'成本价', raw_data->>'cost', raw_data->>'Cost', raw_data->>'unit_cost') AS unit_cost_raw,
        COALESCE(raw_data->>'库存金额', raw_data->>'库存价值', raw_data->>'inventory_value', raw_data->>'Inventory Value') AS inventory_value_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_inventory
),
cleaned AS (
    SELECT
        platform_code,
        shop_id,
        data_domain,
        granularity,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        product_id,
        product_name,
        platform_sku,
        sku_id,
        product_sku,
        warehouse_name,
        warehouse_code,
        CASE WHEN available_stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(available_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS available_stock,
        CASE WHEN on_hand_stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(on_hand_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS on_hand_stock,
        CASE WHEN reserved_stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(reserved_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS reserved_stock,
        CASE WHEN in_transit_stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(in_transit_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS in_transit_stock,
        CASE WHEN stockout_qty_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stockout_qty_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS stockout_qty,
        CASE WHEN reorder_point_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(reorder_point_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS reorder_point,
        CASE WHEN safety_stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(safety_stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS safety_stock,
        CASE WHEN unit_cost_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unit_cost_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS unit_cost,
        CASE WHEN inventory_value_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(inventory_value_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS inventory_value,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM mapped
),
deduplicated AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, shop_id, data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM cleaned
)
SELECT
    platform_code,
    shop_id,
    data_domain,
    granularity,
    metric_date,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    product_id,
    product_name,
    platform_sku,
    sku_id,
    product_sku,
    warehouse_name,
    warehouse_code,
    COALESCE(available_stock, 0) AS available_stock,
    COALESCE(on_hand_stock, 0) AS on_hand_stock,
    COALESCE(reserved_stock, 0) AS reserved_stock,
    COALESCE(in_transit_stock, 0) AS in_transit_stock,
    COALESCE(stockout_qty, 0) AS stockout_qty,
    COALESCE(reorder_point, 0) AS reorder_point,
    COALESCE(safety_stock, 0) AS safety_stock,
    COALESCE(unit_cost, 0) AS unit_cost,
    COALESCE(inventory_value, 0) AS inventory_value,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
