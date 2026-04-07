-- ============================================================
-- 更新fact_product_metrics表的唯一索引，添加data_domain字段
-- 时间: 2025-11-05
-- 版本: v4.10.0
-- 说明: 支持同一SKU在同一天有多个数据域的数据（products和inventory）
-- ============================================================

-- Step 1: 删除旧唯一索引
DROP INDEX IF EXISTS ix_product_unique_with_scope;

-- Step 2: 创建新唯一索引（包含data_domain）
CREATE UNIQUE INDEX ix_product_unique_with_scope 
ON fact_product_metrics(platform_code, shop_id, platform_sku, metric_date, granularity, sku_scope, data_domain);

-- Step 3: 添加索引注释
COMMENT ON INDEX ix_product_unique_with_scope IS '产品指标唯一索引（包含data_domain，支持同一SKU在同一天有多个数据域的数据）';

-- 完成提示
SELECT '唯一索引更新成功！' as status;

