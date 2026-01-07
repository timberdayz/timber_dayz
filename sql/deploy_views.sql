-- ============================================================================
-- PostgreSQL视图层部署脚本
-- Description: 一键部署所有视图、物化视图、函数和表
-- Purpose: 支持DSS架构的PostgreSQL视图层
-- Created: 2025-11-22
-- Usage: psql -h localhost -U your_user -d xihong_erp -f sql/deploy_views.sql
-- ============================================================================

\echo '========================================='
\echo 'PostgreSQL DSS视图层部署脚本'
\echo '版本: 1.0.0'
\echo '日期: 2025-11-22'
\echo '========================================='
\echo ''

-- 设置客户端编码
SET client_encoding = 'UTF8';

-- 开始事务
BEGIN;

\echo '>>> Step 1/6: 创建A类数据表（用户配置数据）...'
\i sql/migrations/001_create_a_class_data_tables.sql

\echo ''
\echo '>>> Step 2/6: 创建Layer 1 - 原子视图（6个）...'
\i sql/views/atomic/view_orders_atomic.sql
\i sql/views/atomic/view_product_metrics_atomic.sql
\i sql/views/atomic/view_inventory_atomic.sql
\i sql/views/atomic/view_expenses_atomic.sql
\i sql/views/atomic/view_targets_atomic.sql
\i sql/views/atomic/view_campaigns_atomic.sql

\echo ''
\echo '>>> Step 3/6: 创建Layer 2 - 聚合物化视图（3个）...'
\i sql/views/aggregate/mv_daily_sales_summary.sql
\i sql/views/aggregate/mv_monthly_shop_performance.sql
\i sql/views/aggregate/mv_product_sales_ranking.sql

\echo ''
\echo '>>> Step 4/6: 创建Layer 3 - 宽表视图（2个）...'
\i sql/views/wide/view_shop_performance_wide.sql
\i sql/views/wide/view_product_performance_wide.sql

\echo ''
\echo '>>> Step 5/6: 创建刷新函数和日志表...'
\i sql/functions/refresh_superset_materialized_views.sql

\echo ''
\echo '>>> Step 6/6: 创建性能优化索引...'
\i sql/migrations/002_create_indexes.sql

-- 提交事务
COMMIT;

\echo ''
\echo '========================================='
\echo '部署完成！'
\echo '========================================='
\echo ''
\echo '已创建的对象：'
\echo '- A类数据表: 3张 (sales_targets, campaign_targets, operating_costs)'
\echo '- Layer 1原子视图: 6个'
\echo '- Layer 2聚合物化视图: 3个'
\echo '- Layer 3宽表视图: 2个'
\echo '- 刷新函数: 1个'
\echo '- 性能索引: 20+个'
\echo ''
\echo '下一步操作：'
\echo '1. 执行 VACUUM ANALYZE; 更新统计信息'
\echo '2. 测试视图查询: SELECT * FROM view_orders_atomic LIMIT 10;'
\echo '3. 刷新物化视图: SELECT * FROM refresh_superset_materialized_views(NULL, FALSE);'
\echo '4. 查看刷新日志: SELECT * FROM mv_refresh_log ORDER BY start_time DESC LIMIT 10;'
\echo ''
\echo '文档位置: sql/README.md'
\echo '========================================='

