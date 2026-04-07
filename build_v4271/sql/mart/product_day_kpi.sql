CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.product_day_kpi AS
SELECT
    metric_date::date AS period_date,
    platform_code,
    shop_id,
    platform_sku,
    product_id,
    product_name,
    COALESCE(SUM(sales_amount), 0) AS sales_amount,
    COALESCE(SUM(order_count), 0) AS order_count,
    COALESCE(SUM(sales_volume), 0) AS sales_volume,
    COALESCE(SUM(page_views), 0) AS page_views,
    COALESCE(SUM(unique_visitors), 0) AS unique_visitors,
    COALESCE(SUM(impressions), 0) AS impressions,
    COALESCE(SUM(clicks), 0) AS clicks,
    CASE
        WHEN COALESCE(SUM(unique_visitors), 0) > 0
        THEN ROUND(COALESCE(SUM(order_count), 0)::numeric * 100.0 / SUM(unique_visitors), 2)
        ELSE 0
    END AS conversion_rate
FROM semantic.fact_products_atomic
WHERE granularity = 'daily'
GROUP BY metric_date::date, platform_code, shop_id, platform_sku, product_id, product_name;
