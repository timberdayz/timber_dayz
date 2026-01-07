-- PostgreSQL 监控配置脚本（第三阶段优化）
--
-- 功能：
-- 1. 启用 pg_stat_statements 扩展（慢查询监控）
-- 2. 创建监控视图（Top 慢查询、连接状态、锁等待）
-- 3. 配置 Prometheus 导出器所需权限
--
-- 执行：在 PostgreSQL 容器中运行
-- psql -U postgres -d xihong_erp -f init_monitoring.sql

-- ==================== pg_stat_statements 配置 ====================

-- 创建扩展（需要 shared_preload_libraries='pg_stat_statements'）
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 配置参数（postgresql.conf）
-- shared_preload_libraries = 'pg_stat_statements'
-- pg_stat_statements.track = all
-- pg_stat_statements.max = 10000

-- ==================== 监控视图 ====================

-- 1. Top 10 慢查询视图
CREATE OR REPLACE VIEW v_top_slow_queries AS
SELECT 
    query,
    calls,
    ROUND(mean_exec_time::numeric, 2) AS mean_ms,
    ROUND(total_exec_time::numeric, 2) AS total_ms,
    ROUND((total_exec_time / sum(total_exec_time) OVER ()) * 100, 2) AS pct,
    rows,
    100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0) AS hit_ratio
FROM pg_stat_statements
WHERE mean_exec_time > 100  -- 超过100ms
ORDER BY mean_exec_time DESC
LIMIT 10;

COMMENT ON VIEW v_top_slow_queries IS 'Top 10 慢查询监控视图';


-- 2. 连接状态视图
CREATE OR REPLACE VIEW v_connection_status AS
SELECT 
    state,
    COUNT(*) AS count,
    MAX(EXTRACT(EPOCH FROM (now() - state_change))) AS max_idle_seconds
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;

COMMENT ON VIEW v_connection_status IS '数据库连接状态统计';


-- 3. 锁等待视图
CREATE OR REPLACE VIEW v_lock_waits AS
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS blocking_statement,
    blocked_activity.application_name AS blocked_application
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity 
    ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity 
    ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

COMMENT ON VIEW v_lock_waits IS '锁等待分析视图';


-- 4. 表膨胀监控视图
CREATE OR REPLACE VIEW v_table_bloat AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS indexes_size,
    n_live_tup AS live_tuples,
    n_dead_tup AS dead_tuples,
    ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_ratio
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_dead_tup DESC
LIMIT 20;

COMMENT ON VIEW v_table_bloat IS '表膨胀监控视图（需要 VACUUM 的表）';


-- ==================== Prometheus 导出器权限 ====================

-- 创建监控用户（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prometheus_exporter') THEN
        CREATE USER prometheus_exporter WITH PASSWORD 'prometheus_pass_2025';
    END IF;
END
$$;

-- 授予只读权限
GRANT CONNECT ON DATABASE xihong_erp TO prometheus_exporter;
GRANT USAGE ON SCHEMA public TO prometheus_exporter;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO prometheus_exporter;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO prometheus_exporter;

-- 授予监控视图权限
GRANT SELECT ON v_top_slow_queries TO prometheus_exporter;
GRANT SELECT ON v_connection_status TO prometheus_exporter;
GRANT SELECT ON v_lock_waits TO prometheus_exporter;
GRANT SELECT ON v_table_bloat TO prometheus_exporter;

-- 授予系统表权限
GRANT pg_monitor TO prometheus_exporter;


-- ==================== 便捷查询函数 ====================

-- 查看当前慢查询
CREATE OR REPLACE FUNCTION get_slow_queries(threshold_ms NUMERIC DEFAULT 1000)
RETURNS TABLE (
    query TEXT,
    calls BIGINT,
    mean_ms NUMERIC,
    total_ms NUMERIC,
    pct NUMERIC
) AS $$
SELECT 
    query,
    calls,
    ROUND(mean_exec_time::numeric, 2),
    ROUND(total_exec_time::numeric, 2),
    ROUND((total_exec_time / sum(total_exec_time) OVER ()) * 100, 2)
FROM pg_stat_statements
WHERE mean_exec_time > threshold_ms
ORDER BY mean_exec_time DESC
LIMIT 20;
$$ LANGUAGE SQL;

COMMENT ON FUNCTION get_slow_queries IS '获取慢查询列表（默认阈值1000ms）';


-- 获取表大小排名
CREATE OR REPLACE FUNCTION get_table_sizes()
RETURNS TABLE (
    table_name TEXT,
    total_size TEXT,
    table_size TEXT,
    indexes_size TEXT
) AS $$
SELECT 
    schemaname||'.'||tablename AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)),
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)),
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;
$$ LANGUAGE SQL;

COMMENT ON FUNCTION get_table_sizes IS '获取表大小排名（Top 20）';


GRANT EXECUTE ON FUNCTION get_slow_queries TO prometheus_exporter;
GRANT EXECUTE ON FUNCTION get_table_sizes TO prometheus_exporter;

-- ==================== 完成 ====================

\echo '监控配置完成！'
\echo '下一步：'
\echo '1. 修改 postgresql.conf 添加 shared_preload_libraries = pg_stat_statements'
\echo '2. 重启 PostgreSQL 服务'
\echo '3. 部署 postgres_exporter: docker run -e DATA_SOURCE_NAME=... -p 9187:9187 prometheuscommunity/postgres-exporter'
\echo '4. 配置 Prometheus 抓取 localhost:9187'
\echo '5. 导入 Grafana 看板（ID: 9628）'

