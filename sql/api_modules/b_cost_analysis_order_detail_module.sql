CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_order_detail_module AS
WITH base AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        platform_code || '|' || shop_id AS shop_key,
        currency_code,
        order_id,
        order_status,
        order_time,
        order_date,
        order_original_amount,
        product_id,
        platform_sku,
        sku_id,
        product_sku,
        product_name,
        paid_amount AS gmv,
        purchase_amount,
        warehouse_operation_fee,
        shipping_fee,
        promotion_fee,
        platform_commission,
        platform_deduction_fee,
        platform_voucher,
        platform_service_fee,
        platform_total_cost_itemized,
        platform_total_cost_derived,
        (
            COALESCE(purchase_amount, 0)
            + COALESCE(warehouse_operation_fee, 0)
            + COALESCE(platform_total_cost_itemized, 0)
        ) AS total_cost_b
    FROM semantic.fact_orders_atomic
)
SELECT
    period_month,
    platform_code,
    shop_id,
    shop_key,
    currency_code,
    order_id,
    order_status,
    COALESCE(order_time, order_date::timestamp) AS order_time,
    order_date,
    order_original_amount,
    product_id,
    platform_sku,
    sku_id,
    product_sku,
    product_name,
    gmv,
    purchase_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    platform_total_cost_itemized,
    platform_total_cost_derived,
    total_cost_b,
    (gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref,
    (gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref
FROM base;
