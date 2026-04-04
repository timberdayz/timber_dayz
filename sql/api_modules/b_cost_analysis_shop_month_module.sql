CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.b_cost_analysis_shop_month_module AS
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
    gross_margin_ref,
    net_margin_ref
FROM mart.b_cost_shop_month;
