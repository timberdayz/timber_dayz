# 性能优化建议文档

**创建日期**: 2025-11-05  
**适用版本**: v4.6.2+  
**优先级分类**: P0紧急/P1重要/P2建议

---

## 执行摘要

本文档记录了针对西虹ERP系统的性能优化建议。当前系统功能完整，但在查询性能、缓存策略、索引优化等方面有提升空间。所有建议均标注了优先级、预期收益和实施难度，供未来优化参考。

**不建议立即执行**：这些优化应该在有明确性能瓶颈时再实施，避免过度优化。

---

## 1. 数据库索引优化

### 1.1 字段映射辞典查询优化（P1 - 重要）

**当前状态**:
```python
# modules/core/db/schema.py
class FieldMappingDictionary(Base):
    __table_args__ = (
        Index("ix_field_dict_domain", "data_domain"),
        Index("ix_field_dict_version", "version"),
    )
```

**问题分析**:
- 字段映射API频繁查询（每次预览数据时调用）
- 查询条件：`data_domain + version + status`
- 当前索引不完整，可能导致全表扫描

**优化建议**:
```python
# 添加复合索引
__table_args__ = (
    Index("ix_field_dict_domain", "data_domain"),
    Index("ix_field_dict_version", "version"),
    # 新增：复合索引（覆盖查询条件）
    Index("ix_field_dict_composite", "data_domain", "version", "status"),
    # 新增：Pattern查询优化
    Index("ix_field_dict_pattern", "is_pattern_based"),
)
```

**预期收益**:
- 字段辞典查询速度提升50-80%
- 预览数据响应时间从200ms降至50ms

**实施难度**: 低（创建Alembic迁移，5分钟）

**验证方法**:
```sql
-- 执行前
EXPLAIN ANALYZE
SELECT * FROM field_mapping_dictionary
WHERE data_domain = 'orders' AND version = 2 AND status = 'active';

-- 执行后
-- 应该看到使用ix_field_dict_composite索引
```

---

### 1.2 订单查询优化（P1 - 重要）

**当前状态**:
```python
# modules/core/db/schema.py
class FactOrder(Base):
    __table_args__ = (
        UniqueConstraint(...),
        Index("ix_fact_orders_date", "order_date_local"),
        Index("ix_fact_orders_platform", "platform_code"),
    )
```

**问题分析**:
- 数据看板按平台+日期范围查询订单
- 店铺销售统计按shop_id+日期查询
- 当前索引不支持复合查询

**优化建议**:
```python
# 添加复合索引
__table_args__ = (
    # 现有索引保留
    Index("ix_fact_orders_date", "order_date_local"),
    Index("ix_fact_orders_platform", "platform_code"),
    # 新增：日期范围 + 平台查询
    Index("ix_orders_date_platform", "order_date_local", "platform_code"),
    # 新增：店铺销售统计
    Index("ix_orders_shop_date", "shop_id", "order_date_local"),
    # 新增：状态筛选
    Index("ix_orders_status", "order_status"),
)
```

**预期收益**:
- 数据看板查询速度提升60-90%
- TopN查询从500ms降至100ms

**实施难度**: 低（创建Alembic迁移，5分钟）

---

### 1.3 产品指标查询优化（P1 - 重要）

**当前状态**:
```python
# modules/core/db/schema.py
class FactProductMetrics(Base):
    __table_args__ = (
        UniqueConstraint(...),
        Index("ix_fact_product_metrics_date", "metric_date"),
    )
```

**问题分析**:
- 产品管理页按日期范围查询
- SKU趋势分析按platform_sku + 日期查询
- 当前索引不够完整

**优化建议**:
```python
# 添加复合索引
__table_args__ = (
    # 现有索引保留
    Index("ix_fact_product_metrics_date", "metric_date"),
    # 新增：日期范围查询
    Index("ix_metrics_date_range", "metric_date", "platform_code", "shop_id"),
    # 新增：SKU趋势查询
    Index("ix_metrics_sku", "platform_sku", "metric_date"),
    # 新增：粒度筛选
    Index("ix_metrics_granularity", "granularity"),
)
```

**预期收益**:
- 产品列表查询速度提升70%
- SKU趋势图加载从1秒降至200ms

**实施难度**: 低（创建Alembic迁移，5分钟）

---

### 1.4 隔离数据查询优化（P2 - 建议）

**优化建议**:
```python
# modules/core/db/schema.py
class DataQuarantine(Base):
    __table_args__ = (
        # 新增：按文件查询
        Index("ix_quarantine_file", "catalog_file_id"),
        # 新增：按平台+域查询
        Index("ix_quarantine_platform_domain", "platform_code", "data_domain"),
        # 新增：未解决数据筛选
        Index("ix_quarantine_resolved", "is_resolved", "created_at"),
    )
```

