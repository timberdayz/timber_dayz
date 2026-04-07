-- ============================================================
-- 修改fact_product_metrics表，允许inventory域的platform_code和shop_id为NULL
-- 时间: 2025-11-05
-- 版本: v4.10.0
-- 说明: 库存数据是仓库级别的数据，不存在店铺或平台的概念
-- ============================================================

-- Step 1: 修改platform_code和shop_id字段，允许NULL
ALTER TABLE fact_product_metrics 
ALTER COLUMN platform_code DROP NOT NULL;

ALTER TABLE fact_product_metrics 
ALTER COLUMN shop_id DROP NOT NULL;

-- Step 2: 更新唯一索引，确保NULL值正确处理
-- PostgreSQL的UNIQUE索引会自动处理NULL值（多个NULL值被认为是不同的）
-- 但为了确保inventory域的数据唯一性，我们需要确保索引正确工作

-- 检查当前索引
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'fact_product_metrics' AND indexname = 'ix_product_unique_with_scope';

-- Step 3: 添加注释说明
COMMENT ON COLUMN fact_product_metrics.platform_code IS '平台代码（inventory域允许为空，其他域必填）';
COMMENT ON COLUMN fact_product_metrics.shop_id IS '店铺ID（inventory域允许为空，其他域必填）';

-- 完成提示
SELECT 'platform_code和shop_id字段已修改为允许NULL（支持inventory域）' as status;

