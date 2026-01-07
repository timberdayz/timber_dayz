# PostgreSQL生产环境部署与优化指南

## 概述

西虹ERP系统v4.3.2在生产环境推荐使用PostgreSQL 15+，以获得最佳性能和完整功能支持（特别是质量监控和物化视图）。

## 一、环境准备

### 1.1 安装PostgreSQL

**Windows:**
```powershell
# 下载并安装PostgreSQL 15+
# https://www.postgresql.org/download/windows/

# 或使用Docker
docker run -d --name erp_postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=xihong_erp \
  -p 5432:5432 \
  -v erp_data:/var/lib/postgresql/data \
  postgres:15-alpine
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql-15 postgresql-contrib-15

# CentOS/RHEL
sudo dnf install postgresql15-server postgresql15-contrib
sudo postgresql-15-setup initdb
sudo systemctl enable postgresql-15
sudo systemctl start postgresql-15
```

### 1.2 创建数据库和用户

```sql
-- 以postgres用户登录
psql -U postgres

-- 创建数据库
CREATE DATABASE xihong_erp 
  ENCODING 'UTF8' 
  LC_COLLATE = 'zh_CN.UTF-8' 
  LC_CTYPE = 'zh_CN.UTF-8'
  TEMPLATE template0;

-- 创建应用用户
CREATE USER erp_user WITH PASSWORD 'secure_password_here';

-- 授权
GRANT ALL PRIVILEGES ON DATABASE xihong_erp TO erp_user;

-- 连接到目标数据库
\c xihong_erp

-- 授予schema权限
GRANT ALL ON SCHEMA public TO erp_user;

-- 授予表创建权限
ALTER DATABASE xihong_erp OWNER TO erp_user;
```

## 二、配置西虹ERP系统

### 2.1 更新环境变量

编辑项目根目录的 `.env` 文件：

```env
# PostgreSQL连接（生产环境）
DATABASE_URL=postgresql://erp_user:secure_password_here@localhost:5432/xihong_erp

# 或使用连接参数形式
DB_HOST=localhost
DB_PORT=5432
DB_NAME=xihong_erp
DB_USER=erp_user
DB_PASSWORD=secure_password_here
```

### 2.2 初始化数据库Schema

```bash
# 方法1：使用重建脚本（推荐用于首次部署）
python scripts/rebuild_database_v4_3_2.py

# 方法2：使用Alembic迁移
alembic upgrade head
```

## 三、创建物化视图

### 3.1 部署物化视图

```bash
# 连接PostgreSQL并执行SQL
psql -U erp_user -d xihong_erp -f sql/create_materialized_views.sql
```

或使用Python脚本：

```python
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.getenv('DATABASE_URL'))

with open('sql/create_materialized_views.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

with engine.begin() as conn:
    conn.execute(text(sql))
    print('[OK] 物化视图创建成功')
```

### 3.2 配置自动刷新（pg_cron）

#### 安装pg_cron扩展

```sql
-- 以postgres超级用户执行
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 授权给erp_user
GRANT USAGE ON SCHEMA cron TO erp_user;
```

#### 配置刷新任务

```sql
-- 每5分钟刷新店铺汇总（高频）
SELECT cron.schedule(
    'refresh-shop-summary',
    '*/5 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shop_summary;'
);

-- 每15分钟刷新Top商品榜
SELECT cron.schedule(
    'refresh-top-products',
    '*/15 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_products;'
);

-- 每15分钟刷新销售趋势
SELECT cron.schedule(
    'refresh-sales-trend',
    '*/15 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales_trend;'
);

-- 查看已配置的任务
SELECT * FROM cron.job;

-- 删除任务（如需修改）
SELECT cron.unschedule('refresh-shop-summary');
```

#### 替代方案：使用系统cron

如果无法使用pg_cron，可以使用系统cron：

```bash
# 编辑crontab
crontab -e

# 添加以下任务
*/5 * * * * PGPASSWORD=secure_password_here psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shop_summary;" >> /var/log/erp/mv_refresh.log 2>&1
*/15 * * * * PGPASSWORD=secure_password_here psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_products;" >> /var/log/erp/mv_refresh.log 2>&1
*/15 * * * * PGPASSWORD=secure_password_here psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales_trend;" >> /var/log/erp/mv_refresh.log 2>&1
```

