## Context

生产环境原为 2 核 4G 云服务器，使用 `docker-compose.cloud.yml` 优化配置；Metabase 通过 `docker-compose.metabase.yml` 独立加载。在 Metabase 执行较重 SQL 查询时发生过整机卡死，根因是 Metabase（limit 4G、JVM -Xmx2g）与主栈（约 3.5G limits）叠加后逼近或超过 8G 机器内存，引发 OOM/swap。服务器已升级为 4 核 8G，需要系统性调整资源限制与 .env 配置。

## Goals / Non-Goals

**Goals:**
- 限制 Metabase 单容器内存与 JVM 堆，防止再次占满整机
- 为 4 核 8G 生产环境提供专用 compose override（backend workers、celery concurrency 适度放宽；生产不跑采集）
- 统一 .env.production 与服务器 .env 中的资源相关变量（RESOURCE_MONITOR_* 等；不包含 MAX_COLLECTION_TASKS，生产不跑采集）
- 补充文档：4 核 8G 推荐配置、Metabase 导致卡死的应急处置
- 强化 Redis 配置与 CacheService，提升缓存命中率、降低阻塞
- 明确 4c8g 下连接池推荐值，支持 50 人以上并发
- 确保生产启用慢查询监控，便于排查性能问题

**Non-Goals:**
- 不修改 PostgreSQL 内部参数（shared_buffers、work_mem 等）— 应用层 connect_args 已有 statement_timeout
- 不调整 Nginx worker_connections
- 不改变现有 2 核 4G 的 cloud.yml 默认行为（保持兼容，4 核 8G 通过 overlay 覆盖）
- **不单独部署 Metabase**（短期保持与主栈同机；后续可另行规划）
- 不实现 Backend 对 Metabase 的健康检查/熔断（可后续变更）
- 不实现 Redis 与 Celery 分离（可后续变更）
- 不实现缓存预热、写时失效（可后续变更）
- 不评估或引入 Metabase Guest embedding（可后续与产品确认后规划；**注意**：Guest embedding 仅适合单一报表页，不适合业务概览等多维度集成 + 多业务筛选场景）

**Future Considerations（后续可选优化）：**
- Backend→Metabase 超时：当前 60s，CLOUD_4C8G_REFERENCE 中说明；若需调整可改 `MetabaseQuestionService` 的 httpx timeout
- RESOURCE_MONITOR 告警对接：显式启用后，对接钉钉/邮件/Webhook 需后续实施

## Decisions

### 1. Metabase 内存限制方式

- **方案 A**：直接修改 `docker-compose.metabase.yml` 将 limit 4G 改为 2G、JAVA_OPTS 改为 -Xmx1g -Xms512m。
- **方案 B**：新建 `docker-compose.metabase.4c8g.yml` override，只覆盖 Metabase 的 environment 与 deploy.resources。

**选择**：方案 B。理由：保持 metabase.yml 为默认配置，4 核 8G 通过 overlay 叠加，便于不同规格服务器复用同一套 base 配置；且 2 核 4G 用户若误加载 metabase 也可避免单服务占满。

### 2. 主栈 4 核 8G override 形式

- **方案 A**：新建 `docker-compose.cloud-4c8g.yml`，覆盖 backend command（**推荐 `--workers 3`**，4 核下预留 1 核给 Metabase/Postgres）、**backend environment**（`DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`，因 `docker-compose.prod.yml` 固定 20/40，compose 的 environment 会覆盖 .env）、celery-worker command（concurrency 维持 2 或放宽至 3，生产不跑采集），可适度放宽 postgres/backend limits（在总内存 ≤ 约 7G 前提下）。
- **方案 B**：直接修改 `docker-compose.cloud.yml` 头部注释与 limits/commands，标明「4 核 8G 优化」。

**选择**：方案 A。理由：cloud.yml 明确针对 2 核 4G，4 核 8G 单独 overlay 更清晰；**DB_POOL 必须在 overlay 中覆盖**，否则 .env 中 DB_POOL_SIZE=30 无法生效（compose environment 覆盖 env_file）。

### 3. 部署脚本如何加载 4c8g overlay

- **方案 A**：在 `deploy_remote_production.sh` 中根据环境变量（如 `CLOUD_PROFILE=4c8g`）或检测逻辑自动加载 cloud-4c8g、metabase.4c8g。
- **方案 B**：不在脚本中自动加载，仅通过文档说明：4 核 8G 用户需手动在 compose 命令中追加 `-f docker-compose.cloud-4c8g.yml -f docker-compose.metabase.4c8g.yml`（**加载顺序**：cloud-4c8g 须在 cloud 之后、metabase-4c8g 须在 metabase 之后，才能正确覆盖）。