**预期收益**: 隔离区列表查询速度提升50%

---

## 2. 查询缓存策略

### 2.1 Redis缓存实施（P1 - 重要）

**当前状态**: 无缓存机制，每次API调用都查询数据库

**问题分析**:
- 字段辞典查询频繁（每次预览数据）
- 数据看板查询重复（多用户同时查看）
- 汇率数据查询（每次入库）

**优化建议**:

#### 安装依赖
```bash
pip install redis aioredis fastapi-cache2
```

#### 配置Redis
```python
# backend/utils/redis_client.py
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

async def init_redis():
    redis = aioredis.from_url(
        "redis://localhost",
        encoding="utf8",
        decode_responses=True
    )
    FastAPICache.init(RedisBackend(redis), prefix="xihong-erp-cache:")
    return redis
```

#### 应用缓存
```python
# backend/routers/field_mapping_dictionary.py
from fastapi_cache.decorator import cache

@router.get("/fields")
@cache(expire=3600)  # 1小时缓存
async def get_field_dictionary(
    data_domain: Optional[str] = None,
    version: Optional[int] = None
):
    # 原有查询逻辑
    pass
```

**缓存策略**:

| 数据类型 | 缓存时间 | 更新策略 |
|---------|---------|---------|
| 字段辞典 | 1小时 | 手动更新时清除缓存 |
| 数据看板 | 5分钟 | 定时刷新 |
| 汇率数据 | 24小时 | 每日凌晨刷新 |
| 模板列表 | 30分钟 | 保存模板时清除缓存 |

**预期收益**:
- API响应速度提升80-95%
- 数据库负载降低70%
- 并发能力提升3-5倍

**实施难度**: 中（需要Redis服务，2-4小时）

**注意事项**:
- 开发环境可不启用缓存（便于调试）
- 缓存失效策略需要完善（CRUD操作时清除相关缓存）

---

### 2.2 物化视图自动刷新（P2 - 建议）

**当前状态**: 5个物化视图需要手动刷新

**优化建议**:
```python
# backend/tasks/scheduled_tasks.py
from celery import Celery
from sqlalchemy import text

celery = Celery('xihong_erp', broker='redis://localhost:6379/0')

@celery.task
def refresh_materialized_views():
    """定时刷新物化视图"""
    views = [
        'mv_sales_day_shop_sku',
        'mv_inventory_snapshot_day',
        'mv_pnl_shop_month',
        'mv_vendor_performance',
        'mv_tax_report_summary'
    ]
    
    with engine.connect() as conn:
        for view in views:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            logger.info(f"Refreshed view: {view}")

# 设置定时任务
celery.conf.beat_schedule = {
    'refresh-mv-hourly': {
        'task': 'backend.tasks.scheduled_tasks.refresh_materialized_views',
        'schedule': 3600.0,  # 每小时执行
    },
}
```

**预期收益**: P&L报表查询稳定在1秒以内

**实施难度**: 中（需要Celery配置，2小时）

---

## 3. N+1查询优化

### 3.1 订单关联查询优化（P1 - 重要）

**当前问题**:
```python
# 可能存在N+1查询
orders = session.query(FactOrder).filter(...).all()
for order in orders:
    shop = order.shop  # 每次查询一次shop表（N+1）
    platform = order.platform  # 每次查询一次platform表（N+1）
```

**优化建议**:
```python
from sqlalchemy.orm import joinedload

# 使用joinedload一次性加载关联数据
orders = session.query(FactOrder)\
    .options(
        joinedload(FactOrder.shop),
        joinedload(FactOrder.platform)
    )\
    .filter(...)\
    .all()

# 或使用selectinload（更适合一对多）
orders = session.query(FactOrder)\
    .options(
        selectinload(FactOrder.items)  # 订单行项目
    )\
    .filter(...)\
    .all()
```

**预期收益**: 订单列表查询速度提升50-80%

**实施难度**: 低（修改查询代码，30分钟）

---

### 3.2 产品图片关联查询优化（P2 - 建议）

**优化建议**:
```python
# backend/routers/product_management.py
from sqlalchemy.orm import selectinload

products = session.query(DimProduct)\
    .options(
        selectinload(DimProduct.images)  # 一次性加载所有图片
    )\
    .filter(...)\
    .all()
```

**预期收益**: 产品列表查询速度提升30-50%

---

## 4. 批量操作优化

