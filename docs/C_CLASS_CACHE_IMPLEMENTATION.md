# C类数据缓存策略实现文档

## 概述

本文档记录了C类数据缓存策略的实现，实现了健康度评分、达成率、排名数据的缓存机制，提升系统性能。

## 实现状态

### ✅ 已完成

1. **缓存工具类** (`backend/utils/c_class_cache.py`)
   - ✅ 支持Redis缓存和内存缓存（降级方案）
   - ✅ 健康度评分缓存（5分钟TTL）
   - ✅ 达成率缓存（1分钟TTL）
   - ✅ 排名数据缓存（5分钟TTL）
   - ✅ 缓存统计功能（命中率、请求数等）

2. **缓存集成** (`backend/services/c_class_data_service.py`)
   - ✅ 在`query_health_scores`方法中集成缓存
   - ✅ 在`query_shop_ranking`方法中集成缓存
   - ✅ 查询前先检查缓存，命中则直接返回
   - ✅ 查询后自动缓存结果

3. **缓存失效机制** (`backend/services/event_listeners.py`)
   - ✅ 物化视图刷新后自动失效相关缓存
   - ✅ A类数据更新后自动失效相关缓存
   - ✅ 根据视图类型和数据类型智能失效缓存

4. **缓存管理API** (`backend/routers/store_analytics.py`)
   - ✅ `GET /api/store-analytics/cache/stats` - 获取缓存统计信息
   - ✅ `POST /api/store-analytics/cache/clear` - 清除缓存（支持按类型清除）

## 缓存策略

### 缓存类型和TTL

| 缓存类型 | TTL | 说明 |
|---------|-----|------|
| health_score | 5分钟 | 健康度评分缓存 |
| achievement_rate | 1分钟 | 达成率缓存（更新频繁） |
| ranking | 5分钟 | 排名数据缓存 |

### 缓存key生成规则

缓存key由以下参数生成MD5哈希：
- 缓存类型（health_score/achievement_rate/ranking）
- 查询参数（start_date、end_date、granularity、platform_codes、shop_ids等）

示例：
```
c_class:health_score:a1b2c3d4e5f6g7h8
```

### 缓存失效规则

1. **物化视图刷新后**
   - 销售视图刷新 → 失效达成率和排名缓存
   - 健康度视图刷新 → 失效健康度评分缓存
   - 流量视图刷新 → 失效健康度评分缓存

2. **A类数据更新后**
   - 销售战役/目标更新 → 失效达成率缓存
   - 绩效配置更新 → 失效健康度评分缓存

3. **手动清除**
   - 支持按类型清除（health_score/achievement_rate/ranking）
   - 支持清除所有C类数据缓存

## 使用方法

### 查询数据（自动缓存）

```python
from backend.services.c_class_data_service import CClassDataService

service = CClassDataService(db)

# 查询健康度评分（自动缓存5分钟）
result = service.query_health_scores(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31),
    granularity="daily",
    platform_codes=["shopee"],
    page=1,
    page_size=20
)
```

### 手动清除缓存

```python
from backend.utils.c_class_cache import get_c_class_cache

cache = get_c_class_cache()

# 清除健康度评分缓存
cache.clear_by_type("health_score")

# 清除所有C类数据缓存
cache.clear_all()
```

### 查看缓存统计

```python
from backend.utils.c_class_cache import get_c_class_cache

cache = get_c_class_cache()
stats = cache.get_stats()

print(f"命中率: {stats['hit_rate']}%")
print(f"总请求数: {stats['total_requests']}")
print(f"缓存后端: {stats['cache_backend']}")
```

## API端点

### 获取缓存统计

```http
GET /api/store-analytics/cache/stats
```

响应：
```json
{
  "success": true,
  "data": {
    "hits": 100,
    "misses": 50,
    "sets": 150,
    "deletes": 10,
    "hit_rate": 66.67,
    "total_requests": 150,
    "cache_backend": "redis"
  }
}
```

### 清除缓存

```http
POST /api/store-analytics/cache/clear?cache_type=health_score
```

参数：
- `cache_type`（可选）：缓存类型（health_score/achievement_rate/ranking），如果省略则清除所有缓存

响应：
```json
{
  "success": true,
  "data": {
    "cleared_count": 10,
    "cache_type": "health_score"
  },
  "message": "已清除health_score缓存，数量=10"
}
```

## 性能优化

### 缓存命中率监控

系统会自动记录缓存命中率，可以通过以下方式查看：

1. **API端点**：`GET /api/store-analytics/cache/stats`
2. **日志记录**：缓存操作会记录到日志中（DEBUG级别）

### 缓存降级

如果Redis不可用，系统会自动降级为内存缓存：
- 内存缓存支持相同的API接口
- 缓存统计功能正常工作
- 应用重启后内存缓存会清空

## 配置说明

### Redis配置

Redis连接URL通过环境变量配置：
```bash
REDIS_URL=redis://localhost:6379/0
```

如果未配置或Redis不可用，系统会自动使用内存缓存。

### 缓存TTL配置

缓存TTL在`backend/utils/c_class_cache.py`中配置：

```python
CACHE_TTL = {
    "health_score": 300,  # 5分钟
    "achievement_rate": 60,  # 1分钟
    "ranking": 300,  # 5分钟
}
```

## 相关文档

- [数据流转流程自动化实现文档](docs/DATA_FLOW_AUTOMATION_IMPLEMENTATION.md)
- [C类数据查询策略指南](docs/C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md)
- [API契约标准](docs/API_CONTRACTS.md)

