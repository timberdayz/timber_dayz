CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_latest AS
-- Current runtime scope is company-level inventory.
-- shop_id is intentionally excluded from the grouping key for now and is
-- returned as NULL only to preserve a future shop-scope interface surface.
WITH company_daily AS (
    SELECT
        snapshot_date,
        platform_code,
        product_id,
        product_name,
        platform_sku,
        sku_id,
        product_sku,
        warehouse_name,
        warehouse_code,
        SUM(available_stock) AS available_stock,
        SUM(on_hand_stock) AS on_hand_stock,
        SUM(reserved_stock) AS reserved_stock,
        SUM(in_transit_stock) AS in_transit_stock,
        SUM(stockout_qty) AS stockout_qty,
        MAX(reorder_point) AS reorder_point,
        MAX(safety_stock) AS safety_stock,
        MAX(unit_cost) AS unit_cost,
        SUM(inventory_value) AS inventory_value,
        MAX(currency_code)::varchar(3) AS currency_code,
        MAX(source_file_id) AS source_file_id,
        MAX(ingest_timestamp) AS ingest_timestamp
    FROM mart.inventory_snapshot_history
    GROUP BY
        snapshot_date,
        platform_code,
        platform_sku,
        product_sku,
        warehouse_name,
        product_id,
        product_name,
        sku_id,
        warehouse_code
),
ranked_inventory AS (
    SELECT
        snapshot_date,
        platform_code,
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
            PARTITION BY platform_code, COALESCE(platform_sku, ''), COALESCE(product_sku, ''), COALESCE(warehouse_name, '')
            ORDER BY snapshot_date DESC, ingest_timestamp DESC
        ) AS rn
    FROM company_daily
)
SELECT
    snapshot_date,
    platform_code,
    NULL::text AS shop_id,
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
