CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_overview_module AS
WITH aggregated AS (
    SELECT
        period_month,
        platform_code,
        currency_code,
        SUM(gmv) AS gmv,
        SUM(purchase_amount) AS purchase_amount,
        SUM(warehouse_operation_fee) AS warehouse_operation_fee,
        SUM(shipping_fee) AS shipping_fee,
        SUM(promotion_fee) AS promotion_fee,
        SUM(platform_commission) AS platform_commission,
        SUM(platform_deduction_fee) AS platform_deduction_fee,
        SUM(platform_voucher) AS platform_voucher,
        SUM(platform_service_fee) AS platform_service_fee,
        SUM(platform_total_cost_itemized) AS platform_total_cost_itemized,
        SUM(total_cost_b) AS total_cost_b
    FROM mart.b_cost_shop_month
    GROUP BY period_month, platform_code, currency_code
)
SELECT
    period_month,
    platform_code,
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
FROM aggregated;
