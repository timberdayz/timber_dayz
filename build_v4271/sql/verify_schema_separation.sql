-- ===================================================
-- 验证Schema分离结果
-- ===================================================
-- 创建时间: 2025-11-26
-- 目的: 验证表是否已正确迁移到对应Schema

-- 1. 查看各Schema的表数量
SELECT 
    schemaname,
    COUNT(*) as table_count
FROM pg_tables
WHERE schemaname IN ('a_class', 'b_class', 'c_class', 'core', 'finance', 'public')
GROUP BY schemaname
ORDER BY schemaname;

-- 2. 查看各Schema的表列表
SELECT 
    schemaname,
    tablename
FROM pg_tables
WHERE schemaname IN ('a_class', 'b_class', 'c_class', 'core', 'finance')
ORDER BY schemaname, tablename;

-- 3. 检查是否还有Superset表残留
SELECT 
    'Superset表残留' as check_type,
    COUNT(*) as count
FROM pg_tables
WHERE schemaname = 'public'
AND (
    tablename LIKE 'ab_%' 
    OR tablename IN (
        'dashboards', 'slices', 'query', 'sql_metrics', 'table_columns', 
        'table_schema', 'tables', 'css_templates', 'dashboard_roles', 
        'dashboard_slices', 'dashboard_user', 'embedded_dashboards', 
        'favstar', 'filter_sets', 'key_value', 'keyvalue', 'logs',
        'rls_filter_roles', 'rls_filter_tables', 'row_level_security_filters',
        'slice_user', 'sqlatable_user', 'ssh_tunnels', 'tab_state', 
        'tag', 'tagged_object', 'url', 'user_attribute', 'dbs', 
        'annotation', 'annotation_layer', 'dynamic_plugin',
        'sl_columns', 'sl_dataset_columns', 'sl_dataset_tables', 
        'sl_dataset_users', 'sl_datasets', 'sl_table_columns', 'sl_tables'
    )
);

-- 4. 检查public schema中剩余的表
SELECT 
    'public schema剩余表' as check_type,
    tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