**选择**：方案 B。理由：避免脚本复杂度与误判；文档中**必须**明确 4 核 8G 用户若不手动追加 overlay，则 Metabase 限制不会生效（deploy 脚本当前不加载 4c8g overlay）。**若实现方案 A**：overlay 插入顺序须为 `cloud.yml` → `cloud-4c8g.yml` → `deploy.yml` → `metabase.yml` → `metabase-4c8g.yml`，才能正确覆盖。

### 4. MAX_COLLECTION_TASKS 与生产环境

- **现状**：生产环境与采集环境已区分；**生产环境不跑采集**，`MAX_COLLECTION_TASKS` 仅采集环境使用。
- **决策**：**不在** .env.production 中增加 `MAX_COLLECTION_TASKS`；在文档中说明该变量仅采集环境使用，生产环境无需配置，避免混淆。

### 5. RESOURCE_MONITOR 显式配置

- **决策**：在 .env.production 中显式设置 `RESOURCE_MONITOR_ENABLED=true`、`RESOURCE_MONITOR_MEMORY_THRESHOLD=85`（及可选 CPU_THRESHOLD、CHECK_INTERVAL），便于运维调参与告警对接。

### 6. Celery 在生产环境中的定位

- **现状**：生产环境与采集环境已区分；生产不跑 Playwright 采集，celery-worker 主要用于定时任务（备份、告警、数据入库等）。
- **决策**：4c8g overlay 中 celery concurrency 维持 2 或适度放宽至 3；不强求与采集环境一致的 3–4。生产以查询/看板为主，Celery 负载较轻。

### 7. Redis 配置与数据流说明

- **现状**：Redis 承担 Celery broker、result backend、限流存储、Dashboard/重查询缓存（CacheService）。当前 limit 256M，未显式配置 maxmemory、eviction。
- **决策**：
  - 推荐：在 Redis 容器 command 中显式设置 `maxmemory=220m`、`maxmemory-policy=volatile-lru`（见 Decision 8）；文档中说明 Redis 角色与 220M 容量评估。
  - **数据流文档**：在部署/架构文档中补充实际链路：PostgreSQL ← Metabase（查询）→ Backend（调用 Metabase API）→ Redis（Backend 写入/读取缓存）→ Backend → 前端。前端仅调用 Backend API，不直接访问 Redis；Backend 是 Metabase 与 Redis 之间的中介。

### 8. Redis 驱逐策略

- **问题**：`allkeys-lru` 在内存紧张时可能淘汰 Celery broker 的 key（通常无 TTL），导致任务队列异常。
- **选择**：使用 `volatile-lru`，仅淘汰设置了 TTL 的 key。业务缓存（CacheService）均有 TTL；Celery broker 通常无 TTL，可避免误伤；**注意**：Celery result 有 `result_expires`（如 3600 或 86400），带 TTL，内存紧张时 `volatile-lru` 可能淘汰 result key，导致任务完成但取不到结果；生产环境 Celery 主要用于定时任务，任务状态可查 DB/进度表，接受该风险。

### 9. CacheService delete_pattern 与 maintenance_service.clear_cache

- **问题**：`CacheService.delete_pattern` 与 `maintenance_service.clear_cache` 均使用 `KEYS pattern`，在大 key 集合下 O(N) 阻塞 Redis，生产环境风险高。
- **选择**：二者均改用 `SCAN` 游标迭代，分批删除，避免阻塞。
- **范围**：本变更仅覆盖 CacheService 与 maintenance_service。`backend/utils/redis_client.clear_cache`、`backend/utils/c_class_cache` 中同样使用 `KEYS`，若在生产中按 pattern 清理也会阻塞；不在本次范围内，可后续单独变更。

### 10. Redis 配置落地位置

- **选择**：在 `docker-compose.cloud-4c8g.yml` 中增加 redis 服务的 `command` override，完整覆盖为 `redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-redis_pass_2025} --maxmemory 220mb --maxmemory-policy volatile-lru`（继承 prod 的 appendonly、requirepass，追加 maxmemory 与 eviction）。
- **实施前**：核对 `docker-compose.prod.yml`、`docker-compose.cloud.yml` 中 redis 的 command，确保 overlay 覆盖后不丢失 prod 已有参数。

### 11. 慢查询监控

