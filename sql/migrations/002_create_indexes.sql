-- ============================================================================
-- Migration: 002_create_indexes
-- Description: 创建性能优化索引
-- Purpose: 提升Superset查询性能
-- Created: 2025-11-22
-- ============================================================================

-- ============================================================================
-- 1. fact_orders 表索引优化
-- ============================================================================

-- 联合索引：店铺 + 日期（最常用的查询组合）
CREATE INDEX IF NOT EXISTS idx_orders_shop_date 
ON fact_orders(shop_id, order_date_local);

-- 联合索引：平台 + 日期
CREATE INDEX IF NOT EXISTS idx_orders_platform_date 
ON fact_orders(platform_code, order_date_local);

-- 部分索引：已完成订单（只索引已完成的订单，节省空间）
CREATE INDEX IF NOT EXISTS idx_orders_completed 
ON fact_orders(order_status) 
WHERE order_status IN ('completed', 'delivered', 'finished');

-- 联合索引：买家 + 日期（复购分析）
CREATE INDEX IF NOT EXISTS idx_orders_buyer_date 
ON fact_orders(buyer_username, order_date_local);

-- B-tree索引：订单金额（范围查询）
CREATE INDEX IF NOT EXISTS idx_orders_amount 
ON fact_orders(total_amount);

-- B-tree索引：订单时间UTC（时间范围查询）
CREATE INDEX IF NOT EXISTS idx_orders_time_utc 
ON fact_orders(order_time_utc);

-- ============================================================================
-- 2. fact_product_metrics 表索引优化
-- ============================================================================

-- 联合索引：店铺 + 产品 + 日期
CREATE INDEX IF NOT EXISTS idx_product_metrics_shop_product_date 
ON fact_product_metrics(shop_id, product_id, metric_date);

-- 联合索引：平台 + 日期
CREATE INDEX IF NOT EXISTS idx_product_metrics_platform_date 
ON fact_product_metrics(platform_code, metric_date);

-- B-tree索引：销售额（排序查询）
CREATE INDEX IF NOT EXISTS idx_product_metrics_sales 
ON fact_product_metrics(sales_amount DESC);

-- B-tree索引：订单数（排序查询）
CREATE INDEX IF NOT EXISTS idx_product_metrics_orders 
ON fact_product_metrics(orders DESC);

-- ============================================================================
-- 3. fact_inventory 表索引优化
-- ============================================================================

-- 联合索引：店铺 + 产品 + 日期
CREATE INDEX IF NOT EXISTS idx_inventory_shop_product_date 
ON fact_inventory(shop_id, product_id, snapshot_date);

-- 部分索引：缺货产品（库存预警）
CREATE INDEX IF NOT EXISTS idx_inventory_out_of_stock 
ON fact_inventory(product_id, snapshot_date) 
WHERE available_stock = 0;

-- 部分索引：低库存产品（库存预警）
CREATE INDEX IF NOT EXISTS idx_inventory_low_stock 
ON fact_inventory(product_id, snapshot_date) 
WHERE available_stock < 10 AND available_stock > 0;

-- ============================================================================
-- 4. fact_expenses 表索引优化
-- ============================================================================

-- 联合索引：店铺 + 日期
CREATE INDEX IF NOT EXISTS idx_expenses_shop_date 
ON fact_expenses(shop_id, expense_date);

-- 索引：费用类型
CREATE INDEX IF NOT EXISTS idx_expenses_type 
ON fact_expenses(expense_type);

-- 索引：审批状态
CREATE INDEX IF NOT EXISTS idx_expenses_approval 
ON fact_expenses(approval_status) 
WHERE approval_status IS NOT NULL;

-- B-tree索引：金额（范围查询）
CREATE INDEX IF NOT EXISTS idx_expenses_amount 
ON fact_expenses(amount_cny DESC);

-- ============================================================================
-- 5. dim_products 表索引优化（如果有JSONB字段）
-- ============================================================================

-- GIN索引：JSONB字段（支持JSON查询）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'dim_products' 
        AND column_name = 'attributes' 
        AND data_type = 'jsonb'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_products_attributes 
        ON dim_products USING GIN(attributes);
    END IF;
END $$;

-- B-tree索引：品类
CREATE INDEX IF NOT EXISTS idx_products_category 
ON dim_products(category) WHERE category IS NOT NULL;

-- B-tree索引：品牌
CREATE INDEX IF NOT EXISTS idx_products_brand 
ON dim_products(brand) WHERE brand IS NOT NULL;

-- ============================================================================
-- 6. dim_shops 表索引优化
-- ============================================================================

-- 索引：平台
CREATE INDEX IF NOT EXISTS idx_shops_platform 
ON dim_shops(platform_code);

-- 索引：国家
CREATE INDEX IF NOT EXISTS idx_shops_country 
ON dim_shops(country) WHERE country IS NOT NULL;

-- 索引：状态
CREATE INDEX IF NOT EXISTS idx_shops_status 
ON dim_shops(status) WHERE status IS NOT NULL;

-- ============================================================================
-- 7. 物化视图索引（已在视图创建时定义，这里检查）
-- ============================================================================

-- mv_daily_sales_summary 的索引已在创建时定义
-- mv_monthly_shop_performance 的索引已在创建时定义
-- mv_product_sales_ranking 的索引已在创建时定义

-- ============================================================================
-- 8. 验证索引创建
-- ============================================================================

-- 查看fact_orders的所有索引
-- SELECT 
--     schemaname,
--     tablename,
--     indexname,
--     indexdef
-- FROM pg_indexes
-- WHERE tablename = 'fact_orders'
-- ORDER BY indexname;

-- 查看索引大小
-- SELECT
--     schemaname || '.' || tablename AS table_name,
--     indexname,
--     pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'public'
-- ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================================================
-- 9. 性能分析建议
-- ============================================================================

-- 执行VACUUM ANALYZE更新统计信息
-- VACUUM ANALYZE fact_orders;
-- VACUUM ANALYZE fact_product_metrics;
-- VACUUM ANALYZE fact_inventory;
-- VACUUM ANALYZE fact_expenses;

-- 查看最慢的查询
-- SELECT 
--     query,
--     calls,
--     total_time,
--     mean_time,
--     max_time
-- FROM pg_stat_statements
-- WHERE query LIKE '%fact_orders%' OR query LIKE '%fact_product_metrics%'
-- ORDER BY mean_time DESC
-- LIMIT 20;

COMMENT ON INDEX idx_orders_shop_date IS '订单表联合索引：店铺ID + 订单日期（最常用查询组合）';
COMMENT ON INDEX idx_orders_completed IS '订单表部分索引：已完成订单状态（节省空间）';
COMMENT ON INDEX idx_product_metrics_shop_product_date IS '产品指标表联合索引：店铺ID + 产品ID + 指标日期';
COMMENT ON INDEX idx_inventory_out_of_stock IS '库存表部分索引：缺货产品（库存预警）';

-- ============================================================================
-- 完成
-- ============================================================================
-- 索引创建完成！
-- 建议：执行VACUUM ANALYZE更新统计信息
-- 建议：定期监控慢查询日志并根据实际查询模式调整索引

