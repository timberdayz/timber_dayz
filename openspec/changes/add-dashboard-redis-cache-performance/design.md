# Design: Dashboard Redis 缓存与并发支撑

## Context

- 业务概览通过 Metabase Question API 查询数据，后端 `dashboard_api.py` 作为代理调用 `MetabaseQuestionService`
- 现有 `CacheService` 已用于 `accounts_list`、`component_versions` 等，支持 Redis 与降级
- 当前部署：2 核 4G 云服务器，Gunicorn 2 workers，PostgreSQL 连接池默认配置

## Goals / Non-Goals

**Goals:**
- 相同查询参数在 TTL 内复用 Redis 缓存，减轻 Metabase/PostgreSQL 压力
- 提升 50~100 人并发下的稳定性

**Non-Goals:**
- 不改造 Metabase 架构（独立部署、只读副本）
- 不引入前端缓存

## Decisions

### 1. 缓存策略：按参数缓存

- **决策**：缓存 Key = `cache_type:params_hash`，与 `accounts_list` 一致
- **理由**：不同用户查询相同参数（如 2025-01、月度）应共享缓存，命中率高
- **备选**：按用户 ID 隔离缓存 → 命中率低，不采用

### 2. TTL 设置

- **决策**：KPI/对比/赛马/流量/经营指标 180s，清仓/库存积压 300s
- **理由**：业务数据非实时，3~5 分钟可接受；清仓/积压变化较慢，可更长

### 3. 仅缓存成功响应

- **决策**：仅当 Metabase 返回成功结果时写入缓存；4xx/5xx、超时、异常不缓存
- **理由**：业界惯例，避免错误响应被缓存放大；符合 [RFC 7234](https://datatracker.ietf.org/doc/html/rfc7234) 对缓存语义的建议

### 4. 缓存 Key 参数规范化

- **决策**：写入缓存前，将 params 规范化（如 None→空字符串、日期格式统一），确保语义相同请求生成相同 Key
- **理由**：避免 `month=2025-01&platform=None` 与 `month=2025-01` 生成不同 Key 导致重复缓存

### 5. 降级策略

- **决策**：Redis 不可用时，`CacheService.get` 返回 None，路由直接调用 Metabase
- **理由**：与现有 accounts_list 逻辑一致，无额外实现

### 6. 缓存接入方式

- **决策**：在每个路由内显式调用 `cache_service.get/set`，不引入装饰器
- **理由**：dashboard 参数多样，装饰器需处理参数序列化，显式调用更清晰；后续可抽象为装饰器
- **实现**：路由需注入 `Request` 以访问 `request.app.state.cache_service`（与 `collection.py` 一致）

### 7. Gunicorn Workers（资源分级）

- **2 核 4G**：保持 workers=2。5 workers 约 750MB~1G，易 OOM；缓存是主要优化手段
- **4 核 8G 及以上**：可调至 4~5（2*CPU+1）
- **理由**：遵循 [Twelve-Factor App](https://12factor.net/processes) 进程模型，按资源配置选择 worker 数

### 8. 连接池

- **决策**：通过环境变量 `DB_POOL_SIZE`、`DB_MAX_OVERFLOW` 配置，不修改 `database.py` 代码
- **约束**：`workers × (pool_size + max_overflow)` 须小于 PostgreSQL `max_connections`
- **2 核 4G 建议**：保持现有 pool_size=10、max_overflow=20

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 缓存导致数据延迟 | TTL 3~5 分钟，业务可接受；可提供手动刷新入口（后续） |
| Redis 内存占用 | 单条缓存通常 <100KB，7 类接口 * 若干参数组合，预估 <50MB |
| 2 核 4G 资源紧张 | 保持 workers=2，主要依赖 Redis 缓存减轻负载 |

## Migration Plan

1. 部署时无需数据迁移
2. **回滚步骤**：① 若曾修改 workers，改回 `--workers 2`；② 移除 `dashboard_api.py` 中各路由的 cache get/set 逻辑及 Request 依赖；③ 重启 backend 容器

## 业界主流设计对照

| 实践 | 本方案 | 业界参考 |
|------|--------|----------|
| 读多写少 API 缓存 | Redis + TTL | [Cache-Aside](https://docs.aws.amazon.com/AmazonElastiCache/latest/mem-ug/Strategies.html)，常见于报表/看板场景 |
| 仅缓存成功响应 | 4xx/5xx 不缓存 | [RFC 7234](https://datatracker.ietf.org/doc/html/rfc7234) 缓存语义；避免错误放大 |
| 缓存 Key 基于请求参数 | `cache_type:params_hash` | 参数化缓存，命中率高；与 Stripe、GitHub API 等一致 |
| Redis 不可用降级 | 跳过缓存，直接查源 | 高可用设计；[Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html) 思想 |
| Worker 数量 | 2核4G 保持 2；4核8G 可 4~5 | [Twelve-Factor processes](https://12factor.net/processes)；按资源配置伸缩 |
| 连接池约束 | workers × (pool+overflow) < max_conn | PostgreSQL 官方建议；避免连接耗尽 |

## Open Questions

- 是否需要提供「强制刷新」API 或管理端清除缓存能力？（建议后续迭代）
