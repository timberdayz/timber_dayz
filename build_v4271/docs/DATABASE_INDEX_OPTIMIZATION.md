# 数据库索引优化指南

**创建时间**: 2025-01-31  
**状态**: ✅ 已完成  
**目的**: 记录数据库索引优化策略和实施情况

---

## 📋 概述

本文档记录数据库索引优化策略，确保查询性能达到企业级ERP标准。

---

## ✅ 已实施的索引

### 1. Fact Orders表索引

**位置**: `modules/core/db/schema.py` (FactOrder类)

**已创建索引**:
- ✅ `ix_fact_orders_plat_shop_date`: `(platform_code, shop_id, order_date_local)`
- ✅ `ix_fact_orders_status`: `(platform_code, shop_id, order_status)`
- ✅ `ix_fact_orders_file_id`: `(file_id)`

**用途**:
- 平台+店铺+日期查询（最常用）
- 订单状态筛选
- 文件关联查询

### 2. Fact Order Items表索引

**位置**: `modules/core/db/schema.py` (FactOrderItem类)

**已创建索引**:
- ✅ `ix_fact_items_plat_shop_order`: `(platform_code, shop_id, order_id)`
- ✅ `ix_fact_items_plat_shop_sku`: `(platform_code, shop_id, platform_sku)`
- ✅ `ix_fact_items_product_id`: `(product_id)` (v4.12.0新增)

**用途**:
- 订单明细查询
- SKU查询
- 产品ID查询（冗余字段优化）

### 3. Fact Product Metrics表索引

**位置**: `modules/core/db/schema.py` (FactProductMetric类)

**已创建索引**:
- ✅ 主键字段自动索引: `platform_code`, `shop_id`, `platform_sku`, `metric_date`
- ✅ `granularity`: 粒度查询
- ✅ `sku_scope`: SKU粒度查询
- ✅ `data_domain`: 数据域查询
- ✅ `parent_platform_sku`: 父级SKU查询
- ✅ `source_catalog_id`: 来源文件查询

**用途**:
- 商品指标查询（多维度）
- 粒度筛选
- 数据域筛选

### 4. Catalog Files表索引

**位置**: `sql/create_performance_indexes.sql`

**已创建索引**:
- ✅ `idx_catalog_platform_domain_granularity`: `(source_platform, data_domain, granularity)`
- ✅ `idx_catalog_date_range`: `(date_from, date_to)`
- ✅ `idx_catalog_shop`: `(shop_id)`
- ✅ `idx_catalog_account`: `(account)`
- ✅ `idx_catalog_status_time`: `(status, first_seen_at DESC)`
- ✅ `idx_catalog_file_hash`: `(file_hash)` (唯一索引)

**用途**:
- 文件查询（平台+域+粒度）
- 日期范围查询
- 店铺/账号查询
- 状态查询
- 文件去重

### 5. 维度表索引

**DimShops表**:
- ✅ `ix_dim_shops_platform_shop`: `(platform_code, shop_id)`
- ✅ `ix_dim_shops_platform_slug`: `(platform_code, shop_slug)`

**DimProducts表**:
- ✅ `ix_dim_products_platform_shop`: `(platform_code, shop_id)`

**DimExchangeRates表**:
- ✅ `ix_exchange_rate_lookup`: `(from_currency, to_currency, rate_date)`
- ✅ `ix_exchange_rate_date`: `(rate_date)`

---

## 🔍 索引优化建议

### 1. 时间字段索引优化

**当前状态**: 
- ✅ `order_date_local`已索引（在组合索引中）
- ✅ `metric_date`已索引（主键字段）

**建议**:
- ✅ 保持现有索引策略
- ⚠️ 如需查询`order_time_utc`，考虑添加单列索引或组合索引

### 2. 店铺字段索引优化

**当前状态**:
- ✅ `shop_id`在多个组合索引中
- ✅ `platform_code + shop_id`组合索引已创建

**建议**:
- ✅ 保持现有索引策略
- ✅ 组合索引顺序符合查询模式（platform_code → shop_id → date）

### 3. 状态字段索引优化

