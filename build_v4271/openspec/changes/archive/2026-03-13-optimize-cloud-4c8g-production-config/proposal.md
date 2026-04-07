# Change: 生产环境 4 核 8G 云服务器资源配置优化

## Why

1. **历史卡死问题**：生产服务器原为 2 核 4G，在 Metabase 执行较重查询时出现过整机卡死、无法登录的情况，根因是 Metabase 与其他服务争抢内存导致 OOM/严重 swap。
2. **服务器已升级**：生产环境已升级为 4 核 8G、SSD 180G、带宽 12Mbps、流量 2000GB/月。需要系统性调整资源配置与限制，避免再次因单服务占满内存而卡死。
3. **配置分散且针对 2 核 4G**：当前 `docker-compose.cloud.yml` 为 2 核 4G 优化；`docker-compose.metabase.yml` 中 Metabase 容器 limit 4G、JVM -Xmx2g，在主栈约 3.5G 基础上叠加后总 limits 约 7.5G，在 8G 机器上几乎无余量；`.env.production` 与 compose 中的 DB_POOL、workers 等存在不一致或未针对 4 核 8G 优化。**注意**：生产环境与采集环境已区分，生产环境不跑采集，本变更仅针对生产环境。

## What Changes

- **Metabase 内存与 JVM 限制**：将 Metabase 容器 memory limit 从 4G 降至 2G，JVM `-Xmx2g -Xms1g` 改为 `-Xmx1g -Xms512m`（通过 override 或修改 metabase compose）。
- **4 核 8G Compose 覆盖**：新增 `docker-compose.cloud-4c8g.yml` 或类似 override，在保持总 limits ≤ 约 6.5–7G 的前提下，backend workers 推荐 `--workers 3`（4 核下预留 1 核给 Metabase/Postgres）；**Celery**：生产环境不跑采集，celery-worker 仅用于定时任务（备份、告警等），4c8g overlay 可维持 concurrency=2 或适度放宽至 3，不强求与采集环境一致。
- **.env.production 与服务器 .env 统一**：
  - 实施者更新 `env.production.example`（可提交的模板）及 CLOUD_4C8G_REFERENCE 中的变量清单；**因 `.env.production` 在 .gitignore 中**，部署者将新变量合并进本地 `.env.production`（含敏感信息，不提交），再将其内容复制到云端服务器的 `.env`（默认 `PRODUCTION_PATH/.env`，通常 `/opt/xihong_erp/.env`）。`.env.production` 内容与云端 `.env` 保持一致。
  - 增加 `RESOURCE_MONITOR_ENABLED=true`、`RESOURCE_MONITOR_MEMORY_THRESHOLD=85` 等，显式启用资源监控。
  - 可选：`CPU_EXECUTOR_WORKERS`（容器限 1 核时建议 1）。**不增加** `MAX_COLLECTION_TASKS`：生产环境不跑采集，该变量仅采集环境使用；文档中说明此区分，避免混淆。
- **Redis 强化**（短期优化重点）：
  - 显式配置 `maxmemory=220m`、`maxmemory-policy=volatile-lru`（仅淘汰带 TTL 的 key，保护 Celery broker）；文档说明 220M 容量评估及 volatile-lru 与 allkeys-lru 的选择理由；**注意**：Celery result 有 TTL，volatile-lru 在内存紧张时可能淘汰 result key，生产 Celery 以定时任务为主，可接受。
  - CacheService 中 `delete_pattern` 与 `maintenance_service.clear_cache` 均改为使用 SCAN 替代 KEYS，避免 O(N) 阻塞。
  - 在 `/api/system/maintenance/cache/status` 中增加 CacheService 命中率字段（hits、misses、hit_rate；多 worker 下为单 worker 采样值）。
  - 可选：Celery 配置 `result_expires=86400`（24 小时），控制 result 占用 Redis。
  - 在文档中说明 Cache TTL 与 key 设计对前端数据新鲜度与 Metabase/DB 压力的平衡（现有 CacheService 已对 Dashboard KPI、对比、店铺赛马等使用 180–300s TTL）。
