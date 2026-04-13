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
top_two_history AS (
    SELECT *
    FROM ranked_history
    WHERE snapshot_rank <= 2
),
grouped_history AS (
    SELECT
        platform_code,
        shop_id,
        platform_sku,
        product_sku,
        warehouse_name,
        MAX(snapshot_date) FILTER (WHERE snapshot_rank = 1) AS snapshot_date,
        MAX(snapshot_date) FILTER (WHERE snapshot_rank = 2) AS previous_snapshot_date,
        MAX(product_id) FILTER (WHERE snapshot_rank = 1) AS product_id,
        MAX(product_name) FILTER (WHERE snapshot_rank = 1) AS product_name,
        MAX(sku_id) FILTER (WHERE snapshot_rank = 1) AS sku_id,
        MAX(warehouse_code) FILTER (WHERE snapshot_rank = 1) AS warehouse_code,
        MAX(available_stock) FILTER (WHERE snapshot_rank = 1) AS current_available_stock,
        MAX(available_stock) FILTER (WHERE snapshot_rank = 2) AS previous_available_stock,
        MAX(on_hand_stock) FILTER (WHERE snapshot_rank = 1) AS on_hand_stock,
        MAX(inventory_value) FILTER (WHERE snapshot_rank = 1) AS current_inventory_value,
        MAX(inventory_value) FILTER (WHERE snapshot_rank = 2) AS previous_inventory_value,
        MAX(source_file_id) FILTER (WHERE snapshot_rank = 1) AS source_file_id,
        MAX(ingest_timestamp) FILTER (WHERE snapshot_rank = 1) AS ingest_timestamp
    FROM top_two_history
    GROUP BY
        platform_code,
        shop_id,
        platform_sku,
        product_sku,
        warehouse_name
)
SELECT
    g.snapshot_date,
    g.platform_code,
    g.shop_id,
    g.product_id,
    g.product_name,
    g.platform_sku,
    g.sku_id,
    g.product_sku,
    g.warehouse_name,
    g.warehouse_code,
    g.current_available_stock AS available_stock,
    g.on_hand_stock,
    g.current_inventory_value AS inventory_value,
    g.source_file_id,
    g.ingest_timestamp,
    g.previous_snapshot_date,
    COALESCE(g.current_available_stock, 0) - COALESCE(g.previous_available_stock, g.current_available_stock, 0) AS stock_delta,
    COALESCE(g.current_inventory_value, 0) - COALESCE(g.previous_inventory_value, g.current_inventory_value, 0) AS inventory_value_delta,
    CASE
        WHEN g.previous_snapshot_date IS NULL THEN 0
        ELSE GREATEST((g.snapshot_date - g.previous_snapshot_date), 0)
    END AS snapshot_gap_days,
    CASE
        WHEN g.previous_snapshot_date IS NULL THEN FALSE
        WHEN ABS(COALESCE(g.current_available_stock, 0) - COALESCE(g.previous_available_stock, 0)) <= 0 THEN TRUE
        ELSE FALSE
    END AS is_stagnant,
    CASE
        WHEN g.previous_snapshot_date IS NULL THEN 0
        WHEN ABS(COALESCE(g.current_available_stock, 0) - COALESCE(g.previous_available_stock, 0)) <= 0 THEN GREATEST((g.snapshot_date - g.previous_snapshot_date), 0)
        ELSE 0
    END AS estimated_stagnant_days,
    CASE
        WHEN g.previous_snapshot_date IS NULL THEN 0
        WHEN ABS(COALESCE(g.current_available_stock, 0) - COALESCE(g.previous_available_stock, 0)) <= 0 THEN 1
        ELSE 0
    END AS stagnant_snapshot_count
FROM grouped_history g;
