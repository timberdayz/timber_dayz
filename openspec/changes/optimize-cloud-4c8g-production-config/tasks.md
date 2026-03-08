# Tasks: 生产环境 4 核 8G 云服务器资源配置优化

**目标**：限制 Metabase 内存、提供 4 核 8G 专用 compose overlay、强化 Redis 与连接池、统一 .env 资源变量、补充慢查询监控与文档，避免生产服务器再次卡死。**本变更不包含 Metabase 单独部署**，Metabase 与主栈继续同机运行。

## 1. Metabase 4c8g Overlay

- [ ] 1.1 新建 `docker-compose.metabase.4c8g.yml`：覆盖 metabase 的 environment（JAVA_OPTS: "-Xmx1g -Xms512m"）与 deploy.resources.limits（memory: 2G, cpus: "1"）。
- [ ] 1.2 验证：`docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.metabase.yml -f docker-compose.metabase.4c8g.yml config` 能成功生成合并配置，且 metabase 的 memory limit 为 2G。

## 2. 主栈 4c8g Overlay

- [ ] 2.1 新建 `docker-compose.cloud-4c8g.yml`：覆盖 backend command（**推荐** `--workers 3`）；**backend environment** 覆盖 `DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`（因 docker-compose.prod.yml 固定 20/40，.env 无法覆盖 compose environment）；celery-worker command 维持 `--concurrency=2` 或放宽至 3；可选适度放宽 postgres/backend memory limits（保持总 limits ≤ 约 7G）。Redis override 见任务 4.1。
- [ ] 2.2 在文件头部添加注释：说明该 overlay 用于 4 核 8G 服务器、生产环境 celery-worker 主要用于定时任务（非采集），与 cloud.yml 叠加使用。
- [ ] 2.3 验证：compose config 合并后 backend 与 celery-worker 的 command 正确。

## 3. .env 配置统一

- [ ] 3.1 更新 `env.production.example`（及若项目使用则同步 `env.production.cloud.example`）：增加 `RESOURCE_MONITOR_ENABLED=true`、`RESOURCE_MONITOR_MEMORY_THRESHOLD=85`（及可选 `RESOURCE_MONITOR_CPU_THRESHOLD=80`、`RESOURCE_MONITOR_CHECK_INTERVAL=60`）；4c8g 推荐 `DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`；在 CLOUD_4C8G_REFERENCE 中列出**需新增/修改的变量清单**。**不增加** `MAX_COLLECTION_TASKS`。**说明**：`.env.production` 在 .gitignore，部署者将新变量合并进本地 `.env.production`，再复制到云端 `.env`（`PRODUCTION_PATH/.env`，默认 `/opt/xihong_erp/.env`）。
- [ ] 3.2 在文档中说明 `MAX_COLLECTION_TASKS` 仅采集环境使用、生产环境无需配置；若 `.env.production` 中已有 `MAX_CONCURRENT_TASKS`，建议加注释标明「采集环境使用，生产可忽略」或删除，避免混淆。
- [ ] 3.3 若 backend 容器限制 1 CPU，在文档中建议设置 `CPU_EXECUTOR_WORKERS=1`；否则可依赖默认值。

## 4. Redis 强化

