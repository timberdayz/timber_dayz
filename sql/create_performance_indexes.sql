-- =============================================
-- 西虹ERP系统 - PostgreSQL性能优化索引
-- v4.3.5 - 现代化ERP标准
-- =============================================

-- =============================================
-- 1. Catalog Files 表索引（文件查询核心）
-- =============================================

-- 组合索引：平台+数据域+粒度（最常用的筛选组合）
CREATE INDEX IF NOT EXISTS idx_catalog_platform_domain_granularity
ON catalog_files (source_platform, data_domain, granularity)
WHERE source_platform IS NOT NULL AND data_domain IS NOT NULL;

-- 时间范围索引（按日期查询）
CREATE INDEX IF NOT EXISTS idx_catalog_date_range
ON catalog_files (date_from, date_to)
WHERE date_from IS NOT NULL;

-- 店铺索引（按店铺查询）
CREATE INDEX IF NOT EXISTS idx_catalog_shop
ON catalog_files (shop_id)
WHERE shop_id IS NOT NULL;

-- 账号索引（按账号查询）
CREATE INDEX IF NOT EXISTS idx_catalog_account
ON catalog_files (account)
WHERE account IS NOT NULL;

-- 状态索引（待处理/需指派）
CREATE INDEX IF NOT EXISTS idx_catalog_status_time
ON catalog_files (status, first_seen_at DESC);

-- 文件哈希唯一索引（去重）
CREATE UNIQUE INDEX IF NOT EXISTS idx_catalog_file_hash
ON catalog_files (file_hash)
WHERE file_hash IS NOT NULL;

-- =============================================
-- 2. Fact Tables 索引（数据查询核心）
-- =============================================

-- 订单事实表
CREATE INDEX IF NOT EXISTS idx_fact_orders_platform_shop_date
ON fact_orders (platform_code, shop_id, order_date_local DESC);

CREATE INDEX IF NOT EXISTS idx_fact_orders_date
ON fact_orders (order_date_local DESC);

-- 产品指标事实表（根据实际存在的字段创建）
CREATE INDEX IF NOT EXISTS idx_fact_products_platform_shop_sku_date
ON fact_product_metrics (platform_code, shop_id, platform_sku, metric_date DESC);

-- 按日期查询
CREATE INDEX IF NOT EXISTS idx_fact_products_date
ON fact_product_metrics (metric_date DESC);

-- =============================================
-- 3. Dimension Tables 索引（关联查询）
-- =============================================

-- 店铺维度
CREATE INDEX IF NOT EXISTS idx_dim_shops_active
ON dim_shops (is_active, platform_code)
WHERE is_active = TRUE;

-- 产品维度
CREATE INDEX IF NOT EXISTS idx_dim_products_platform_sku
ON dim_products (platform_code, platform_sku);

-- =============================================
-- 4. 汇率表索引（货币转换）
-- =============================================

CREATE INDEX IF NOT EXISTS idx_currency_rates_date_from_to
ON dim_currency_rates (currency_from, currency_to, rate_date DESC);

-- =============================================
-- 执行报告
-- =============================================

SELECT '索引创建完成！' AS message;
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('catalog_files', 'fact_orders', 'fact_product_metrics', 'dim_shops', 'dim_products', 'dim_currency_rates')
ORDER BY tablename, indexname;

