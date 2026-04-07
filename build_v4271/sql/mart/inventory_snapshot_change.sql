CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_change AS
WITH ranked_history AS (
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
        inventory_value,
        source_file_id,
        ingest_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), COALESCE(platform_sku, ''), COALESCE(product_sku, ''), COALESCE(warehouse_name, '')
            ORDER BY snapshot_date DESC, ingest_timestamp DESC
        ) AS snapshot_rank
    FROM mart.inventory_snapshot_history
),
current_snapshot AS (
    SELECT * FROM ranked_history WHERE snapshot_rank = 1
),
previous_snapshot AS (
    SELECT * FROM ranked_history WHERE snapshot_rank = 2
)
SELECT
    c.snapshot_date,
    c.platform_code,
    c.shop_id,
    c.product_id,
    c.product_name,
    c.platform_sku,
    c.sku_id,
    c.product_sku,
    c.warehouse_name,
    c.warehouse_code,
    c.available_stock,
    c.on_hand_stock,
    c.inventory_value,
    c.source_file_id,
    c.ingest_timestamp,
    p.snapshot_date AS previous_snapshot_date,
    COALESCE(c.available_stock, 0) - COALESCE(p.available_stock, c.available_stock, 0) AS stock_delta,
    COALESCE(c.inventory_value, 0) - COALESCE(p.inventory_value, c.inventory_value, 0) AS inventory_value_delta,
    CASE
        WHEN p.snapshot_date IS NULL THEN 0
        ELSE GREATEST((c.snapshot_date - p.snapshot_date), 0)
    END AS snapshot_gap_days,
    CASE
        WHEN p.snapshot_date IS NULL THEN FALSE
        WHEN ABS(COALESCE(c.available_stock, 0) - COALESCE(p.available_stock, 0)) <= 0 THEN TRUE
        ELSE FALSE
    END AS is_stagnant,
    CASE
        WHEN p.snapshot_date IS NULL THEN 0
        WHEN ABS(COALESCE(c.available_stock, 0) - COALESCE(p.available_stock, 0)) <= 0 THEN GREATEST((c.snapshot_date - p.snapshot_date), 0)
        ELSE 0
    END AS estimated_stagnant_days,
    CASE
        WHEN p.snapshot_date IS NULL THEN 0
        WHEN ABS(COALESCE(c.available_stock, 0) - COALESCE(p.available_stock, 0)) <= 0 THEN 1
        ELSE 0
    END AS stagnant_snapshot_count
FROM current_snapshot c
LEFT JOIN previous_snapshot p
    ON c.platform_code = p.platform_code
   AND COALESCE(c.shop_id, '') = COALESCE(p.shop_id, '')
   AND COALESCE(c.platform_sku, '') = COALESCE(p.platform_sku, '')
   AND COALESCE(c.product_sku, '') = COALESCE(p.product_sku, '')
   AND COALESCE(c.warehouse_name, '') = COALESCE(p.warehouse_name, '');