## 四、性能优化

### 4.1 关键索引（已在schema.py中定义）

系统已自动创建以下关键索引：

**fact_product_metrics:**
- `ix_product_unique`: 业务唯一索引（含sku_scope）
- `ix_product_platform_date`: 平台+日期查询
- `ix_product_shop_date`: 店铺+日期查询
- `ix_product_parent_sku_date`: 层级聚合查询

**fact_orders:**
- `ix_order_shop_date`: 店铺订单查询
- `ix_order_platform_date`: 平台订单查询

### 4.2 PostgreSQL配置优化

编辑 `postgresql.conf`:

```ini
# 内存配置（根据服务器内存调整）
shared_buffers = 256MB              # 建议：系统内存的25%
effective_cache_size = 1GB          # 建议：系统内存的50-75%
maintenance_work_mem = 64MB         # 用于索引创建和维护
work_mem = 16MB                     # 每个查询操作的内存

# 连接池
max_connections = 100               # 根据并发需求调整

# 查询优化
random_page_cost = 1.1              # SSD存储建议设为1.1
effective_io_concurrency = 200      # SSD存储建议200

# 日志（生产环境建议启用）
log_min_duration_statement = 1000   # 记录执行超过1秒的查询
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
log_statement = 'mod'               # 记录所有DDL/DML
```

重启PostgreSQL使配置生效：
```bash
sudo systemctl restart postgresql-15
```

### 4.3 定期维护

#### 自动VACUUM配置

```sql
-- 查看当前autovacuum配置
SHOW autovacuum;

-- 针对大表调整（如fact_product_metrics）
ALTER TABLE fact_product_metrics SET (
    autovacuum_vacuum_scale_factor = 0.05,  -- 表变更5%时触发
    autovacuum_analyze_scale_factor = 0.02
);
```

#### 手动维护脚本

创建 `scripts/pg_maintenance.sh`:

```bash
#!/bin/bash
export PGPASSWORD=secure_password_here

echo "[$(date)] 开始数据库维护..."

# VACUUM ANALYZE（回收空间+更新统计）
psql -U erp_user -d xihong_erp -c "VACUUM ANALYZE;"

# REINDEX（重建索引）
psql -U erp_user -d xihong_erp -c "REINDEX DATABASE xihong_erp;"

echo "[$(date)] 维护完成"
```

设置为每周执行：
```bash
chmod +x scripts/pg_maintenance.sh

# 添加到crontab（每周日凌晨3点）
0 3 * * 0 /path/to/scripts/pg_maintenance.sh >> /var/log/erp/maintenance.log 2>&1
```

## 五、监控与告警

### 5.1 查询性能监控

```sql
-- 安装pg_stat_statements扩展
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 查看慢查询TOP 10
SELECT 
    query,
    calls,
    mean_exec_time,
    max_exec_time,
    total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- 重置统计
SELECT pg_stat_statements_reset();
```

### 5.2 连接监控

```sql
-- 当前连接数
SELECT count(*) FROM pg_stat_activity;

-- 活跃查询
SELECT 
    pid,
    usename,
    application_name,
    state,
    query,
    query_start
FROM pg_stat_activity
WHERE state = 'active'
  AND pid != pg_backend_pid();

-- 杀死长时间运行的查询（慎用）
SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
WHERE state = 'active' 
  AND query_start < NOW() - INTERVAL '10 minutes'
  AND pid != pg_backend_pid();
```

### 5.3 表和索引大小监控

```sql
-- 表大小TOP 10
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY size_bytes DESC
LIMIT 10;

-- 索引使用情况
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC, pg_relation_size(indexrelid) DESC;
```

## 六、备份与恢复

### 6.1 定时备份

```bash
#!/bin/bash
# scripts/pg_backup.sh

BACKUP_DIR="/var/backups/erp"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="xihong_erp_${DATE}.sql.gz"

export PGPASSWORD=secure_password_here

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份
pg_dump -U erp_user -d xihong_erp | gzip > "$BACKUP_DIR/$FILENAME"

# 保留最近7天的备份
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "[$(date)] 备份完成: $FILENAME"
```

