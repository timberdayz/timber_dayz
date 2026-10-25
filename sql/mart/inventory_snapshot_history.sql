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
    NULLIF(to_jsonb(snapshot)->>'file_id', '')::integer AS source_file_id,
    ingest_timestamp,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    -- 行级时间戳：库存停滞时长的时间基准
    observed_at,
    created_at,
    -- 妙手仓库清单自带的滚动销量窗口（缺失为 NULL = 不可算）
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM semantic.fact_inventory_snapshot AS snapshot;
