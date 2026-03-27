# API参考文档

**版本**: v1.0  
**更新日期**: 2025-10-16  

---

## 📋 目录

- [DataQueryService](#dataquery服务)
- [CacheService](#缓存服务)
- [ETL服务](#etl服务)
- [工具函数](#工具函数)

---

## DataQuery服务

### DataQueryService

统一数据查询服务，提供所有数据查询接口。

#### 初始化

```python
from modules.services.data_query_service import DataQueryService

service = DataQueryService()
```

或使用全局单例：

```python
from modules.services.data_query_service import get_data_query_service

service = get_data_query_service()
```

---

### 订单查询

#### `get_orders()`

查询订单数据。

**参数**:
- `platforms` (Optional[List[str]]) - 平台列表，如`['shopee', 'tiktok']`
- `shops` (Optional[List[str]]) - 店铺ID列表
- `start_date` (Optional[str]) - 开始日期，格式`YYYY-MM-DD`
- `end_date` (Optional[str]) - 结束日期，格式`YYYY-MM-DD`
- `status` (Optional[str]) - 订单状态过滤
- `limit` (int) - 返回记录数限制，默认1000

**返回**: `pd.DataFrame`

包含列：
- `order_id` - 订单ID
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `order_date_local` - 订单日期
- `total_amount` - 总金额（原币种）
- `total_amount_rmb` - 总金额（RMB）
- `currency` - 货币
- `order_status` - 订单状态
- `payment_status` - 支付状态
- `is_cancelled` - 是否取消
- `is_refunded` - 是否退款

**示例**:

```python
# 查询Shopee近7天订单
from datetime import date, timedelta

orders = service.get_orders(
    platforms=['shopee'],
    start_date=(date.today() - timedelta(days=7)).strftime('%Y-%m-%d'),
    end_date=date.today().strftime('%Y-%m-%d'),
    limit=100
)

print(f"订单数: {len(orders)}")
print(f"总金额: ¥{orders['total_amount_rmb'].sum():,.2f}")
```

---

#### `get_order_summary()`

订单汇总统计。

**参数**:
- `platforms` (Optional[List[str]]) - 平台列表
- `start_date` (Optional[str]) - 开始日期
- `end_date` (Optional[str]) - 结束日期
- `group_by` (str) - 分组方式，可选：
  - `'day'` - 按天聚合
  - `'week'` - 按周聚合
  - `'month'` - 按月聚合
  - `'platform'` - 按平台聚合
  - `'shop'` - 按店铺聚合

**返回**: `pd.DataFrame`

包含列（取决于group_by）:
- `date/week/month/platform_code/shop_id` - 分组字段
- `order_count` - 订单数
- `total_amount` - 总金额（原币种）
- `total_amount_rmb` - 总金额（RMB）
- `avg_amount` - 平均订单金额
- `cancelled_count` - 取消订单数
- `refunded_count` - 退款订单数

**示例**:

```python
# 按天汇总近30天订单
summary = service.get_order_summary(
    platforms=['shopee', 'tiktok'],
    start_date='2024-09-16',
    end_date='2024-10-16',
    group_by='day'
)

# 绘制趋势图
import plotly.express as px
fig = px.line(summary, x='date', y='order_count', title='订单趋势')
```

---

### 产品指标查询

#### `get_product_metrics()`

查询产品指标数据。

**参数**:
- `platforms` (Optional[List[str]]) - 平台列表
- `shops` (Optional[List[str]]) - 店铺ID列表
- `skus` (Optional[List[str]]) - SKU列表
- `metric_type` (Optional[str]) - 指标类型，如`gmv`, `units_sold`, `page_views`
- `start_date` (Optional[str]) - 开始日期
- `end_date` (Optional[str]) - 结束日期
- `limit` (int) - 返回记录数限制，默认1000

**返回**: `pd.DataFrame`

包含列：
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `platform_sku` - 平台SKU
- `product_title` - 产品标题
- `metric_date` - 指标日期
- `metric_type` - 指标类型
- `metric_value` - 指标值（原币种）
- `currency` - 货币
- `metric_value_rmb` - 指标值（RMB）
- `granularity` - 粒度（daily/weekly/monthly）

**示例**:

```python
# 查询Shopee所有产品的GMV
gmv_metrics = service.get_product_metrics(
    platforms=['shopee'],
    metric_type='gmv',
    start_date='2024-10-01',
    end_date='2024-10-16'
)

# 计算总GMV
total_gmv = gmv_metrics['metric_value_rmb'].sum()
print(f"总GMV: ¥{total_gmv:,.2f}")
```

---

#### `get_top_products()`

获取Top产品排行榜。

**参数**:
- `platforms` (Optional[List[str]]) - 平台列表
- `metric_type` (str) - 排序指标，默认`gmv`
- `start_date` (Optional[str]) - 开始日期
- `end_date` (Optional[str]) - 结束日期
- `top_n` (int) - 返回Top N，默认10

**返回**: `pd.DataFrame`

包含列：
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `platform_sku` - 平台SKU
- `product_title` - 产品标题
- `total_value` - 总值（原币种）
- `total_value_rmb` - 总值（RMB）

**示例**:

```python
# 获取Top 10销量产品
top_sales = service.get_top_products(
    metric_type='units_sold',
    start_date='2024-10-01',
    end_date='2024-10-16',
    top_n=10
)

# 显示榜单
for i, row in top_sales.iterrows():
    print(f"{i+1}. {row['product_title']}: {row['total_value']:.0f}件")
```

---

### Catalog查询

#### `get_catalog_status()`

获取Catalog文件状态统计。

**参数**: 无

**返回**: `Dict[str, Any]`

包含键：
- `total` (int) - 总文件数
- `by_status` (List[Dict]) - 按状态分组，格式`[{'status': 'pending', 'count': 100}, ...]`
- `by_domain` (List[Dict]) - 按数据域分组
- `by_platform` (List[Dict]) - 按平台分组

**示例**:

```python
status = service.get_catalog_status()

print(f"总文件数: {status['total']}")

# 显示各状态文件数
for item in status['by_status']:
    print(f"{item['status']}: {item['count']}")
```

---

#### `get_recent_files()`

获取最近处理的文件列表。

**参数**:
- `status` (Optional[str]) - 状态过滤，如`pending`, `ingested`, `failed`
- `limit` (int) - 返回记录数，默认20

**返回**: `pd.DataFrame`

包含列：
- `id` - Catalog文件ID
- `file_name` - 文件名
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `data_domain` - 数据域
- `status` - 状态
- `error_message` - 错误信息
- `first_seen_at` - 首次发现时间
- `last_processed_at` - 最后处理时间

**示例**:

```python
# 获取最近失败的文件
failed_files = service.get_recent_files(status='failed', limit=10)

for _, row in failed_files.iterrows():
    print(f"{row['file_name']}: {row['error_message'][:50]}")
```

---

### 仪表盘服务

#### `get_dashboard_summary()`

获取仪表盘汇总数据（综合多种数据）。

**参数**:
- `platforms` (Optional[List[str]]) - 平台列表
- `days` (int) - 统计天数，默认7

**返回**: `Dict[str, Any]`

包含键：
- `period` (str) - 统计周期，如`近7天`
- `start_date` (str) - 开始日期
- `end_date` (str) - 结束日期
- `order_summary` (List[Dict]) - 订单汇总
- `top_products` (List[Dict]) - Top 5产品
- `catalog_status` (Dict) - Catalog状态

**示例**:

```python
dashboard = service.get_dashboard_summary(
    platforms=['shopee', 'tiktok'],
    days=7
)

print(f"统计周期: {dashboard['period']}")
print(f"订单总数: {len(dashboard['order_summary'])}")
print(f"Top产品数: {len(dashboard['top_products'])}")
```

---

## 缓存服务

### CacheService

三层缓存服务（内存+文件+数据库）。

#### 初始化

```python
from modules.services.cache_service import CacheService

cache = CacheService(cache_dir=Path('temp/cache'))
```

或使用全局单例：

```python
from modules.services.cache_service import get_cache_service

cache = get_cache_service()
```

---

### 基本操作

#### `set(key, value, persist=True)`

设置缓存。

**参数**:
- `key` (str) - 缓存键
- `value` (Any) - 缓存值
- `persist` (bool) - 是否持久化到文件，默认True

**示例**:

```python
cache.set('my_key', {'data': [1, 2, 3]})
```

---

#### `get(key, ttl_seconds=None)`

获取缓存。

**参数**:
- `key` (str) - 缓存键
- `ttl_seconds` (Optional[int]) - 有效期（秒），None表示永不过期

**返回**: 缓存值，不存在或过期返回None

**示例**:

```python
value = cache.get('my_key', ttl_seconds=3600)  # 1小时有效期
```

---

#### `delete(key)`

删除缓存。

**示例**:

```python
cache.delete('my_key')
```

---

#### `clear()`

清空所有缓存。

**示例**:

```python
cache.clear()
```

---

### 装饰器缓存

#### `@cached(ttl_seconds, key_func)`

自动缓存函数结果。

**参数**:
- `ttl_seconds` (Optional[int]) - 缓存有效期，默认3600秒
- `key_func` (Optional[Callable]) - 自定义key生成函数

**示例**:

```python
from modules.services.cache_service import cached

@cached(ttl_seconds=3600)
def expensive_calculation(x: int, y: int) -> int:
    # 昂贵的计算
    return x + y

result = expensive_calculation(1, 2)  # 首次计算
result = expensive_calculation(1, 2)  # 从缓存读取
```

---

### 专用缓存函数

#### 文件Hash缓存

```python
from modules.services.cache_service import cache_file_hash, get_cached_file_hash

# 缓存hash
cache_file_hash(file_path, 'abc123def456')

# 获取缓存
hash_value = get_cached_file_hash(file_path)
```

#### 汇率缓存

```python
from modules.services.cache_service import cache_exchange_rate, get_cached_exchange_rate
from datetime import datetime

# 缓存汇率
cache_exchange_rate('USD', datetime(2024, 10, 16), 7.2)

# 获取缓存
rate = get_cached_exchange_rate('USD', datetime(2024, 10, 16))
```

---

## ETL服务

### CatalogScanner

文件扫描与注册服务。

#### `scan_and_register(paths=None)`

扫描目录并注册文件到catalog。

**参数**:
- `paths` (Optional[Iterable[Path]]) - 扫描目录列表，默认`['data/raw']`

**返回**: `ScanResult`
- `seen` (int) - 扫描的文件数
- `registered` (int) - 新注册的文件数
- `skipped` (int) - 跳过的文件数

**示例**:

```python
from modules.services.catalog_scanner import scan_and_register
from pathlib import Path

result = scan_and_register([Path('data/raw')])

print(f"扫描: {result.seen}, 新注册: {result.registered}")
```

---

### IngestionWorker

数据入库引擎。

#### `run_once(limit, domains, recent_hours, progress_cb)`

执行一次入库操作。

**参数**:
- `limit` (int) - 每批处理文件数，默认20
- `domains` (Optional[List[str]]) - 数据域列表，如`['products', 'orders']`
- `recent_hours` (Optional[int]) - 只处理最近N小时的文件
- `progress_cb` (Optional[Callable]) - 进度回调函数

**返回**: `IngestionStats`
- `picked` (int) - 选取的文件数
- `succeeded` (int) - 成功入库的文件数
- `failed` (int) - 失败的文件数

**示例**:

```python
from modules.services.ingestion_worker import run_once

def progress_callback(cf, stage, msg):
    if stage == 'start':
        print(f"处理: {cf.file_name}")
    elif stage == 'done':
        print(f"✅ 完成")
    elif stage == 'failed':
        print(f"❌ 失败: {msg}")

stats = run_once(
    limit=50,
    domains=['products', 'orders'],
    recent_hours=24,
    progress_cb=progress_callback
)

print(f"成功: {stats.succeeded}, 失败: {stats.failed}")
```

---

### CurrencyService

汇率服务。

#### `get_rate(rate_date, base, quote, use_api=True)`

获取汇率。

**参数**:
- `rate_date` (date) - 汇率日期
- `base` (str) - 基准货币，默认`USD`
- `quote` (str) - 报价货币，默认`CNY`
- `use_api` (bool) - 是否使用API查询，默认True

**返回**: `float` - 汇率

**示例**:

```python
from modules.services.currency_service import get_rate
from datetime import date

rate = get_rate(date(2024, 10, 16), 'USD', 'CNY')
print(f"汇率: {rate}")
```

---

#### `normalize_amount_to_rmb(amount, currency, rate_date)`

将金额标准化为人民币。

**参数**:
- `amount` (float) - 金额
- `currency` (str) - 货币代码，如`USD`, `EUR`
- `rate_date` (date) - 汇率日期

**返回**: `float` - RMB金额

**示例**:

```python
from modules.services.currency_service import normalize_amount_to_rmb
from datetime import date

rmb_amount = normalize_amount_to_rmb(100.0, 'USD', date(2024, 10, 16))
print(f"¥{rmb_amount:.2f}")  # ¥720.00
```

---

## 工具函数

### 便捷查询函数

```python
from modules.services.data_query_service import (
    query_orders,
    query_product_metrics,
    query_catalog_status
)

# 快速查询订单
orders = query_orders(platforms=['shopee'], limit=10)

# 快速查询指标
metrics = query_product_metrics(metric_type='gmv', limit=10)

# 快速查询状态
status = query_catalog_status()
```

---

## 缓存配置

### 环境变量

- `DATABASE_URL` - 数据库连接URL
- `FX_FALLBACK_USD_CNY` - USD->CNY兜底汇率，默认7.0
- `SCAN_WRITE_SIDECAR` - 是否写入sidecar文件，默认0

### 缓存TTL配置

| 数据类型 | TTL | 说明 |
|----------|-----|------|
| Catalog状态 | 60秒 | 变化快 |
| 订单/产品 | 300秒 | 变化慢 |
| 仪表盘汇总 | 600秒 | 综合数据 |
| 汇率 | 7天 | 基本不变 |
| 文件hash | 永久 | 基于mtime失效 |

---

## 错误处理

### 异常类型

所有查询函数在失败时返回空数据而不是抛异常：

```python
try:
    data = service.get_orders()
except Exception:
    # 不会发生，服务内部已处理
    pass

# 正确做法
data = service.get_orders()
if data.empty:
    print("暂无数据")
```

### 超时处理

数据库查询默认30秒超时（SQLite配置）。

---

## 性能优化建议

### 1. 使用缓存

```python
# 好：利用缓存
for _ in range(100):
    status = service.get_catalog_status()  # 第2-100次从缓存

# 避免：频繁清空缓存
st.cache_data.clear()  # 谨慎使用
```

### 2. 合理设置limit

```python
# 好：按需查询
recent_orders = service.get_orders(limit=100)

# 避免：查询全部数据
all_orders = service.get_orders(limit=100000)  # 慢
```

### 3. 使用日期范围

```python
# 好：限定日期范围
orders = service.get_orders(
    start_date='2024-10-01',
    end_date='2024-10-16'
)

# 避免：查询全部历史
all_orders = service.get_orders()  # 慢
```

---

**文档版本**: v1.0  
**最后更新**: 2025-10-16  
**维护者**: ERP开发团队

