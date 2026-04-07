CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.clearance_ranking_module AS
SELECT
    b.snapshot_date,
    b.platform_code,
    b.shop_id,
    b.product_id,
    b.product_name,
    b.platform_sku,
    b.product_sku,
    b.available_stock,
    b.inventory_value,
    0::numeric AS total_sales,
    0::numeric AS total_orders,
    b.daily_avg_sales,
    b.estimated_turnover_days,
    b.stagnant_snapshot_count,
    b.estimated_stagnant_days,
    b.risk_level,
    b.clearance_priority_score
FROM mart.inventory_backlog_base b;
