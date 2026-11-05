CREATE SCHEMA IF NOT EXISTS mart;

-- 数据源：物化视图 `semantic.fact_products_atomic_mv`。
-- 口径与读普通视图 `semantic.fact_products_atomic` **完全一致** ——
-- 物化视图的正文就是普通视图的正文（SELECT *），只是把「每行跑一次店铺别名
-- 解析」从请求路径搬到刷新路径。
-- 生产实测（2026-11-05）：读普通视图时本视图要 **14.1 秒**（强制全列实算），
-- 商品经营分析页（performance_management）因此是秒级慢；读物化副本后是毫秒级。
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
FROM semantic.fact_products_atomic_mv
WHERE granularity = 'daily'
GROUP BY metric_date::date, platform_code, shop_id, platform_sku, product_id, product_name;
