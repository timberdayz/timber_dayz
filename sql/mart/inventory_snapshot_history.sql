CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_history AS
SELECT
    metric_date::date AS snapshot_date,
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
    data_hash,
    NULL::integer AS source_file_id,
    ingest_timestamp
FROM semantic.fact_inventory_snapshot;