**当前状态**:
- ✅ `order_status`在组合索引中
- ✅ `status`在catalog_files表中已索引

**建议**:
- ✅ 保持现有索引策略
- ⚠️ 如需频繁查询特定状态，考虑部分索引（WHERE status = 'active'）

### 4. JSONB字段索引优化

**当前状态**:
- ⚠️ `attributes`字段（JSONB）未创建GIN索引

**建议**:
- ⚠️ 如需查询JSONB字段，创建GIN索引：
  ```sql
  CREATE INDEX idx_fact_orders_attributes_gin ON fact_orders USING GIN (attributes);
  ```

---

## 📊 索引使用情况监控

### 1. 检查索引使用情况

**PostgreSQL查询**:
```sql
-- 查看索引使用统计
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

### 2. 识别未使用的索引

**查询未使用的索引**:
```sql
-- 查找从未使用过的索引
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND idx_scan = 0
  AND indexname NOT LIKE 'pg_toast%'
ORDER BY tablename, indexname;
```

### 3. 索引大小监控

**查询索引大小**:
```sql
-- 查看索引大小
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## 🚀 性能优化最佳实践

### 1. 索引设计原则

- ✅ **最左前缀原则**: 组合索引列顺序必须匹配查询WHERE条件顺序
- ✅ **选择性**: 高选择性字段优先（如日期、ID）
- ✅ **查询频率**: 为频繁查询的字段组合创建索引
- ✅ **索引大小**: 避免索引列过多（影响写入性能）

### 2. 避免N+1查询

**问题**: 循环中执行数据库查询

**解决方案**:
- ✅ 使用`joinedload()`预加载关联数据
- ✅ 使用批量查询（`IN`查询）
- ✅ 使用物化视图（预计算数据）

**示例**:
```python
# ❌ N+1查询
for order in orders:
    items = db.query(FactOrderItem).filter_by(order_id=order.order_id).all()

# ✅ 批量查询
order_ids = [order.order_id for order in orders]
items = db.query(FactOrderItem).filter(FactOrderItem.order_id.in_(order_ids)).all()
```

### 3. 使用物化视图

**优势**:
- ✅ 预计算数据，查询速度快
- ✅ 减少实时计算开销
- ✅ 支持索引优化

**当前物化视图**:
- ✅ `mv_shop_daily_performance`: 店铺日度表现
- ✅ `mv_shop_health_summary`: 店铺健康度汇总
- ✅ `mv_campaign_achievement`: 战役达成率
- ✅ `mv_target_achievement`: 目标达成率

---

## 📝 索引维护

### 1. 定期重建索引

**PostgreSQL命令**:
```sql
-- 重建索引（回收空间，优化性能）
REINDEX INDEX CONCURRENTLY idx_fact_orders_plat_shop_date;
```

### 2. 更新统计信息

**PostgreSQL命令**:
```sql
-- 更新表统计信息（优化查询计划）
ANALYZE fact_orders;
ANALYZE fact_order_items;
ANALYZE fact_product_metrics;
```

### 3. 监控索引膨胀

**查询索引膨胀**:
```sql
-- 查看索引膨胀情况
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    pg_size_pretty(pg_relation_size(indexrelid) - pg_relation_size(indexrelid, 'vm')) AS bloat_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## 🔧 索引创建脚本

**位置**: `sql/create_performance_indexes.sql`

**使用方法**:
```bash
# 执行索引创建脚本
psql -U postgres -d xihong_erp -f sql/create_performance_indexes.sql
```

**注意**:
- ✅ 索引创建可能需要较长时间（大数据量）
- ✅ 建议在低峰期执行
- ✅ 使用`CREATE INDEX CONCURRENTLY`避免锁表

---

## 📚 相关文档

- 📖 [数据库设计规范](DEVELOPMENT_RULES/DATABASE_DESIGN.md) - 数据库设计详细规范
- 📖 [C类数据查询策略指南](C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md) - 查询优化策略
- 📖 [PostgreSQL慢查询日志配置指南](POSTGRESQL_SLOW_QUERY_LOG_GUIDE.md) - 慢查询监控

---

**最后更新**: 2025-01-31  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

