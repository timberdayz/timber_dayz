CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.inventory_backlog_summary_module AS
SELECT
    SUM(inventory_value) AS total_value,
    SUM(CASE WHEN estimated_turnover_days >= 30 THEN inventory_value ELSE 0 END) AS backlog_30d_value,
    SUM(CASE WHEN estimated_turnover_days >= 60 THEN inventory_value ELSE 0 END) AS backlog_60d_value,
    SUM(CASE WHEN estimated_turnover_days >= 90 THEN inventory_value ELSE 0 END) AS backlog_90d_value,
    SUM(available_stock) AS total_quantity,
    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_sku_count,
    COUNT(*) FILTER (WHERE risk_level = 'medium') AS medium_risk_sku_count,
    COUNT(*) FILTER (WHERE risk_level = 'low') AS low_risk_sku_count,
    AVG(clearance_priority_score) AS avg_clearance_priority_score,
    MAX(clearance_priority_score) AS max_clearance_priority_score
FROM mart.inventory_backlog_base;
