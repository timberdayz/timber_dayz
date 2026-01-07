# PostgreSQL慢查询日志配置指南

**创建时间**: 2025-01-31  
**状态**: ✅ 已完成  
**目的**: 指导数据库管理员如何配置PostgreSQL慢查询日志

---

## 📋 概述

本文档说明如何配置PostgreSQL慢查询日志，用于识别和优化慢查询。

**注意**: 此配置需要数据库管理员权限，不在代码层面实现。

---

## 🔧 配置步骤

### 1. 修改PostgreSQL配置文件

**配置文件位置**:
- Linux: `/etc/postgresql/{version}/main/postgresql.conf`
- Windows: `C:\Program Files\PostgreSQL\{version}\data\postgresql.conf`
- Docker: 挂载配置文件或使用环境变量

### 2. 启用慢查询日志

**配置项**:
```conf
# 启用日志记录
logging_collector = on

# 日志目录（Linux）
log_directory = 'log'

# 日志文件名模式
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'

# 日志轮转
log_rotation_age = 1d
log_rotation_size = 100MB

# 记录慢查询（>100ms）
log_min_duration_statement = 100

# 记录所有语句（可选，用于调试）
# log_statement = 'all'

# 记录执行计划（可选）
# log_plan = on

# 记录锁等待（可选）
# log_lock_waits = on
```

### 3. Docker环境配置

**docker-compose.yml示例**:
```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: xihong_erp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf  # 挂载配置文件
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

**或使用环境变量**:
```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: xihong_erp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      # 慢查询日志配置
      POSTGRES_INITDB_ARGS: "-c log_min_duration_statement=100"
```

### 4. 重启PostgreSQL服务

**Linux**:
```bash
sudo systemctl restart postgresql
```

**Docker**:
```bash
docker-compose restart postgres
```

---

## 📊 慢查询日志格式

### 标准格式

```
2025-01-31 10:30:15.123 UTC [12345] postgres@xihong_erp LOG:  duration: 250.456 ms  statement: SELECT * FROM fact_orders WHERE platform_code = 'shopee' AND shop_id = 'shop1' AND order_date_local BETWEEN '2025-01-01' AND '2025-01-31';
```

### 字段说明

- **timestamp**: 查询执行时间
- **duration**: 查询耗时（毫秒）
- **statement**: SQL语句

---

## 🔍 分析慢查询日志

### 1. 提取慢查询

**使用grep提取**:
```bash
# 提取所有慢查询
grep "duration:" /var/lib/postgresql/data/log/postgresql-*.log

# 提取超过1秒的查询
grep "duration: [0-9]\{4,\}" /var/lib/postgresql/data/log/postgresql-*.log

# 提取特定表的查询
grep "FROM fact_orders" /var/lib/postgresql/data/log/postgresql-*.log
```

### 2. 统计慢查询

**使用awk统计**:
```bash
# 统计慢查询数量
grep "duration:" /var/lib/postgresql/data/log/postgresql-*.log | wc -l

# 统计最慢的10个查询
grep "duration:" /var/lib/postgresql/data/log/postgresql-*.log | \
  awk '{print $NF, $0}' | \
  sort -rn | \
  head -10
```

### 3. 分析查询模式

**识别常见慢查询**:
```bash
# 提取SQL语句并统计
grep "duration:" /var/lib/postgresql/data/log/postgresql-*.log | \
  sed 's/.*statement: //' | \
  sort | uniq -c | \
  sort -rn | \
  head -20
```

---

## 🚀 优化慢查询

### 1. 识别问题查询

**常见问题**:
- ❌ 缺少索引
- ❌ 全表扫描
- ❌ N+1查询
- ❌ 复杂JOIN
- ❌ 子查询性能差

### 2. 使用EXPLAIN分析

**分析查询计划**:
```sql
-- 查看查询计划
EXPLAIN ANALYZE
SELECT * FROM fact_orders
WHERE platform_code = 'shopee'
  AND shop_id = 'shop1'
  AND order_date_local BETWEEN '2025-01-01' AND '2025-01-31';
```

**关键指标**:
- **Seq Scan**: 全表扫描（需要优化）
- **Index Scan**: 索引扫描（良好）
- **Execution Time**: 执行时间（目标<100ms）

### 3. 优化策略

**添加索引**:
```sql
-- 为慢查询字段添加索引
CREATE INDEX CONCURRENTLY idx_fact_orders_platform_shop_date
ON fact_orders (platform_code, shop_id, order_date_local);
```

**优化查询**:
```sql
-- ❌ 避免全表扫描
SELECT * FROM fact_orders WHERE order_status = 'pending';

-- ✅ 使用索引字段
SELECT * FROM fact_orders 
WHERE platform_code = 'shopee' 
  AND shop_id = 'shop1' 
  AND order_status = 'pending';
```

---

## 📈 监控和告警

### 1. 定期分析

**建议频率**:
- ✅ 每日分析（开发环境）
- ✅ 每周分析（生产环境）
- ✅ 每月总结（优化报告）

### 2. 设置告警

**告警阈值**:
- ⚠️ 慢查询数量 > 100/天
- ⚠️ 单个查询 > 5秒
- ⚠️ 全表扫描 > 10次/天

### 3. 性能报告

**报告内容**:
- 📊 慢查询统计（数量、平均耗时）
- 📊 最慢的10个查询
- 📊 索引使用情况
- 📊 优化建议

---

## 🔧 高级配置

### 1. 记录执行计划

**配置**:
```conf
# 记录执行计划（仅慢查询）
log_min_duration_statement = 100
log_plan = on
```

**日志格式**:
```
2025-01-31 10:30:15.123 UTC [12345] postgres@xihong_erp LOG:  duration: 250.456 ms  plan:
  Seq Scan on fact_orders  (cost=0.00..1234.56 rows=1000 width=100) (actual time=0.123..250.456 rows=1000 loops=1)
    Filter: ((platform_code = 'shopee') AND (shop_id = 'shop1'))
    Rows Removed by Filter: 9000
```

### 2. 记录锁等待

**配置**:
```conf
# 记录锁等待（>1秒）
log_lock_waits = on
deadlock_timeout = 1000
```

### 3. 记录连接信息

**配置**:
```conf
# 记录连接信息
log_connections = on
log_disconnections = on
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

---

## 📚 相关文档

- 📖 [数据库索引优化指南](DATABASE_INDEX_OPTIMIZATION.md) - 索引优化策略
- 📖 [C类数据查询策略指南](C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md) - 查询优化策略
- 📖 [性能监控实现文档](docs/DEVELOPMENT_RULES/PERFORMANCE_MONITORING.md) - 性能监控详细规范

---

## ⚠️ 注意事项

1. **日志文件大小**: 慢查询日志可能快速增长，需要定期清理
2. **性能影响**: 启用详细日志可能影响性能，建议仅在需要时启用
3. **权限要求**: 修改PostgreSQL配置需要数据库管理员权限
4. **备份配置**: 修改配置前请备份原始配置文件

---

**最后更新**: 2025-01-31  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

