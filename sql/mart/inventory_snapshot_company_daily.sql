CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_company_daily AS
WITH normalized AS (
    SELECT
        snapshot_date,
        platform_code,
        COALESCE(
            NULLIF(BTRIM(platform_sku), ''),
            NULLIF(BTRIM(product_sku), ''),
            NULLIF(BTRIM(sku_id), ''),
            NULLIF(BTRIM(product_id), '')
        ) AS sku_key,
        NULLIF(BTRIM(platform_sku), '') AS platform_sku,
        NULLIF(BTRIM(product_sku), '') AS product_sku,
        NULLIF(BTRIM(sku_id), '') AS sku_id,
        NULLIF(BTRIM(product_id), '') AS product_id,
        NULLIF(BTRIM(product_name), '') AS product_name,
        NULLIF(BTRIM(warehouse_name), '') AS warehouse_name,
        COALESCE(available_stock, 0) AS available_stock,
        COALESCE(on_hand_stock, 0) AS on_hand_stock,
        COALESCE(inventory_value, 0) AS inventory_value,
        ingest_timestamp
    FROM mart.inventory_snapshot_history
),
deduplicated AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY
                snapshot_date,
                platform_code,
                sku_key,
                COALESCE(warehouse_name, '')
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM normalized
    WHERE sku_key IS NOT NULL
),
daily_latest AS (
    SELECT
        snapshot_date,
        platform_code,
        sku_key,
        platform_sku,
        product_sku,
        sku_id,
        product_id,
        product_name,
        warehouse_name,
        available_stock,
        on_hand_stock,
        inventory_value,
        ingest_timestamp
    FROM deduplicated
    WHERE rn = 1
)
SELECT
    snapshot_date,
    platform_code,
    sku_key,
    MAX(platform_sku) AS platform_sku,
    MAX(product_sku) AS product_sku,
    MAX(sku_id) AS sku_id,
    MAX(product_id) AS product_id,
    MAX(product_name) AS product_name,
    SUM(available_stock) AS available_qty,
    SUM(on_hand_stock) AS on_hand_qty,
    SUM(inventory_value) AS inventory_value,
    COUNT(DISTINCT warehouse_name) FILTER (WHERE warehouse_name IS NOT NULL) AS warehouse_count,
    MAX(ingest_timestamp) AS last_ingest_timestamp
FROM daily_latest
GROUP BY snapshot_date, platform_code, sku_key;
