# Change: 未缓存重查询接口接入 Redis 缓存

## Why

当前除业务概览 Dashboard 外，部分**重查询接口**（调用 Metabase 或复杂 DB 聚合）**未使用 Redis 缓存**，每次请求均直打 Metabase/PostgreSQL。在多人并发或重复打开同一页面时存在：

1. **延迟**：首请求或缓存未命中时响应慢，易触及前端 timeout（如 45s），影响体验。
2. **并发压力**：绩效、HR 店铺/年度统计、费用汇总等被多次请求时，压力集中在 Metabase/DB，可能拖慢整体系统。
3. **一致性**：与已有 Dashboard 缓存策略不一致，不利于运维与可观测（如 X-Cache: HIT）。

需要为这些未缓存的重查询接口接入 Redis 缓存，提升系统运作效率，避免延迟和并发对系统运作的影响。

## What Changes

### 1. 优先接入缓存的接口（P0）

与现有 `dashboard_api` 一致：先 `cache_service.get(cache_type, **params)`，命中则返回（可带 `X-Cache: HIT`）；未命中则执行查询后 `cache_service.set(...)`。Redis 不可用时降级为直接查询，不阻塞接口。

| 模块 | 接口 | 缓存 key 依据 | 建议 TTL |
|------|------|----------------|----------|
| **performance_management** | `GET /performance/scores` | period, platform 等请求参数 | 180s |
| **performance_management** | `GET /performance/scores/{shop_id}` | period, shop_id 等 | 180s |
| **hr_management** | `GET /shop-profit-statistics` | month | 300s |
| **hr_management** | `GET /annual-profit-statistics` | year | 300s |

### 2. 可选接入（P1，视慢查询与并发情况）

| 模块 | 接口 | 缓存 key 依据 | 建议 TTL |
|------|------|----------------|----------|
| **expense_management** | `GET /summary/monthly` | 月份、筛选参数 | 300s |
| **expense_management** | `GET /summary/yearly` | 年份、筛选参数 | 300s |
| **target_management** | `GET /by-month` | 月份、店铺等 | 180s |
| **target_management** | `GET /{target_id}/breakdown` | target_id、查询参数 | 180s |

### 3. 技术约定

- **CacheService**：在 `backend/services/cache_service.py` 的 `DEFAULT_TTL` 中新增上述缓存类型及 TTL。
- **参数规范化**：各路由对查询参数做规范化（如 None→空字符串、排序）后参与 cache key，与 `dashboard_api._normalize_cache_params` 模式一致。
- **仅缓存成功响应**：异常或 4xx/5xx 不写入缓存。
- **降级**：`request.app.state.cache_service` 不存在或 get 返回 None 时，直接执行原逻辑。

## Impact

### 受影响的规格

- **dashboard**（或基础设施）：MODIFIED - 扩展 Redis 缓存覆盖至绩效、HR 统计等重查询接口（与现有 Dashboard 缓存策略一致）。

### 受影响的代码

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| 后端 | `backend/services/cache_service.py` | DEFAULT_TTL 新增 performance_scores、performance_scores_shop、hr_shop_profit_statistics、hr_annual_profit_statistics（及可选 expense_*、target_*） |
| 后端 | `backend/routers/performance_management.py` | GET /scores、GET /scores/{shop_id} 增加缓存读写，参数规范化 |
| 后端 | `backend/routers/hr_management.py` | GET /shop-profit-statistics、GET /annual-profit-statistics 增加缓存读写 |
| 后端 | `backend/routers/expense_management.py` | （可选）GET /summary/monthly、/summary/yearly 增加缓存读写 |
| 后端 | `backend/routers/target_management.py` | （可选）GET /by-month、GET /{id}/breakdown 增加缓存读写 |

### 依赖关系

- 依赖现有 Redis 与 `CacheService`（与 Dashboard 缓存一致）；无 Redis 时自动降级，无前置新依赖。

## 非目标（Non-Goals）

- 不修改前端调用逻辑与超时时间；仅后端缓存。
- 不新增 Metabase Question 或业务指标。
- 不在此变更内调整 Gunicorn workers 或 DB 连接池（已有归档变更可参考）。

## 成功标准

- P0 接口在相同参数下 TTL 内二次请求可命中缓存，响应带 X-Cache: HIT（或实现一致的可观测方式）。
- Redis 不可用时，上述接口仍可正常返回（降级直查）。
- 仅成功响应写入缓存，异常不写入。
