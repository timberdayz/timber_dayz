CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_current AS
-- 2026-10-24 改造：排序键从 metric_date 改成 observed_at（行级「最后修改时间」）。
-- 增量模式下未被采到的行保留旧 observed_at —— 它们的库存本来就是准的，
-- 不需要靠批次日期排序来「刷新」。
WITH ranked_inventory AS (
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
        observed_at,
        created_at,
        checklist_sales_7d,
        checklist_sales_30d,
        checklist_sales_60d,
        checklist_sales_90d,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), COALESCE(platform_sku, ''), COALESCE(product_sku, '')
            ORDER BY observed_at DESC NULLS LAST, ingest_timestamp DESC
        ) AS rn
    FROM semantic.fact_inventory_snapshot
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
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    observed_at,
    created_at,
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM ranked_inventory
WHERE rn = 1;
