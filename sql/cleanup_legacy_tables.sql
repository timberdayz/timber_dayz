-- 历史遗留表清理SQL脚本
-- 
-- 日期: 2026-01-11
-- 说明: 清理8张public schema的历史遗留表（全部为空，无业务代码引用）
--
-- 执行前请确保：
-- 1. 已备份数据库
-- 2. 已确认表为空（0行数据）
-- 3. 已确认无业务代码引用
--
-- 执行方式:
-- docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < sql/cleanup_legacy_tables.sql

-- 开始事务（可选，如果需要回滚）
-- BEGIN;

-- 清理 public schema 的历史遗留表
DROP TABLE IF EXISTS collection_tasks_backup CASCADE;
DROP TABLE IF EXISTS key_value CASCADE;
DROP TABLE IF EXISTS keyvalue CASCADE;
DROP TABLE IF EXISTS raw_ingestions CASCADE;
DROP TABLE IF EXISTS report_execution_log CASCADE;
DROP TABLE IF EXISTS report_recipient CASCADE;
DROP TABLE IF EXISTS report_schedule CASCADE;
DROP TABLE IF EXISTS report_schedule_user CASCADE;

-- 提交事务（如果使用了BEGIN）
-- COMMIT;

-- 验证清理结果
SELECT 
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
    AND table_name IN (
        'collection_tasks_backup',
        'key_value',
        'keyvalue',
        'raw_ingestions',
        'report_execution_log',
        'report_recipient',
        'report_schedule',
        'report_schedule_user'
    );

-- 如果查询结果为空，说明清理成功
-- 如果查询结果不为空，说明还有表未清理（可能是表名拼写错误）
