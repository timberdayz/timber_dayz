CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序 → 先 DROP 再建。
DROP VIEW IF EXISTS api.business_overview_inventory_backlog_module;

CREATE OR REPLACE VIEW api.business_overview_inventory_backlog_module AS
-- API module currently exposes company-scope backlog rows.
-- 2026-10-24：判据换「距上次进货时长」；DOS / 风险等级 / 清理优先级等假指标已从源头删除。
SELECT
    snapshot_date,
    platform_code,
    shop_id,
    product_id,
    product_name,
    platform_sku,
    product_sku,
    warehouse_name,
    available_stock,
    on_hand_stock,
    inventory_value,
    stock_added_at,
    row_seen_at,
    row_written_at,
    days_since_restock,
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM mart.inventory_backlog_base;