- [ ] 4.1 在 `docker-compose.cloud-4c8g.yml` 中增加 redis 服务的 `command` override，完整覆盖为 `redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-redis_pass_2025} --maxmemory 220mb --maxmemory-policy volatile-lru`。**实施前**：核对 prod/cloud compose 中 redis 的 command，确保 overlay 不丢失已有参数。
- [ ] 4.2 在文档中说明 Redis 角色（Celery broker、result backend、限流、Dashboard/重查询缓存）及 220M 容量评估；说明 volatile-lru 与 allkeys-lru 的选择理由；**注明**：Celery result 有 TTL，volatile-lru 在内存紧张时可能淘汰 result key（任务完成但取不到结果），生产 Celery 以定时任务为主可接受。
- [ ] 4.3 修改 `backend/services/cache_service.py`：`delete_pattern` 改为使用 SCAN 游标迭代 + DELETE，替代 KEYS；修改 `backend/services/maintenance_service.py`：`clear_cache` 中按模式删除时使用 SCAN 替代 `r.keys(pattern)`。
- [ ] 4.4 在 `/api/system/maintenance/cache/status` 返回中增加 CacheService 命中率字段（hits、misses、hit_rate）；在 `maintenance_service.get_cache_status()` 中调用 `get_cache_service().get_stats()` 并合并到 status；需**同步修改** `backend/schemas/maintenance.py` 中的 `CacheStatusResponse`，新增上述可选字段（Optional[int] / Optional[float]）；文档注明多 worker 下为单 worker 采样。
- [ ] 4.5 可选：在 `backend/celery_app.py` 中配置 `result_expires=86400`（24 小时），控制 result 占用 Redis。
- [ ] 4.6 在文档中补充 Cache TTL 与 key 设计说明：Dashboard KPI/对比/店铺赛马等使用 180–300s TTL，对前端数据新鲜度与 Metabase/DB 压力的平衡。

## 5. 连接池强化

- [ ] 5.1 在 `env.production.example` 中增加 4c8g 推荐注释：`DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`（若 3.1 已更新 env.production.example 变量值，此处仅补充注释；可合并到 3.1）。
- [ ] 5.2 在 CLOUD_4C8G_REFERENCE 中说明 Backend + Metabase + Celery 的总连接数与 Postgres `max_connections` 的关系，建议留出余量。

## 6. 慢查询监控

- [ ] 6.1 在 CLOUD_4C8G_REFERENCE 中说明：生产 Postgres 需配置 `shared_preload_libraries=pg_stat_statements`、`log_min_duration_statement=1000`；给出**可复制的 postgres command 示例**：`postgres -c shared_preload_libraries=pg_stat_statements -c log_min_duration_statement=1000`；**注明**：配置后需重启 Postgres，应在维护窗口执行；`docker/postgres/init_monitoring.sql` 中的 `v_top_slow_queries` 需 DBA 手动执行或加入 `sql/init`；引用 `docs/POSTGRESQL_SLOW_QUERY_LOG_GUIDE.md`（若不存在则说明手动配置步骤）。
- [ ] 6.1b 可选：在 `docker-compose.cloud-4c8g.yml` 中增加 postgres 的 `command` override 以启用慢查询监控（覆盖默认 postgres 启动命令）；若 postgres 已有自定义 command，需合并参数或仅在文档中说明手动配置步骤。
- [ ] 6.2 说明如何定期查询 `v_top_slow_queries`（或等价视图），给出示例命令。
- [ ] 6.3 在部署清单中增加「慢查询监控已启用」检查项（人工检查 `SHOW shared_preload_libraries` 是否含 pg_stat_statements；或可选在 `scripts/pre_deployment_check.py` 中增加脚本检查）。

## 7. 文档

