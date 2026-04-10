CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.inventory_age_list_module AS
SELECT
    snapshot_date,
    platform_code,
    sku_key,
    platform_sku,
    product_sku,
    sku_id,
    product_id,
    product_name,
    current_qty,
    previous_qty,
    qty_delta,
    age_anchor_date,
    age_days,
    bucket,
    reset_reason,
    on_hand_qty,
    inventory_value,
    warehouse_count,
    last_ingest_timestamp
FROM mart.inventory_age_current;
