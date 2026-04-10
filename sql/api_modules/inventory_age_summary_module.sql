CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.inventory_age_summary_module AS
WITH current_rows AS (
    SELECT
        bucket,
        current_qty,
        inventory_value
    FROM mart.inventory_age_current
),
totals AS (
    SELECT
        COUNT(*) AS total_sku_count,
        COALESCE(SUM(current_qty), 0) AS total_quantity,
        COALESCE(SUM(inventory_value), 0) AS total_inventory_value
    FROM current_rows
),
bucketed AS (
    SELECT
        bucket,
        COUNT(*) AS sku_count,
        COALESCE(SUM(current_qty), 0) AS quantity,
        COALESCE(SUM(inventory_value), 0) AS inventory_value
    FROM current_rows
    GROUP BY bucket
)
SELECT
    bucketed.bucket,
    bucketed.sku_count,
    bucketed.quantity,
    bucketed.inventory_value,
    totals.total_sku_count,
    totals.total_quantity,
    totals.total_inventory_value
FROM bucketed
CROSS JOIN totals;
