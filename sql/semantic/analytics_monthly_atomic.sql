CREATE SCHEMA IF NOT EXISTS semantic;

DROP VIEW IF EXISTS semantic.fact_analytics_monthly_atomic CASCADE;

CREATE OR REPLACE VIEW semantic.fact_analytics_monthly_atomic AS
SELECT
    metric_date,
    platform_code,
    shop_id,
    raw_shop_id,
    store_label_raw,
    resolved_shop_account_id,
    resolution_method,
    identity_source_value,
    visitor_count,
    product_visitor_count,
    page_views,
    order_count,
    sku_order_count,
    gmv,
    total_transaction_amount,
    data_hash,
    ingest_timestamp
FROM semantic.fact_analytics_monthly_atomic_mv;