- **连接池强化**：
  - 4c8g 下在 `.env.production` 或文档中明确推荐：`DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`，确保 Backend 有足够连接应对 50 人以上并发；文档中说明与 Postgres `max_connections` 的对应关系。
- **慢查询监控**：
  - 生产 Postgres 需配置 `shared_preload_libraries=pg_stat_statements`、`log_min_duration_statement=1000`（需 command 或 postgresql.conf 并**重启 Postgres**）；启用时应在维护窗口执行；`docker/postgres/init_monitoring.sql` 中的 `v_top_slow_queries` 需 DBA 手动执行或加入 `sql/init`；CLOUD_4C8G_REFERENCE 中说明配置步骤、定期查看方式及 Postgres 重启影响；部署清单增加「慢查询监控已启用」检查项。
- **数据流文档**：在 `docs/deployment/` 或架构文档中补充**实际数据流**：PostgreSQL ← Metabase（查询）→ Backend（调用 Metabase API）→ Redis（Backend 写入/读取缓存）→ Backend → 前端（前端仅调用 Backend API，不直接访问 Redis）。明确 Backend 是 Metabase 与 Redis 之间的中介。
- **部署脚本与 overlay 加载**：当前 `deploy_remote_production.sh` **不会**自动加载 `cloud-4c8g.yml`、`metabase.4c8g.yml`。4 核 8G 用户需**二者择一**：（A）在 deploy 脚本中增加条件加载（如 `CLOUD_PROFILE=4c8g` 时追加 overlay），或（B）不使用 deploy 脚本，手动执行 compose 命令并追加 overlay。文档中必须明确此要求，否则 Metabase 限制不会生效。
- **CI/CD 同步**：`.github/workflows/deploy-production.yml` 当前仅 SCP 同步 `yml`、`prod`、`cloud`、`metabase`，**不包含** `cloud-4c8g`、`metabase.4c8g`。需在 Sync compose files 步骤中增加对这两个文件的 SCP 同步。**⚠️ 关键**：tag 部署或手动部署完成后，deploy 脚本**不会**自动加载 4c8g overlay；4 核 8G 用户**必须**按 CLOUD_4C8G_REFERENCE 手动追加 overlay 或配置 CLOUD_PROFILE，否则 Metabase 仍为 4G limit，限制不生效；部署清单须含「4c8g overlay 已加载」检查项。
- **文档**：在 `docs/deployment/` 下新增 `CLOUD_4C8G_REFERENCE.md`（或等价），补充「4 核 8G 生产环境推荐配置」「**完整 compose 命令示例**（含 overlay 顺序）」「Metabase 导致卡死应急处置」「compose overlay 加载顺序与 deploy 脚本说明」「慢查询监控启用与检查」等。
- **范围说明**：本变更为短期优化，**不**包含 Metabase 单独部署；Metabase 与主栈继续同机运行。
- **Backend→Metabase 超时**：当前 `MetabaseQuestionService` 已配置 `httpx.AsyncClient(timeout=60.0)`，60 秒超时。CLOUD_4C8G_REFERENCE 中说明此值，并注明：若 Metabase 查询经常超时，可调整或按 Question 区分超时。

## Future Considerations（后续可选优化）

以下为符合业界主流的优化方向，**不包含在本变更范围**，可作为后续 OpenSpec 变更或 CLOUD_4C8G_REFERENCE 进阶章节：

