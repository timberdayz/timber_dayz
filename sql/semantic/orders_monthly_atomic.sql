CREATE SCHEMA IF NOT EXISTS semantic;

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
