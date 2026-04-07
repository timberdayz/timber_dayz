-- ===================================================
-- 验证 Metabase Schema 配置的 SQL 查询
-- ===================================================
-- 在 PostgreSQL 中执行这些查询，验证数据库状态
-- ===================================================

-- 1. 检查所有 schema 中的 fact_raw_data_* 表
SELECT 
    table_schema,
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema = t.table_schema 
     AND table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_name LIKE 'fact_raw_data%'
ORDER BY table_schema, table_name;

-- 预期结果：应该返回 0 行（没有旧表）

-- 2. 检查 b_class schema 中的所有 fact_* 表
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema = 'b_class' 
     AND table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'b_class'
AND table_name LIKE 'fact_%'
ORDER BY table_name;

-- 预期结果：应该返回 26 行（按平台分表的表）

-- 3. 检查是否有视图引用旧表
SELECT 
    schemaname,
    viewname,
    LEFT(definition, 200) as definition_preview
FROM pg_views
WHERE definition LIKE '%fact_raw_data%'
ORDER BY schemaname, viewname;

-- 预期结果：应该返回 0 行（没有视图引用旧表）

-- 4. 检查是否有跨 schema 的重复表名
SELECT 
    table_name,
    COUNT(DISTINCT table_schema) as schema_count,
    STRING_AGG(DISTINCT table_schema, ', ' ORDER BY table_schema) as schemas
FROM information_schema.tables
WHERE table_schema IN ('public', 'b_class', 'a_class', 'c_class', 'core', 'finance')
AND table_name LIKE 'fact_%'
GROUP BY table_name
HAVING COUNT(DISTINCT table_schema) > 1
ORDER BY table_name;

-- 预期结果：应该返回 0 行（没有跨 schema 的重复表名）

-- 5. 统计各 schema 中的表数量
SELECT 
    table_schema,
    COUNT(*) as table_count,
    COUNT(CASE WHEN table_name LIKE 'fact_%' THEN 1 END) as fact_table_count
FROM information_schema.tables
WHERE table_schema IN ('public', 'b_class', 'a_class', 'c_class', 'core', 'finance')
GROUP BY table_schema
ORDER BY table_schema;

-- 预期结果：
-- b_class schema 应该有约 26 个 fact_* 表
-- public schema 不应该有 fact_raw_data_* 表

