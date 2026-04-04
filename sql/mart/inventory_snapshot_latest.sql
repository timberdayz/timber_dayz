CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_latest AS
WITH ranked_inventory AS (
    SELECT
        snapshot_date,
        platform_code,
        shop_id,
        product_id,
        product_name,
        platform_sku,
        sku_id,
        product_sku,
        warehouse_name,
        warehouse_code,
        available_stock,
        on_hand_stock,
        reserved_stock,
        in_transit_stock,
        stockout_qty,
        reorder_point,
        safety_stock,
        unit_cost,
        inventory_value,
        currency_code,
        source_file_id,
        ingest_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), COALESCE(platform_sku, ''), COALESCE(product_sku, ''), COALESCE(warehouse_name, '')
            ORDER BY snapshot_date DESC, ingest_timestamp DESC
        ) AS rn
    FROM mart.inventory_snapshot_history
)
SELECT
    snapshot_date,
    platform_code,
    shop_id,
    product_id,
    product_name,
    platform_sku,
    sku_id,
    product_sku,
    warehouse_name,
    warehouse_code,
    available_stock,
    on_hand_stock,
    reserved_stock,
    in_transit_stock,
    stockout_qty,
    reorder_point,
    safety_stock,
    unit_cost,
    inventory_value,
    currency_code,
    source_file_id,
    ingest_timestamp
FROM ranked_inventory
WHERE rn = 1;