### 4.1 数据入库批量插入（P1 - 重要）

**当前状态**: 使用bulk_insert_mappings（已优化）

**进一步优化**:
```python
# backend/services/data_importer.py
def bulk_insert_with_conflict(rows: List[Dict], table_class, db: Session):
    """
    批量插入，支持冲突处理
    使用PostgreSQL的ON CONFLICT
    """
    from sqlalchemy.dialects.postgresql import insert
    
    stmt = insert(table_class).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=['platform_code', 'shop_id', 'order_id'],
        set_={col: stmt.excluded[col] for col in rows[0].keys()}
    )
    
    db.execute(stmt)
    db.commit()
```

**预期收益**: 
- 批量入库速度提升20-30%
- 支持更新已存在数据（幂等性）

**实施难度**: 中（需要测试，2小时）

---

### 4.2 费用分摊批量计算（P2 - 建议）

**优化建议**:
```python
# 使用pandas批量计算，再批量插入
import pandas as pd

df = pd.DataFrame(expenses)
# 批量计算分摊金额
df['allocated_amt'] = df['total_amt'] / df['allocation_factor']

# 批量插入
session.bulk_insert_mappings(
    FactExpensesAllocated,
    df.to_dict('records')
)
```

**预期收益**: 费用分摊速度提升50-70%

---

## 5. 前端性能优化

### 5.1 移除生产环境console.log（P1 - 重要）

**当前状态**: 105个console.log，影响性能和安全

**优化建议**:
```javascript
// vite.config.js
export default {
  build: {
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,  // 生产环境移除console
        drop_debugger: true,  // 移除debugger
        pure_funcs: ['console.log']  // 移除特定函数
      }
    }
  }
}
```

**预期收益**: 
- 生产包体积减小5-10%
- 运行速度提升2-5%
- 避免敏感信息泄露

**实施难度**: 低（修改配置，2分钟）

---

### 5.2 代码分割和懒加载（P2 - 建议）

**优化建议**:
```javascript
// router/index.js
const routes = [
  {
    path: '/field-mapping',
    component: () => import('../views/FieldMappingEnhanced.vue')  // 懒加载
  },
  {
    path: '/finance',
    component: () => import('../views/FinanceManagement.vue')
  }
]
```

**预期收益**: 首屏加载速度提升30-50%

---

## 6. 连接池优化

### 6.1 数据库连接池调优（P2 - 建议）

**当前配置**:
```python
# backend/models/database.py
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)
```

**优化建议**:
```python
# 根据并发量调整
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,  # 增加连接池大小
    max_overflow=40,  # 增加溢出连接
    pool_recycle=3600,  # 1小时回收连接
    pool_timeout=30  # 30秒超时
)
```

**预期收益**: 高并发场景性能提升20-40%

**注意**: 需要根据实际并发量和数据库资源调整

---

## 7. 性能监控

### 7.1 慢查询监控（P1 - 重要）

**优化建议**:
```python
# backend/utils/performance_monitor.py
from functools import wraps
import time

def monitor_query(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        if duration > 0.1:  # 100ms阈值
            logger.warning(f"慢查询: {func.__name__} - {duration:.2f}秒")
        
        return result
    return wrapper

# 应用到查询函数
@monitor_query
def get_orders(db: Session):
    return db.query(FactOrder).all()
```

**预期收益**: 及时发现性能瓶颈

---

## 8. 实施优先级总结

### 第1周（紧急优化）
- [ ] 添加关键数据库索引（字段辞典、订单、产品）
- [ ] 优化N+1查询（使用joinedload）

### 第2-3周（重要优化）
- [ ] 实施Redis缓存（字段辞典、数据看板）
- [ ] 移除生产环境console.log
- [ ] 添加慢查询监控

### 第4周+（持续优化）
- [ ] 物化视图自动刷新
- [ ] 批量操作进一步优化
- [ ] 前端代码分割
- [ ] 连接池调优

---

## 9. 验收标准

### 性能指标
- 字段辞典查询 < 50ms
- 数据看板查询 < 2秒
- TopN查询 < 500ms
- 批量入库 > 1000行/秒

### 监控指标
- 慢查询占比 < 1%
- Redis缓存命中率 > 80%
- API P95响应时间 < 200ms
- 数据库连接利用率 < 80%

---

**重要提醒**: 
1. 这些优化应该在有明确性能问题时再实施
2. 每个优化都需要充分测试
3. 监控优化效果，避免过度优化
4. 优先解决真实的性能瓶颈

---

**文档维护**: 请在实施优化后更新此文档  
**最后更新**: 2025-11-05

