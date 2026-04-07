CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_inventory_backlog_module AS
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
    daily_avg_sales,
    estimated_turnover_days,
    stock_delta,
    inventory_value_delta,
    is_stagnant,
    snapshot_gap_days,
    estimated_stagnant_days,
    stagnant_snapshot_count,
    risk_level,
    clearance_priority_score
FROM mart.inventory_backlog_base;