设置为每天执行：
```bash
chmod +x scripts/pg_backup.sh

# 添加到crontab（每天凌晨2点）
0 2 * * * /path/to/scripts/pg_backup.sh >> /var/log/erp/backup.log 2>&1
```

### 6.2 恢复

```bash
# 恢复备份
gunzip -c /var/backups/erp/xihong_erp_20250128_020000.sql.gz | \
psql -U erp_user -d xihong_erp_restore

# 或直接从压缩文件恢复
pg_restore -U erp_user -d xihong_erp_restore /var/backups/erp/xihong_erp_20250128_020000.sql.gz
```

## 七、从SQLite迁移到PostgreSQL

### 7.1 数据迁移工具

使用pgloader（推荐）：

```bash
# 安装pgloader
sudo apt install pgloader  # Ubuntu/Debian
brew install pgloader      # macOS

# 执行迁移
pgloader \
    sqlite://data/unified_erp_system.db \
    postgresql://erp_user:password@localhost/xihong_erp
```

### 7.2 手动迁移脚本

```python
# scripts/migrate_sqlite_to_pg.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pandas as pd

# 源（SQLite）
sqlite_engine = create_engine("sqlite:///data/unified_erp_system.db")

# 目标（PostgreSQL）
pg_engine = create_engine("postgresql://erp_user:password@localhost/xihong_erp")

# 需要迁移的表
tables = [
    'dim_platforms',
    'dim_shops',
    'dim_products',
    'dim_currency_rates',
    'catalog_files',
    'fact_orders',
    'fact_order_items',
    'fact_product_metrics'
]

for table in tables:
    print(f"[迁移] {table}...")
    try:
        df = pd.read_sql_table(table, sqlite_engine)
        df.to_sql(table, pg_engine, if_exists='append', index=False, method='multi', chunksize=1000)
        print(f"  [OK] 迁移 {len(df)} 条记录")
    except Exception as e:
        print(f"  [ERROR] {e}")

print("\n[完成] 数据迁移完成")
```

## 八、故障排查

### 8.1 常见问题

**问题1: 连接被拒绝**
```bash
# 检查PostgreSQL状态
sudo systemctl status postgresql-15

# 检查监听地址
sudo netstat -plnt | grep 5432

# 编辑pg_hba.conf允许连接
# 添加: host  all  all  0.0.0.0/0  md5
sudo systemctl restart postgresql-15
```

**问题2: 查询性能慢**
```sql
-- 分析查询计划
EXPLAIN ANALYZE 
SELECT * FROM fact_product_metrics 
WHERE platform_code = 'shopee' AND metric_date > '2025-01-01';

-- 更新统计信息
ANALYZE fact_product_metrics;
```

**问题3: 磁盘空间不足**
```sql
-- 查看膨胀严重的表
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 执行VACUUM FULL（需要锁表，谨慎使用）
VACUUM FULL fact_product_metrics;
```

## 九、安全加固

### 9.1 访问控制

```sql
-- 限制erp_user权限（最小权限原则）
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO erp_user;

-- 只授予必要的表权限
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO erp_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO erp_user;
```

### 9.2 SSL连接（生产环境推荐）

```ini
# postgresql.conf
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'
```

更新连接字符串：
```env
DATABASE_URL=postgresql://erp_user:password@localhost:5432/xihong_erp?sslmode=require
```

## 十、性能基准测试

部署完成后，运行性能基准测试：

```bash
# 运行完整系统测试
python tests/test_v4_3_2_complete_system.py

# 运行性能测试（如果有）
python backend/run_performance_tests.py
```

---

## 附录：快速检查清单

- [ ] PostgreSQL 15+已安装
- [ ] 数据库和用户已创建
- [ ] 环境变量已配置（DATABASE_URL）
- [ ] Schema已初始化（31个字段完整）
- [ ] 物化视图已创建
- [ ] 自动刷新任务已配置（pg_cron或system cron）
- [ ] PostgreSQL配置已优化
- [ ] 备份脚本已配置并测试
- [ ] 监控指标已配置
- [ ] 系统测试通过（8/8）

**生产就绪！** 🚀