- **现状**：`docker/postgres/init_monitoring.sql` 含 `pg_stat_statements` 与 `v_top_slow_queries`，但 Postgres 仅挂载 `sql/init`，该文件**不会**自动加载；且 `pg_stat_statements` 需 `shared_preload_libraries` 并**重启 Postgres** 才生效。官方 postgres 镜像无 shared_preload 环境变量，需通过 command 或 postgresql.conf 传入。
- **选择**：（1）在 `docker-compose.cloud-4c8g.yml` 中**可选**增加 postgres 的 `command` override：`postgres -c shared_preload_libraries=pg_stat_statements -c log_min_duration_statement=1000`，或仅在 CLOUD_4C8G_REFERENCE 中给出可复制的 command/挂载 conf 示例；（2）`init_monitoring.sql` 需 DBA 手动执行或加入 `sql/init`；（3）配置后需**重启 Postgres**，文档中注明应在维护窗口执行；（4）部署清单增加「慢查询监控已启用」检查项（可人工检查 `SHOW shared_preload_libraries` 等）。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| volatile-lru 可能淘汰 Celery result key | Celery result 有 TTL，volatile-lru 会淘汰；生产 Celery 以定时任务为主，任务状态可查 DB/进度表；CLOUD_4C8G_REFERENCE 中说明此权衡 |
| Metabase 2G limit 下复杂查询可能变慢 | 2G 对中小数据量通常够用；重度分析建议迁移到独立 BI 实例或专用服务器 |
| 用户未按文档加载 4c8g overlay | CLOUD_4C8G_REFERENCE.md 中提供**完整 compose 命令示例**（含 overlay 顺序）；CLAUDE.md/部署清单中增加 4 核 8G 检查项；**首次部署后必做步骤**：追加 overlay 或配置 CLOUD_PROFILE |
| 4c8g overlay 文件未随部署同步到服务器 | 在 `.github/workflows/deploy-production.yml` 的 Sync compose files 步骤中增加对 `docker-compose.cloud-4c8g.yml`、`docker-compose.metabase.4c8g.yml` 的 SCP 同步；部署清单中明确列出需同步的 compose 文件 |
| maintenance clear_cache 无 pattern 时 flushdb | `maintenance_service.clear_cache` 在 cache_type=all/redis 且无 pattern 时使用 flushdb，会清空整个 Redis DB（含 Celery broker/result）。CLOUD_4C8G_REFERENCE 中**明确标注**：生产环境仅在有 pattern 时清理；无 pattern 的「清空全部」需二次确认或权限控制 |

## Migration Plan

1. 新建 `docker-compose.cloud-4c8g.yml`、`docker-compose.metabase.4c8g.yml`，提交到仓库。
2. 在 `docker-compose.cloud-4c8g.yml` 中增加 backend environment（DB_POOL_SIZE=30、DB_MAX_OVERFLOW=30）、redis 的 command override（完整命令含 maxmemory、volatile-lru）；可选：postgres command override 以启用慢查询监控。
3. 修改 `backend/services/cache_service.py`：`delete_pattern` 改用 SCAN 替代 KEYS；修改 `backend/services/maintenance_service.py`：`clear_cache` 按模式删除时改用 SCAN 替代 KEYS。
4. 在 `/api/system/maintenance/cache/status` 中增加 CacheService 命中率（hits、misses、hit_rate；多 worker 下为单 worker 采样）。
5. 更新 `env.production.example`（可提交）及 CLOUD_4C8G_REFERENCE 中的 4c8g 变量清单：RESOURCE_MONITOR_*、DB_POOL_SIZE=30、DB_MAX_OVERFLOW=30；不增加 MAX_COLLECTION_TASKS。**说明**：`.env.production` 在 .gitignore，实施者更新模板；部署者合并到本地 `.env.production`，复制到云端 `.env`（默认 `PRODUCTION_PATH/.env`）。新建 `docs/deployment/CLOUD_4C8G_REFERENCE.md`（含慢查询启用与检查说明）。
6. 更新 `.github/workflows/deploy-production.yml`：在 **deploy-tag** 与 **deploy-manual** 两个 job 的 Sync compose files 步骤中，均增加对 `docker-compose.cloud-4c8g.yml`、`docker-compose.metabase.4c8g.yml` 的 SCP 同步。
7. 在 4 核 8G 生产服务器上，**按顺序**：（1）将 `.env.production` 内容复制到云端 `.env`（`PRODUCTION_PATH/.env`，默认 `/opt/xihong_erp/.env`）；（2）拉取新 compose 文件；（3）按文档追加 overlay（cloud-4c8g、metabase.4c8g）到 compose 命令；（4）重启服务。
8. 可选：在 `backend/celery_app.py` 中配置 `result_expires=86400`（24 小时）。
9. 回滚：移除 overlay 参数、恢复原 compose 命令即可；必要时恢复 .env 中的资源变量。

## Open Questions

- 是否需要通过环境变量（如 `CLOUD_PROFILE=4c8g`）在 deploy 脚本中自动选择 overlay？当前倾向仅文档指引。
