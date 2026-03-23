CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_backlog_base AS
WITH sales_30d AS (
    SELECT
        platform_code,
        shop_id,
        platform_sku,
        product_sku,
        COALESCE(SUM(product_quantity), 0) AS sold_units_30d,
        COUNT(DISTINCT metric_date::date) AS active_days_30d
    FROM semantic.fact_orders_atomic
    WHERE metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
      AND metric_date::date <= CURRENT_DATE
    GROUP BY platform_code, shop_id, platform_sku, product_sku
)
SELECT
    i.snapshot_date,
    i.platform_code,
    i.shop_id,
    i.product_id,
    i.product_name,
    i.platform_sku,
    i.product_sku,
    i.warehouse_name,
    i.available_stock,
    i.on_hand_stock,
    i.inventory_value,
    COALESCE(
        ROUND(
            COALESCE(s.sold_units_30d, 0)::numeric / NULLIF(COALESCE(s.active_days_30d, 0), 0),
            2
        ),
        0
    ) AS daily_avg_sales,
    CASE
        WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
        THEN ROUND(
            COALESCE(i.available_stock, 0)::numeric /
            NULLIF(COALESCE(s.sold_units_30d, 0)::numeric / s.active_days_30d, 0),
            0
        )
        WHEN COALESCE(i.available_stock, 0) > 0
        THEN 9999
        ELSE 0
    END AS estimated_turnover_days
FROM mart.inventory_current i
LEFT JOIN sales_30d s
    ON i.platform_code = s.platform_code
   AND COALESCE(i.shop_id, '') = COALESCE(s.shop_id, '')
   AND COALESCE(i.platform_sku, '') = COALESCE(s.platform_sku, '')
   AND COALESCE(i.product_sku, '') = COALESCE(s.product_sku, '');