| 优先级 | 优化项 | 说明 |
|--------|--------|------|
| P1 | Backend 对 Metabase 健康检查/熔断 | Metabase 不可用时快速失败，避免 API 长时间 hang |
| P1 | 前端 Dashboard 超时与错误提示 | 与 45s 超时、错误文案一致，避免用户无感知等待 |
| P1 | RESOURCE_MONITOR 告警对接 | 阈值触发后对接钉钉/邮件/Webhook，运维可感知 |
| P2 | Redis 与 Celery 分离 | `REDIS_URL` 与 `CELERY_BROKER_URL` 指向不同 Redis 实例，各自调优逐出策略 |
| P2 | 缓存预热 | 启动时或定时预热 Dashboard KPI 等热点，减轻首访 Metabase 压力 |
| P2 | 写时失效 | 数据变更时主动 delete 相关 cache key，提升数据新鲜度 |
| P3 | Metabase 单独部署 | 访问量增大时迁移到独立 2c4g 机器，资源隔离 |
| P3 | Postgres statement_timeout | 应用层或 Metabase 配置，限制单查询执行时间 |
| P3 | Metabase Guest embedding 评估 | OSS 免费版支持 Guest embedding（web component）；**仅适合单一独立报表页**（如全屏销售趋势图），**不适合**业务概览等多维度数据集成、多业务筛选的页面；后者应继续使用 Metabase API + 自定义布局 |

## Capabilities

### New Capabilities

- 无新能力；本变更为部署与运维配置优化。

### Modified Capabilities

- `deployment-ops`：ADDED 生产环境云服务器资源配置要求（4 核 8G 下的 Metabase 限制、compose override、.env 变量与文档约定）。

## Impact

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| Compose | 新建 `docker-compose.metabase.4c8g.yml` | Metabase 容器 memory limit 2G，JVM -Xmx1g -Xms512m |
| Compose | 新建 `docker-compose.cloud-4c8g.yml` | backend workers 3；**backend environment** 覆盖 `DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`（因 prod 固定 20/40，.env 会被 compose environment 覆盖）；celery concurrency 维持 2 或放宽至 3；**Redis** 覆盖 command 为 `redis-server --appendonly yes --requirepass ... --maxmemory 220mb --maxmemory-policy volatile-lru`；**可选** postgres command 覆盖以启用慢查询监控；各服务 limits 适配 4 核 8G |
| 代码 | `backend/services/cache_service.py` | `delete_pattern` 使用 SCAN 替代 KEYS |
| 代码 | `backend/services/maintenance_service.py` | `clear_cache` 中按模式删除时使用 SCAN 替代 `r.keys(pattern)` |
| API | `/api/system/maintenance/cache/status` | 增加 CacheService 命中率字段（hits、misses、hit_rate；多 worker 下为单 worker 采样）；需同步修改 `backend/schemas/maintenance.py` 中的 `CacheStatusResponse`，新增上述字段 |
| 配置 | `env.production.example`、CLOUD_4C8G_REFERENCE | 更新 `env.production.example`（及若使用则同步 `env.production.cloud.example`）；4c8g 变量清单（RESOURCE_MONITOR_*、DB_POOL_SIZE=30、DB_MAX_OVERFLOW=30）；**不配置** MAX_COLLECTION_TASKS；部署者合并到本地 `.env.production` 后复制到云端 `.env`（`PRODUCTION_PATH/.env`） |
| CI/CD | `.github/workflows/deploy-production.yml` | **必须**：在 **deploy-tag** 与 **deploy-manual** 两个 job 的 Sync compose files 步骤中，均增加对 `docker-compose.cloud-4c8g.yml`、`docker-compose.metabase.4c8g.yml` 的 SCP 同步，否则 tag 发布或手动部署后 4c8g overlay 不会出现在服务器 |
| 部署脚本 | `scripts/deploy_remote_production.sh` | 可选：增加 `CLOUD_PROFILE=4c8g` 时加载 cloud-4c8g、metabase.4c8g；**否则**文档必须说明 4 核 8G 用户需手动追加 overlay，否则 Metabase 限制不生效 |
| 文档 | `docs/deployment/CLOUD_4C8G_REFERENCE.md` | 4 核 8G 推荐配置、应急处置、compose overlay 顺序；**⚠️ 首次部署后必做**：4c8g 用户须手动追加 overlay 或 CLOUD_PROFILE；数据流；Redis 角色与 volatile-lru/Celery result 权衡；慢查询监控（含 Postgres 重启、维护窗口）；维护 API 风险；部署清单含「4c8g overlay 已加载」检查项 |
