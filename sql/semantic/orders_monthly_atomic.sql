CREATE SCHEMA IF NOT EXISTS semantic;

-- The canonical online path is the materialized view `semantic.fact_orders_monthly_atomic_mv`.
-- Deploy-time bootstrap is responsible for creating / refreshing the MV.
CREATE OR REPLACE VIEW semantic.fact_orders_monthly_atomic AS
SELECT
    metric_date,
    platform_code,
    shop_id,
    raw_shop_id,
    store_label_raw,
    resolved_shop_account_id,
    resolution_method,
    identity_source_value,
    order_id,
    paid_amount,
    product_quantity,
    profit,
    data_hash,
    ingest_timestamp
FROM semantic.fact_orders_monthly_atomic_mv;
