-- =====================================================
-- 数据库迁移脚本：增加粒度和时间维度字段
-- 版本：v1.0.0
-- 创建日期：2025-01-26
-- 作者：AI 专家级数据工程师
-- 目的：支持智能字段映射系统的粒度感知功能
-- =====================================================

-- =====================================================
-- 1. 为 fact_product_metrics 表增加粒度相关字段
-- =====================================================

-- 检查字段是否已存在（SQLite不支持IF NOT EXISTS，需要手动检查）
-- 如果字段已存在，此脚本会报错，请忽略

-- 1.1 增加 granularity 字段
-- 用途：存储时间粒度（'daily', 'weekly', 'monthly', 'snapshot'）
ALTER TABLE fact_product_metrics 
ADD COLUMN granularity VARCHAR(20) DEFAULT 'daily';

-- 1.2 增加 time_dimension 字段
-- 用途：存储时间维度值
--   - 对于daily粒度：可能是 '14' (小时), '2025-09-22' (日期)
--   - 对于weekly粒度：'2025-09-22' (周内某天)
--   - 对于monthly粒度：'2025-09-22' (月内某天)
--   - 对于snapshot粒度：NULL 或 'snapshot'
ALTER TABLE fact_product_metrics 
ADD COLUMN time_dimension VARCHAR(50) DEFAULT NULL;

-- =====================================================
-- 2. 为现有数据设置默认值（向后兼容）
-- =====================================================

-- 2.1 为现有数据设置默认粒度为 'daily'
UPDATE fact_product_metrics 
SET granularity = 'daily' 
WHERE granularity IS NULL;

-- 2.2 为现有数据设置 time_dimension 为 metric_date
-- 假设现有数据都是日粒度，time_dimension 就是日期本身
UPDATE fact_product_metrics 
SET time_dimension = DATE(metric_date) 
WHERE time_dimension IS NULL;

-- =====================================================
-- 3. 创建索引以提高查询性能
-- =====================================================

-- 3.1 为 granularity 字段创建索引
CREATE INDEX IF NOT EXISTS idx_product_metrics_granularity 
ON fact_product_metrics(granularity);

-- 3.2 为 time_dimension 字段创建索引
CREATE INDEX IF NOT EXISTS idx_product_metrics_time_dimension 
ON fact_product_metrics(time_dimension);

-- 3.3 创建复合索引（平台+店铺+日期+粒度+时间维度）
CREATE INDEX IF NOT EXISTS idx_product_metrics_composite 
ON fact_product_metrics(platform_code, shop_id, metric_date, granularity, time_dimension);

-- =====================================================
-- 4. 验证迁移结果
-- =====================================================

-- 4.1 检查表结构
-- SELECT sql FROM sqlite_master WHERE type='table' AND name='fact_product_metrics';

-- 4.2 检查数据完整性
-- SELECT 
--     COUNT(*) as total_records,
--     COUNT(DISTINCT granularity) as distinct_granularities,
--     COUNT(CASE WHEN granularity IS NULL THEN 1 END) as null_granularities,
--     COUNT(CASE WHEN time_dimension IS NULL THEN 1 END) as null_time_dimensions
-- FROM fact_product_metrics;

-- 4.3 检查粒度分布
-- SELECT 
--     granularity, 
--     COUNT(*) as count 
-- FROM fact_product_metrics 
-- GROUP BY granularity;

-- =====================================================
-- 5. 回滚脚本（如果需要）
-- =====================================================

-- 注意：SQLite不支持 DROP COLUMN，如果需要回滚，需要：
-- 1. 创建新表（不包含新字段）
-- 2. 复制数据
-- 3. 删除旧表
-- 4. 重命名新表

-- 回滚步骤（仅供参考，请谨慎使用）：
/*
BEGIN TRANSACTION;

-- 创建临时表（不包含新字段）
CREATE TABLE fact_product_metrics_backup AS 
SELECT 
    platform_code,
    shop_id,
    platform_sku,
    metric_date,
    metric_type,
    metric_value,
    currency_code,
    data_hash,
    created_at,
    updated_at
FROM fact_product_metrics;

-- 删除原表
DROP TABLE fact_product_metrics;

-- 重命名临时表
ALTER TABLE fact_product_metrics_backup RENAME TO fact_product_metrics;

-- 重新创建索引
CREATE INDEX idx_product_metrics_platform ON fact_product_metrics(platform_code);
CREATE INDEX idx_product_metrics_shop ON fact_product_metrics(shop_id);
CREATE INDEX idx_product_metrics_sku ON fact_product_metrics(platform_sku);
CREATE INDEX idx_product_metrics_date ON fact_product_metrics(metric_date);
CREATE INDEX idx_product_metrics_type ON fact_product_metrics(metric_type);

COMMIT;
*/

-- =====================================================
-- 6. 使用说明
-- =====================================================

-- 6.1 执行迁移脚本
-- sqlite3 data/xihong_erp.db < migrations/add_granularity_fields.sql

-- 6.2 验证迁移结果
-- sqlite3 data/xihong_erp.db "PRAGMA table_info(fact_product_metrics);"

-- 6.3 查看粒度分布
-- sqlite3 data/xihong_erp.db "SELECT granularity, COUNT(*) FROM fact_product_metrics GROUP BY granularity;"

-- =====================================================
-- 7. 注意事项
-- =====================================================

-- 7.1 备份数据库
-- 在执行迁移前，请务必备份数据库文件：
-- cp data/xihong_erp.db data/xihong_erp.db.backup_20250126

-- 7.2 测试环境验证
-- 建议先在测试环境执行迁移，验证无误后再在生产环境执行

-- 7.3 数据一致性
-- 迁移后，请检查数据一致性，确保所有记录都有正确的 granularity 和 time_dimension 值

-- 7.4 应用程序兼容性
-- 确保应用程序代码已更新，能够正确处理新增的字段

-- =====================================================
-- 迁移脚本结束
-- =====================================================