- [ ] 7.1 新建 `docs/deployment/CLOUD_4C8G_REFERENCE.md`：说明 4 核 8G 生产环境的推荐 compose 命令、**完整 compose 命令示例**（含 overlay 顺序：`base → prod → cloud → cloud-4c8g → deploy → metabase → metabase.4c8g`）、需同步的 compose 文件列表；**⚠️ 首次部署后必做步骤**：tag 或手动部署完成后 deploy 脚本**不会**自动加载 4c8g overlay，4 核 8G 用户**必须**按文档手动追加 overlay 或配置 CLOUD_PROFILE，否则 Metabase 仍为 4G limit；**明确** `.env.production` 与云端 `.env` 一致，部署步骤：（1）复制 `.env.production` 到云端 `PRODUCTION_PATH/.env`，（2）追加 overlay 或配置 CLOUD_PROFILE，（3）重启服务；**部署触发说明**：tag push v* 触发，普通 git push 不触发；**手动部署** checkout main 分支；**维护 API 风险**：`/api/system/maintenance/cache/clear` 无 pattern 时 flushdb 会清空整个 Redis（含 Celery broker/result），生产慎用；**明确** deploy_remote_production.sh 当前不会自动加载 4c8g overlay。
- [ ] 7.2 在部署文档中补充「Metabase 导致卡死应急处置」：VNC/控制台登录后 `docker stop <metabase 容器>`、`free -h`、`docker stats` 等诊断步骤。
- [ ] 7.3 在 `docs/deployment/RESOURCE_CONFIGURATION.md` 或 `CLOUD_ENVIRONMENT_VARIABLES.md` 中补充 4 核 8G 推荐配置表（DB_POOL、RESOURCE_MONITOR_*、compose overlay 用法）；不包含 MAX_COLLECTION_TASKS（生产不跑采集）。
- [ ] 7.4 **数据流文档**：在 CLOUD_4C8G_REFERENCE.md 或架构文档中补充**实际数据流**：PostgreSQL ← Metabase（查询）→ Backend（调用 Metabase API）→ Redis（Backend 写入/读取缓存）→ Backend → 前端。明确前端仅调用 Backend API、不直接访问 Redis；Backend 是 Metabase 与 Redis 之间的中介。
- [ ] 7.5 **Backend→Metabase 超时说明**：在 CLOUD_4C8G_REFERENCE 中说明 `MetabaseQuestionService` 已配置 60s 超时（httpx）；若 Metabase 查询经常超时，可调整或按 Question 区分超时；引用 `backend/services/metabase_question_service.py`。
- [ ] 7.6 **后续优化章节**：在 CLOUD_4C8G_REFERENCE 中新增「进阶/后续规划」章节，列出 Future Considerations（含 Metabase Guest embedding 的适用范围说明：**仅适合单一独立报表页**，不适合业务概览等多维度集成、多业务筛选页面）；说明上述为后续可选变更，不包含在本 4c8g 优化范围内。

## 8. CI/CD 与部署脚本

- [ ] 8.1 **必须**：在 `.github/workflows/deploy-production.yml` 的 **deploy-tag** 与 **deploy-manual** 两个 job 的 Sync compose files 步骤（SCP 同步 compose 文件处）中，**均**增加对 `docker-compose.cloud-4c8g.yml`、`docker-compose.metabase.4c8g.yml` 的同步，否则 tag 发布或手动部署后 4c8g overlay 不会出现在生产服务器。**说明**：生产部署由 **tag push (v*)** 触发，普通 git push 不触发；部署完成后 4c8g overlay 加载仍需用户按文档手动追加或配置 CLOUD_PROFILE。
- [ ] 8.2 可选：在 `scripts/deploy_remote_production.sh` 中增加 `CLOUD_PROFILE=4c8g` 时自动加载 cloud-4c8g、metabase.4c8g；**插入顺序**须为 `cloud.yml` → `cloud-4c8g.yml` → `deploy.yml` → `metabase.yml` → `metabase-4c8g.yml`。**否则**在 CLOUD_4C8G_REFERENCE.md 中明确：4 核 8G 用户需手动追加 overlay，否则 Metabase 限制不生效。
- [ ] 8.3 验证：compose config 合并后**总 memory limits ≤ 约 7G**（可用 `docker-compose config` 输出并汇总各服务 limits）。
- [ ] 8.4 在 `scripts/pre_deployment_check.py` 或部署清单中增加 4 核 8G 检查项：确认 compose overlay 文件存在、.env 中 RESOURCE_MONITOR_ENABLED 已配置、**4c8g overlay 已加载**（否则 Metabase 限制不生效）；**不检查** MAX_COLLECTION_TASKS（生产不跑采集）。

## 9. 后续优化（不在本次范围）

以下优化符合业界主流，**本变更不包含**；可作为后续 OpenSpec 变更或 CLOUD_4C8G_REFERENCE 进阶规划：

- Backend 对 Metabase 健康检查/熔断
- 前端 Dashboard 超时与错误提示
- RESOURCE_MONITOR 告警对接（钉钉/邮件/Webhook）
- Redis 与 Celery 分离（独立实例）
- 缓存预热（启动或定时）
- 写时失效（数据变更时主动 delete 相关 cache key）
- Metabase 单独部署
- Postgres statement_timeout 配置
- Metabase Guest embedding 评估：**仅适合单一独立报表页**（如全屏销售图），不适合业务概览等多维度集成 + 多业务筛选页面
