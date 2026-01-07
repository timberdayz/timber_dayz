-- ===================================================
-- 删除Superset系统表（47张）
-- ===================================================
-- 创建时间: 2025-11-26
-- 目的: 清理不再使用的Superset系统表
-- 注意: 删除前请备份数据库！

-- 1. 删除Superset核心表（8张）
DROP TABLE IF EXISTS ab_permission CASCADE;
DROP TABLE IF EXISTS ab_permission_view CASCADE;
DROP TABLE IF EXISTS ab_permission_view_role CASCADE;
DROP TABLE IF EXISTS ab_register_user CASCADE;
DROP TABLE IF EXISTS ab_role CASCADE;
DROP TABLE IF EXISTS ab_user CASCADE;
DROP TABLE IF EXISTS ab_user_role CASCADE;
DROP TABLE IF EXISTS ab_view_menu CASCADE;

-- 2. 删除Superset其他表（39张）
DROP TABLE IF EXISTS annotation CASCADE;
DROP TABLE IF EXISTS annotation_layer CASCADE;
DROP TABLE IF EXISTS css_templates CASCADE;
DROP TABLE IF EXISTS dashboard_roles CASCADE;
DROP TABLE IF EXISTS dashboard_slices CASCADE;
DROP TABLE IF EXISTS dashboard_user CASCADE;
DROP TABLE IF EXISTS dashboards CASCADE;
DROP TABLE IF EXISTS dbs CASCADE;
DROP TABLE IF EXISTS dynamic_plugin CASCADE;
DROP TABLE IF EXISTS embedded_dashboards CASCADE;
DROP TABLE IF EXISTS favstar CASCADE;
DROP TABLE IF EXISTS filter_sets CASCADE;
DROP TABLE IF EXISTS key_value CASCADE;
DROP TABLE IF EXISTS keyvalue CASCADE;
DROP TABLE IF EXISTS logs CASCADE;
DROP TABLE IF EXISTS query CASCADE;
DROP TABLE IF EXISTS rls_filter_roles CASCADE;
DROP TABLE IF EXISTS rls_filter_tables CASCADE;
DROP TABLE IF EXISTS row_level_security_filters CASCADE;
DROP TABLE IF EXISTS sl_columns CASCADE;
DROP TABLE IF EXISTS sl_dataset_columns CASCADE;
DROP TABLE IF EXISTS sl_dataset_tables CASCADE;
DROP TABLE IF EXISTS sl_dataset_users CASCADE;
DROP TABLE IF EXISTS sl_datasets CASCADE;
DROP TABLE IF EXISTS sl_table_columns CASCADE;
DROP TABLE IF EXISTS sl_tables CASCADE;
DROP TABLE IF EXISTS slice_user CASCADE;
DROP TABLE IF EXISTS slices CASCADE;
DROP TABLE IF EXISTS sql_metrics CASCADE;
DROP TABLE IF EXISTS sqlatable_user CASCADE;
DROP TABLE IF EXISTS ssh_tunnels CASCADE;
DROP TABLE IF EXISTS tab_state CASCADE;
DROP TABLE IF EXISTS table_columns CASCADE;
DROP TABLE IF EXISTS table_schema CASCADE;
DROP TABLE IF EXISTS tables CASCADE;
DROP TABLE IF EXISTS tag CASCADE;
DROP TABLE IF EXISTS tagged_object CASCADE;
DROP TABLE IF EXISTS url CASCADE;
DROP TABLE IF EXISTS user_attribute CASCADE;

-- 验证：检查是否还有Superset表残留
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND (table_name LIKE 'ab_%' OR table_name IN ('dashboards', 'slices', 'query', 'sql_metrics', 'table_columns', 'table_schema', 'tables', 'css_templates', 'dashboard_roles', 'dashboard_slices', 'dashboard_user', 'embedded_dashboards', 'favstar', 'filter_sets', 'key_value', 'keyvalue', 'logs', 'rls_filter_roles', 'rls_filter_tables', 'row_level_security_filters', 'slice_user', 'sqlatable_user', 'ssh_tunnels', 'tab_state', 'tag', 'tagged_object', 'url', 'user_attribute', 'dbs', 'annotation', 'annotation_layer', 'dynamic_plugin', 'sl_columns', 'sl_dataset_columns', 'sl_dataset_tables', 'sl_dataset_users', 'sl_datasets', 'sl_table_columns', 'sl_tables'));

