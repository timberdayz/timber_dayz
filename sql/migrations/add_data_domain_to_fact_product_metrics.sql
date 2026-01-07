-- ============================================================
-- 添加data_domain字段到fact_product_metrics表
-- 时间: 2025-11-05
-- 版本: v4.10.0
-- 说明: 支持inventory数据域，区分products域和inventory域数据
-- ============================================================

-- Step 1: 添加data_domain字段到fact_product_metrics表
ALTER TABLE fact_product_metrics 
ADD COLUMN IF NOT EXISTS data_domain VARCHAR(64) NULL DEFAULT 'products';

-- Step 2: 添加索引以支持数据域筛选
CREATE INDEX IF NOT EXISTS idx_fact_product_metrics_domain 
ON fact_product_metrics(data_domain);

-- Step 3: 更新现有数据: 默认设置为'products'(保持向后兼容)
UPDATE fact_product_metrics 
SET data_domain = 'products' 
WHERE data_domain IS NULL;

-- Step 4: 添加注释
COMMENT ON COLUMN fact_product_metrics.data_domain IS '数据域: products(商品销售表现)/inventory(库存快照)/analytics(流量分析)';

-- 完成提示
SELECT 'data_domain字段添加成功！' as status;

