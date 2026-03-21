CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.clearance_ranking_module AS
WITH sales_window AS (
    SELECT
        platform_code,
        shop_id,
        platform_sku,
        product_id,
        product_name,
        COALESCE(SUM(sales_amount), 0) AS total_sales,
        COALESCE(SUM(order_count), 0) AS total_orders,
        COUNT(DISTINCT period_date) AS active_days
    FROM mart.product_day_kpi
    WHERE period_date >= CURRENT_DATE - INTERVAL '30 days'
      AND period_date <= CURRENT_DATE
    GROUP BY platform_code, shop_id, platform_sku, product_id, product_name
)
SELECT
    b.snapshot_date,
    b.platform_code,
    b.shop_id,
    COALESCE(b.product_id, s.product_id) AS product_id,
    COALESCE(b.product_name, s.product_name) AS product_name,
    b.platform_sku,
    b.product_sku,
    b.available_stock,
    b.inventory_value,
    COALESCE(s.total_sales, 0) AS total_sales,
    COALESCE(s.total_orders, 0) AS total_orders,
    b.daily_avg_sales,
    b.estimated_turnover_days
FROM mart.inventory_backlog_base b
LEFT JOIN sales_window s
    ON b.platform_code = s.platform_code
   AND COALESCE(b.shop_id, '') = COALESCE(s.shop_id, '')
   AND COALESCE(b.platform_sku, '') = COALESCE(s.platform_sku, '');
