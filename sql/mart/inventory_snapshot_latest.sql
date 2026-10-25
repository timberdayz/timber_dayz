CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_snapshot_latest AS
-- Current runtime scope is company-level inventory.
-- shop_id is intentionally excluded from the grouping key for now and is
-- returned as NULL only to preserve a future shop-scope interface surface.
--
-- 2026-10-24 改造（增量模式）：
--   1. 排序键从 snapshot_date 改成 observed_at（行级「最后修改时间」）。
--      增量采集只会写回被变动过的行，其余行保留旧 observed_at；
--      按 observed_at 取最新 = 「该 SKU×仓 最近一次变动时的状态」，
--      未被采到的行库存依然是准的。
--   2. 先按 (snapshot_date, SKU×仓) 取最新一行再聚合 —— 增量模式下同一天
--      可能落多批，直接 SUM 会把同一行重复累加。
WITH ranked_rows AS (
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
        observed_at,
        created_at,
        checklist_sales_7d,
        checklist_sales_30d,
        checklist_sales_60d,
        checklist_sales_90d,
        currency_code,
        source_file_id,
        ingest_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY
                snapshot_date,
                platform_code,
                COALESCE(platform_sku, ''),
                COALESCE(product_sku, ''),
                COALESCE(warehouse_name, '')
            ORDER BY observed_at DESC NULLS LAST, ingest_timestamp DESC
        ) AS day_rn
    FROM mart.inventory_snapshot_history
),
company_daily AS (
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
        observed_at,
        created_at,
        checklist_sales_7d,
        checklist_sales_30d,
        checklist_sales_60d,
        checklist_sales_90d,
        currency_code,
        source_file_id,
        ingest_timestamp
    FROM ranked_rows
    WHERE day_rn = 1
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
        observed_at,
        created_at,
        checklist_sales_7d,
        checklist_sales_30d,
        checklist_sales_60d,
        checklist_sales_90d,
        currency_code,
        source_file_id,
        ingest_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(platform_sku, ''), COALESCE(product_sku, ''), COALESCE(warehouse_name, '')
            ORDER BY observed_at DESC NULLS LAST, ingest_timestamp DESC
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
    ingest_timestamp,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    observed_at,
    created_at,
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM ranked_inventory
WHERE rn = 1;
