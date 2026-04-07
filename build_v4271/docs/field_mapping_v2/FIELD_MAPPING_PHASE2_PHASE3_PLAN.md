# 字段映射系统第二、三阶段优化计划

**当前版本**: v2.3（第一阶段已完成）  
**计划日期**: 2025-10-27  
**预计完成**: 第二阶段 2025-11-03，第三阶段 2025-11-17

---

## 第二阶段：高性能批量导入与连接池优化（1周内）

### 目标
- 入库性能提升 5-10 倍（从 1000行/10秒 到 1000行/1-2秒）
- 连接池稳定性增强
- 物化视图自动刷新

### 任务清单

#### 1. COPY 流水线实现

**文件**: `backend/services/bulk_importer.py`（新增）

**核心逻辑**:
```python
def bulk_import_via_copy(df: pd.DataFrame, table: str, db: Session):
    """使用 PostgreSQL COPY 批量导入"""
    # 1. 写入临时 CSV
    temp_csv = f"/tmp/{uuid.uuid4()}.csv"
    df.to_csv(temp_csv, index=False, header=False)
    
    # 2. COPY 到暂存表
    with open(temp_csv, 'r') as f:
        cursor = db.connection().connection.cursor()
        cursor.copy_from(f, f'staging_{table}', sep=',', null='')
    
    # 3. 批量 UPSERT 到事实表
    db.execute(text(f"""
        INSERT INTO {table} (...)
        SELECT ... FROM staging_{table}
        ON CONFLICT (...) DO UPDATE SET ...
    """))
    
    # 4. 清理临时文件和暂存表
    os.remove(temp_csv)
    db.execute(text(f"TRUNCATE staging_{table}"))
```

**性能优化**:
- 会话级设置：`SET LOCAL synchronous_commit = off`
- 批量提交：每 10000 行提交一次
- 后台 ANALYZE：入库后异步执行

---

#### 2. 连接池配置优化

**文件**: `backend/models/database.py`

**配置调整**:
```python
engine = create_engine(
    DATABASE_URL,
    # 连接池配置
    pool_size=20,              # 基础连接数（默认5→20）
    max_overflow=10,           # 最大溢出（默认10）
    pool_recycle=3600,         # 1小时回收（默认-1）
    pool_pre_ping=True,        # 连接前检查（默认False）
    pool_timeout=30,           # 获取连接超时（默认30）
    
    # 语句超时配置
    connect_args={
        "options": "-c statement_timeout=30000"  # 30秒
    },
    
    # 性能优化
    echo=False,                # 生产环境关闭SQL日志
    future=True,               # 使用SQLAlchemy 2.0风格
)
```

**监控**:
```python
@app.get("/api/health")
async def health_check():
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total_available": pool.size() - pool.checkedout()
    }
```

---

#### 3. 物化视图并发刷新

**文件**: `backend/services/materialized_view_manager.py`（新增）

**实现**:
```python
def refresh_mv_concurrently(mv_name: str, db: Session):
    """并发刷新物化视图（不阻塞读取）"""
    # 前提：视图必须有唯一索引
    db.execute(text(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {mv_name}_unique_idx 
        ON {mv_name} (platform_code, shop_id, metric_date);
        
        REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name};
    """))
```

**定时任务**（Celery）:
```python
@app.task
def refresh_dashboard_views():
    """每小时刷新看板物化视图"""
    refresh_mv_concurrently('mv_daily_sales_summary', db)
    refresh_mv_concurrently('mv_weekly_gmv', db)
```

---

### 验收标准

| 指标 | 当前 | 目标 | 测试方法 |
|------|------|------|---------|
| 入库性能 | 1000行/10秒 | 1000行/1-2秒 | 性能测试脚本 |
| 连接池利用率 | 未监控 | <80% | `/health` 接口 |
| MV 刷新时间 | 阻塞式 | 非阻塞 | CONCURRENTLY 验证 |

---

## 第三阶段：分区与监控体系（2周内）

### 目标
- 事实表查询性能提升 10-100 倍（分区裁剪）
- 完整的监控与告警体系
- 类型与约束收敛

### 任务清单

#### 1. 事实表月分区

**目标表**:
- `fact_order` → `fact_order_y2025m10`、`fact_order_y2025m11`
- `fact_product_metrics` → `fact_product_metrics_y2025m10`

