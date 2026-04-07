# Metabase显示"没有结果"的解决方案

## 问题现象

在Metabase中查看表/视图时，显示"没有结果!"（0行数据），但表/视图已经同步到Metabase。

## 可能的原因

### 1. 数据库中确实没有数据（最常见）

**原因**：
- 视图/表已创建，但还没有导入业务数据
- 这是正常的，因为视图是基于基础表的，如果基础表没有数据，视图也会是空的

**验证方法**：
```sql
-- 检查视图是否有数据
SELECT COUNT(*) FROM view_shop_performance_wide;

-- 检查基础表是否有数据
SELECT COUNT(*) FROM fact_orders;
SELECT COUNT(*) FROM fact_product_metrics;
SELECT COUNT(*) FROM fact_inventory;
```

### 2. 视图定义有问题

**原因**：
- 视图SQL有错误
- 视图依赖的表不存在
- JOIN条件导致所有行被过滤

**验证方法**：
```sql
-- 测试视图是否可以查询
SELECT * FROM view_shop_performance_wide LIMIT 1;

-- 查看视图定义
\dv+ view_shop_performance_wide
```

### 3. Metabase同步问题

**原因**：
- Schema同步不完整
- 视图权限问题
- Metabase缓存问题

**解决方案**：
1. 重新同步Schema
2. 清除Metabase缓存
3. 检查数据库用户权限

## 解决方案

### 方案1：如果数据库中确实没有数据（正常情况）

**这是正常的！** 如果您的系统还没有导入业务数据，视图为空是预期的。

**下一步操作**：
1. **继续创建Dashboard结构**
   - 即使没有数据，也可以先创建Dashboard和Question
   - 当有数据后，Dashboard会自动显示数据

2. **测试Dashboard结构**
   - 创建Question时，Metabase会显示字段列表
   - 可以配置筛选器、图表类型等
   - 数据导入后，图表会自动更新

3. **准备测试数据**（可选）
   - 如果需要测试Dashboard，可以导入一些测试数据
   - 或者等待实际业务数据导入

### 方案2：如果有数据但Metabase查不到

**步骤1：检查数据库中的数据**
```bash
# 检查视图数据
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM view_shop_performance_wide;"

# 检查基础表数据
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM fact_orders;"
```

**步骤2：重新同步Metabase Schema**
1. 在Metabase中：数据 → 数据库 → XIHONG_ERP
2. 点击 "同步数据库schema now"
3. 等待同步完成

**步骤3：清除Metabase缓存**
1. 在Metabase中：Admin → Settings → Caching
2. 清除查询缓存

**步骤4：检查视图权限**
```sql
-- 确保erp_user有权限查询视图
GRANT SELECT ON view_shop_performance_wide TO erp_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO erp_user;
```

### 方案3：检查视图定义

**如果视图返回0行，但基础表有数据**：

1. **检查视图SQL**
   ```sql
   -- 查看视图定义
   SELECT pg_get_viewdef('view_shop_performance_wide', true);
   ```

2. **测试视图查询**
   ```sql
   -- 直接查询视图
   SELECT * FROM view_shop_performance_wide LIMIT 10;
   
   -- 检查是否有错误
   EXPLAIN SELECT * FROM view_shop_performance_wide;
   ```

3. **检查视图依赖**
   ```sql
   -- 查看视图依赖的表
   SELECT 
       dependent_ns.nspname as dependent_schema,
       dependent_view.relname as dependent_view,
       source_ns.nspname as source_schema,
       source_table.relname as source_table
   FROM pg_depend
   JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
   JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid
   JOIN pg_class as source_table ON pg_depend.refobjid = source_table.oid
   JOIN pg_namespace dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
   JOIN pg_namespace source_ns ON source_table.relnamespace = source_ns.oid
   WHERE dependent_view.relname = 'view_shop_performance_wide';
   ```

## 推荐操作流程

### 如果数据库中没有数据（正常情况）

1. **继续创建Dashboard结构**
   - ✅ 创建Dashboard："业务概览"
   - ✅ 创建Question（即使没有数据）
   - ✅ 配置筛选器和图表类型
   - ✅ 保存Dashboard

2. **验证Dashboard结构**
   - 检查字段是否正确显示
   - 检查筛选器配置是否正确
   - 检查图表类型是否合适

3. **等待数据导入**
   - 当业务数据导入后
   - Dashboard会自动显示数据
   - 无需重新配置

### 如果数据库中有数据但Metabase查不到

1. **验证数据库数据**
   ```bash
   docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM view_shop_performance_wide;"
   ```

2. **重新同步Schema**
   - 在Metabase UI中重新同步

3. **检查权限**
   - 确保数据库用户有SELECT权限

4. **清除缓存**
   - 清除Metabase查询缓存

## 测试数据准备（可选）

如果需要测试Dashboard，可以准备一些测试数据：

```sql
-- 示例：插入测试订单数据（需要根据实际表结构调整）
INSERT INTO fact_orders (order_id, shop_id, order_date_local, total_amount, ...)
VALUES 
  ('TEST001', 1, CURRENT_DATE, 100.00, ...),
  ('TEST002', 1, CURRENT_DATE - 1, 200.00, ...);
```

然后刷新物化视图：
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales_summary;
```

## 总结

**如果数据库中确实没有数据**：
- ✅ 这是正常的
- ✅ 可以继续创建Dashboard结构
- ✅ 数据导入后会自动显示

**如果数据库中有数据但Metabase查不到**：
- ⚠️ 需要检查同步、权限、缓存
- ⚠️ 按照方案2的步骤排查

## 下一步

1. **先检查数据库中是否有数据**（运行上面的SQL命令）
2. **根据结果选择对应的方案**
3. **继续创建Dashboard结构**（即使没有数据也可以创建）

