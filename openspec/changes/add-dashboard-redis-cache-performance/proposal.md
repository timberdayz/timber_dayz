# Change: 业务概览 Dashboard 性能优化 - Redis 缓存与并发支撑

## Why

当前业务概览（Business Overview）的 KPI、数据对比、店铺赛马、流量排名等接口**无缓存**，每次请求均直接调用 Metabase → PostgreSQL。在 50~100 人同时使用时，存在以下瓶颈：

1. **重复查询**：同一参数（如相同月份、粒度）被多次执行，Metabase 与 PostgreSQL 压力大
2. **Workers 不足**：Gunicorn 2 workers 在高并发下易排队
3. **中心化入口**：Metabase 作为唯一查询入口，大量并发集中于单点

需要优化以稳定支持 50~100 人并发查询与文件上传下载。

## What Changes

### 核心变更

1. **Dashboard 接口 Redis 缓存（P0）**
   - 对 `/api/dashboard/business-overview/*` 各接口按「查询参数」做 Redis 缓存
   - 缓存 Key 基于 `cache_type + params` 生成，TTL 1~5 分钟
   - 复用现有 `CacheService`，新增 `dashboard_*` 缓存类型
   - Redis 不可用时自动降级为直接查询（与 accounts_list 一致）

2. **Gunicorn Workers 调整（P1，可选，视资源配置）**
   - **2 核 4G**：保持 workers=2，主要依赖 Redis 缓存减轻负载
   - **4 核 8G 及以上**：可调整为 4~5（公式 2*CPU+1）
   - 配置可通过 docker-compose 或环境变量覆盖

3. **PostgreSQL 连接池（P2，可选）**
   - 通过 `docker-compose` 或 `.env` 设置 `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`
   - 确保 `workers × (pool_size + max_overflow)` 不超过 PostgreSQL max_connections

### 技术细节

- **缓存接口与 TTL**：
  | 接口 | 缓存 Key 依据 | TTL |
  |------|---------------|-----|
  | KPI | month, platform | 180s |
  | 数据对比 | granularity, date, platforms, shops | 180s |
  | 店铺赛马 | granularity, date, group_by, platforms | 180s |
  | 流量排名 | granularity, dimension, date_value, platforms, shops | 180s |
  | 经营指标 | month, platform | 180s |
  | 清仓排名 | start_date, end_date, platforms, shops, limit | 300s |
  | 库存积压 | days, platforms, shops | 300s |

- **降级策略**：Redis 不可用时，CacheService 返回 None，路由直接调用 Metabase，行为与当前一致

## Impact

### 受影响的规格

- **dashboard**：ADDED - Dashboard API 查询缓存
- **deployment-ops**：ADDED - 并发支撑配置（Gunicorn workers、连接池）

### 受影响的代码

| 文件 | 修改内容 |
|------|----------|
| `backend/services/cache_service.py` | 新增 `dashboard_*` 缓存类型与 TTL |
| `backend/routers/dashboard_api.py` | 各路由注入 Request、增加缓存读写逻辑 |
| `docker-compose.cloud.yml` | 可选：Gunicorn `--workers`、连接池环境变量 |

### 非目标（Non-Goals）

- 不实现 Metabase 独立部署或只读副本（后续单独 change）
- 不修改前端调用逻辑，仅后端优化
- 不引入新的业务指标或 Question

## 成功标准

- [ ] 业务概览各 Dashboard 接口支持 Redis 缓存，相同参数在 TTL 内命中缓存
- [ ] 仅缓存成功响应，错误/异常不写入缓存
- [ ] Redis 不可用时，接口仍可正常工作（降级为直接查询）
- [ ] 2 核 4G 环境下 workers 保持 2，不增加 OOM 风险
- [ ] 在 50 人并发下，接口响应时间与错误率可接受（可通过压测验证）