**创建分区**:
```sql
-- 创建分区表（父表）
CREATE TABLE fact_order_partitioned (
    LIKE fact_order INCLUDING ALL
) PARTITION BY RANGE (order_date);

-- 创建月分区（自动化脚本生成）
CREATE TABLE fact_order_y2025m10 
PARTITION OF fact_order_partitioned
FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

-- 创建本地索引
CREATE INDEX idx_fact_order_y2025m10_shop_date 
ON fact_order_y2025m10 (shop_id, order_date);
```

**数据迁移**:
```sql
-- 迁移现有数据
INSERT INTO fact_order_partitioned SELECT * FROM fact_order;

-- 重命名表（停机维护）
ALTER TABLE fact_order RENAME TO fact_order_old;
ALTER TABLE fact_order_partitioned RENAME TO fact_order;
```

**自动化脚本**: `scripts/create_monthly_partitions.py`（按季度预创建分区）

---

#### 2. dim_date 维表

**表结构**:
```sql
CREATE TABLE dim_date (
    date_id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    
    -- 年月日
    year SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    day SMALLINT NOT NULL,
    
    -- ISO 周
    iso_year SMALLINT NOT NULL,
    iso_week SMALLINT NOT NULL,
    iso_weekday SMALLINT NOT NULL,
    
    -- 季度
    quarter SMALLINT NOT NULL,
    
    -- 中文标签
    year_month VARCHAR(7) NOT NULL,     -- '2025-10'
    year_quarter VARCHAR(7) NOT NULL,   -- '2025-Q4'
    
    -- 工作日标识
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN DEFAULT FALSE
);

-- 索引
CREATE INDEX idx_dim_date_iso_year_week ON dim_date (iso_year, iso_week);
CREATE INDEX idx_dim_date_year_month ON dim_date (year, month);
```

**数据生成**:
```python
def populate_dim_date(start_year=2020, end_year=2030):
    """生成 2020-2030 年的日期维表"""
    import pandas as pd
    from datetime import date, timedelta
    
    dates = []
    current = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    
    while current <= end:
        dates.append({
            'date': current,
            'year': current.year,
            'month': current.month,
            'day': current.day,
            'iso_year': current.isocalendar()[0],
            'iso_week': current.isocalendar()[1],
            'iso_weekday': current.isocalendar()[2],
            'quarter': (current.month - 1) // 3 + 1,
            'year_month': current.strftime('%Y-%m'),
            'year_quarter': f"{current.year}-Q{(current.month-1)//3+1}",
            'is_weekend': current.weekday() >= 5
        })
        current += timedelta(days=1)
    
    df = pd.DataFrame(dates)
    df.to_sql('dim_date', engine, if_exists='append', index=False)
```

**周聚合示例**:
```sql
-- 按周统计 GMV（自动处理跨月/跨年）
SELECT 
    d.iso_year,
    d.iso_week,
    d.year_month,
    SUM(m.gmv) AS weekly_gmv
FROM fact_product_metrics m
JOIN dim_date d ON d.date = m.metric_date
WHERE d.date >= '2025-09-01' AND d.date < '2025-11-01'
GROUP BY d.iso_year, d.iso_week, d.year_month
ORDER BY d.iso_year, d.iso_week;
```

---

#### 3. 监控与慢 SQL 优化

**开启 pg_stat_statements**:
```sql
-- 修改 postgresql.conf
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.track = all
pg_stat_statements.max = 10000

-- 重启 PostgreSQL
-- 创建扩展
CREATE EXTENSION pg_stat_statements;
```

**慢查询监控**:
```sql
-- Top 10 慢查询
SELECT 
    query,
    calls,
    mean_exec_time,
    total_exec_time,
    (total_exec_time / sum(total_exec_time) OVER ()) * 100 AS pct
FROM pg_stat_statements
WHERE mean_exec_time > 100  -- 超过100ms
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Prometheus 指标导出**:
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:9187']
```

---

#### 4. 字段类型与约束收敛

**目标**: 将宽泛类型收敛为精确类型

