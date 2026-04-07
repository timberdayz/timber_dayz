CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.b_cost_shop_month AS
WITH monthly_base AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        shop_id,
        currency_code,
        SUM(paid_amount) AS gmv,
        SUM(purchase_amount) AS purchase_amount,
        SUM(warehouse_operation_fee) AS warehouse_operation_fee,
        SUM(shipping_fee) AS shipping_fee,
        SUM(promotion_fee) AS promotion_fee,
        SUM(platform_commission) AS platform_commission,
        SUM(platform_deduction_fee) AS platform_deduction_fee,
        SUM(platform_voucher) AS platform_voucher,
        SUM(platform_service_fee) AS platform_service_fee,
        SUM(platform_total_cost_itemized) AS platform_total_cost_itemized
    FROM semantic.fact_orders_atomic
    GROUP BY date_trunc('month', metric_date)::date, platform_code, shop_id, currency_code
),
costed AS (
    SELECT
        period_month,
        platform_code,
        shop_id,
        currency_code,
        platform_code || '|' || shop_id AS shop_key,
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
        (
            COALESCE(purchase_amount, 0)
            + COALESCE(warehouse_operation_fee, 0)
            + COALESCE(platform_total_cost_itemized, 0)
        ) AS total_cost_b
    FROM monthly_base
)
SELECT
    period_month,
    platform_code,
    shop_id,
    shop_key,
    currency_code,
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
    total_cost_b,
    (gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref,
    (gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref
FROM costed;