**改造示例**:
```sql
-- 订单金额：VARCHAR → NUMERIC(15,2)
ALTER TABLE fact_order 
ALTER COLUMN total_amount TYPE NUMERIC(15,2) 
USING total_amount::NUMERIC(15,2);

-- 订单日期：VARCHAR → TIMESTAMP WITH TIME ZONE
ALTER TABLE fact_order 
ALTER COLUMN order_date TYPE TIMESTAMP WITH TIME ZONE 
USING order_date::TIMESTAMP WITH TIME ZONE;

-- 必填字段约束
ALTER TABLE fact_order 
ALTER COLUMN order_id SET NOT NULL,
ALTER COLUMN shop_id SET NOT NULL;

-- 复合唯一索引（订单明细）
CREATE UNIQUE INDEX uq_fact_order_detail 
ON fact_order (platform_code, shop_id, order_id, line_no);
```

---

### 验收标准

| 指标 | 当前 | 目标 | 测试方法 |
|------|------|------|---------|
| 跨月周查询 | 全表扫描 | 2-3 分区扫描 | EXPLAIN ANALYZE |
| 查询响应时间 | 10-30s | 1-3s | 看板加载测试 |
| 监控覆盖率 | 0% | 90% | Prometheus + Grafana |
| 类型正确率 | 60% | 95% | Schema 审查 |

---

## 实施风险与缓解

### 风险1: 分区迁移停机时间

**风险等级**: 高  
**缓解方案**:
- 在低峰期（凌晨 2-4 点）执行
- 使用 `pg_partman` 工具自动化分区管理
- 保留 `fact_order_old` 表作为回滚备份

### 风险2: dim_date 与现有查询兼容性

**风险等级**: 中  
**缓解方案**:
- 创建视图兼容旧查询：`CREATE VIEW v_orders_with_week AS SELECT ..., d.iso_week FROM fact_order o JOIN dim_date d ON ...`
- 逐步迁移查询，而非一次性替换

### 风险3: 慢查询优化可能破坏功能

**风险等级**: 低  
**缓解方案**:
- 在测试环境先验证
- 使用 `EXPLAIN ANALYZE` 对比优化前后
- 保留原查询作为注释

---

## 执行步骤

### 第二阶段执行步骤

1. **开发 COPY 流水线**（2天）
   - 实现 `bulk_importer.py`
   - 编写单元测试
   - 性能基准测试

2. **连接池配置优化**（1天）
   - 调整 `database.py` 配置
   - 添加健康检查指标
   - 压力测试

3. **物化视图并发刷新**（2天）
   - 实现 `materialized_view_manager.py`
   - 创建 Celery 定时任务
   - 验证并发刷新无锁

### 第三阶段执行步骤

1. **事实表分区设计**（3天）
   - 设计分区策略（按月/按日）
   - 编写迁移脚本
   - 低峰期执行迁移

2. **dim_date 维表**（2天）
   - 创建表结构
   - 生成 2020-2030 数据
   - 迁移周聚合查询

3. **监控体系搭建**（3天）
   - 配置 pg_stat_statements
   - 部署 Prometheus + Grafana
   - 创建告警规则

4. **类型与约束收敛**（4天）
   - Schema 审查
   - 批量类型转换
   - 添加 NOT NULL 和唯一约束

---

## 性能预期

### 第二阶段后

| 操作 | 当前 | 预期 | 提升 |
|------|------|------|------|
| 入库 10000 行 | 100秒 | 10-20秒 | 5-10倍 |
| 连接获取延迟 | 不稳定 | <100ms | 稳定 |
| MV 刷新阻塞 | 是 | 否 | 无阻塞 |

### 第三阶段后

| 操作 | 当前 | 预期 | 提升 |
|------|------|------|------|
| 跨月周查询 | 30秒 | 2-3秒 | 10-15倍 |
| 看板加载 | 10秒 | 1秒 | 10倍 |
| 监控覆盖 | 0% | 90% | 全面 |

---

## 技术栈

- **分区管理**: pg_partman（自动化）
- **批量导入**: COPY + psycopg3
- **监控**: Prometheus + Grafana + postgres_exporter
- **任务调度**: Celery + Redis
- **日志分析**: pg_stat_statements + pgBadger

---

## 参考资料

- [PostgreSQL 分区表官方文档](https://www.postgresql.org/docs/15/ddl-partitioning.html)
- [pg_partman GitHub](https://github.com/pgpartman/pg_partman)
- [postgres_exporter](https://github.com/prometheus-community/postgres_exporter)
- [Grafana PostgreSQL 看板](https://grafana.com/grafana/dashboards/9628)

---

**文档版本**: v1.0  
**最后更新**: 2025-10-27  
**状态**: 计划阶段

