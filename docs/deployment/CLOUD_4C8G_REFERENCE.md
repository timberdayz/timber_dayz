# 4 核 8G 生产环境配置参考

本文档说明在 4 核 8G 云服务器上部署西虹 ERP 的推荐配置，避免 Metabase 等服务占满内存导致整机卡死。

## 1. 推荐 Compose 命令与 Overlay 顺序

完整 compose 命令（4 核 8G 生产环境）：

```bash
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.cloud-4c8g.yml \
  -f docker-compose.deploy.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.metabase.4c8g.yml \
  --profile production \
  up -d
```

**Overlay 加载顺序**：`base → prod → cloud → cloud-4c8g → deploy → metabase → metabase.4c8g`。4c8g overlay 必须在其 base 之后加载才能正确覆盖。

## 2. 需同步的 Compose 文件

| 文件 | 说明 |
|------|------|
| docker-compose.yml | 基础配置 |
| docker-compose.prod.yml | 生产环境 |
| docker-compose.cloud.yml | 云服务器优化（2 核 4G） |
| docker-compose.cloud-4c8g.yml | **4 核 8G 专用 overlay** |
| docker-compose.deploy.yml | 部署时动态生成（镜像 tag） |
| docker-compose.metabase.yml | Metabase 服务 |
| docker-compose.metabase.4c8g.yml | **Metabase 4 核 8G 限制 overlay** |

## 3. ⚠️ 首次部署后必做步骤

**重要**：tag 或手动部署完成后，deploy 脚本**不会**自动加载 4c8g overlay。4 核 8G 用户**必须**：

1. 按文档手动追加 overlay 到 compose 命令，或
2. 配置 `CLOUD_PROFILE=4c8g`（若 deploy 脚本支持）

否则 Metabase 仍为 4G limit，限制不生效，存在 OOM 风险。

## 4. 部署步骤

1. 将本地 `.env.production` 内容复制到云端 `PRODUCTION_PATH/.env`（默认 `/opt/xihong_erp/.env`）。`.env.production` 与云端 `.env` 保持一致。
2. 按文档追加 overlay 或配置 `CLOUD_PROFILE=4c8g`。
3. 重启服务。

## 5. 部署触发说明

- **tag push (v\*)**：触发生产部署；普通 git push 不触发。
- **手动部署**：在 main 分支执行 workflow_dispatch，输入 image_tag。

## 6. 4c8g 变量清单

需在 `.env.production` / 云端 `.env` 中新增或修改：

| 变量 | 推荐值 | 说明 |
|------|--------|------|
| RESOURCE_MONITOR_ENABLED | true | 启用资源监控 |
| RESOURCE_MONITOR_MEMORY_THRESHOLD | 85 | 内存告警阈值(%) |
| RESOURCE_MONITOR_CPU_THRESHOLD | 80 | CPU 告警阈值(%) |
| RESOURCE_MONITOR_CHECK_INTERVAL | 60 | 检查间隔(秒) |
| RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES | 5 | 告警冷却(分钟)，同类型 N 分钟内只发一次 |
| RESOURCE_MONITOR_WEBHOOK_URL | (可选) | 告警 Webhook URL，POST JSON |
| DINGTALK_WEBHOOK_URL / DINGTALK_ACCESS_TOKEN | (可选) | 钉钉机器人，二选一配置 |
| RESOURCE_MONITOR_SMTP_HOST | (可选) | 告警邮件 SMTP 主机，需配合 SMTP_* 使用 |
| DB_POOL_SIZE | 30 | 4c8g 推荐（compose overlay 会覆盖 prod 的 20） |
| DB_MAX_OVERFLOW | 30 | 4c8g 推荐 |
| METABASE_CACHE_WARMUP_ENABLED | false | 为 true 时启动后执行 Dashboard P1 缓存预热 |
| METABASE_CACHE_WARMUP_DELAY_SECONDS | 10 | 启动后延迟秒数再预热 |
| METABASE_WARMUP_P1_QUESTIONS | (可选) | 逗号分隔 question name，不配置则用默认 P1 列表 |

**不配置** `MAX_COLLECTION_TASKS`：生产环境不跑采集，该变量仅采集环境使用。告警相关变量均从环境变量读取，示例值使用占位符，不包含真实密钥。

## 7. Metabase 导致卡死应急处置

1. 通过 VNC/控制台登录服务器。
2. `docker stop xihong_erp_metabase` 停止 Metabase 容器。
3. `free -h`、`docker stats` 查看内存与容器状态。
4. 确认 4c8g overlay 已加载；若未加载，按文档追加 overlay 后重启。
5. `docker start xihong_erp_metabase` 重启 Metabase。

## 8. 数据流说明

**实际数据流**：

```
PostgreSQL ← Metabase（查询）
               ↑
            Backend（调用 Metabase API）
               ↑
            Redis（Backend 写入/读取缓存）
               ↑
            Backend
               ↑
            前端（仅调用 Backend API，不直接访问 Redis）
```

- 前端仅调用 Backend API，不直接访问 Redis。
- Backend 是 Metabase 与 Redis 之间的中介。

## 9. Backend→Metabase 超时

`MetabaseQuestionService` 已配置 `httpx.AsyncClient(timeout=60.0)`，即 60 秒超时。若 Metabase 查询经常超时，可调整 `backend/services/metabase_question_service.py` 中的 timeout，或按 Question 区分超时。

## 10. Redis 角色与配置

### 10.1 角色

- Celery broker / result backend
- 限流存储
- Dashboard/重查询缓存（CacheService）

### 10.2 4c8g 配置

- `maxmemory=220mb`
- `maxmemory-policy=volatile-lru`

**220M 容量评估**：业务缓存（180–300s TTL）、Celery result（24h TTL）、限流 key 等，220M 在中小规模下足够。

**volatile-lru vs allkeys-lru**：`volatile-lru` 仅淘汰带 TTL 的 key，可保护 Celery broker（通常无 TTL）。**注意**：Celery result 有 TTL，内存紧张时 `volatile-lru` 可能淘汰 result key，导致任务完成但取不到结果；生产 Celery 以定时任务为主，可接受。

### 10.3 Cache TTL 与 key 设计

Dashboard KPI、对比、店铺赛马等使用 180–300s TTL，平衡前端数据新鲜度与 Metabase/DB 压力。

## 11. Postgres statement_timeout

生产环境建议配置 `statement_timeout`，限制单条 SQL 最长执行时间，防止慢 SQL 长时间占用连接与锁。

- **推荐**：DB 侧 50–60 秒，且**不高于** Backend→Metabase HTTP 超时（当前 60s），满足「DB < Backend→Metabase < 前端」三层超时对齐。
- **配置方式**（任选其一）：
  - **启动参数**：`postgres -c statement_timeout=60000`（单位毫秒，60000 = 60s）
  - **ALTER DATABASE**：`ALTER DATABASE xihong_erp SET statement_timeout = '60s';`
  - **会话级**：`SET statement_timeout = '60s';`（仅当前会话）
- **生效**：启动参数或 ALTER 后需重启 Postgres 或仅对新连接生效，应在维护窗口或评估影响后执行。
- **开发/测试**：可选用更短超时（如 10–20s）以尽早暴露慢 SQL。
- **重报表**：如需对少数重报表放宽，仅通过角色/会话级配置单独调整，不建议将全局超时提高到 120s 以上。

**4c8g 单机 docker-compose 片段**（在 `docker-compose.cloud-4c8g.yml` 或单独 overlay 中为 postgres 增加 command，与 base 的 postgres 服务合并）：

```yaml
services:
  postgres:
    # 建议启用：单条 SQL 最长 60 秒，与 Backend→Metabase 超时对齐
    command: ["postgres", "-c", "statement_timeout=60000"]
```

若 base 中 postgres 已有 command，需合并为一条完整 command 并包含 `-c statement_timeout=60000`。

## 12. 连接池与 max_connections

Backend + Metabase + Celery 的总连接数应小于 Postgres `max_connections`。4c8g 推荐 Backend `DB_POOL_SIZE=30`、`DB_MAX_OVERFLOW=30`，支持 50+ 并发用户。建议留出余量。

## 13. 慢查询监控

### 12.1 配置

生产 Postgres 需配置：

- `shared_preload_libraries=pg_stat_statements`
- `log_min_duration_statement=1000`（毫秒）

**可复制的 postgres command 示例**：

```bash
postgres -c shared_preload_libraries=pg_stat_statements -c log_min_duration_statement=1000
```

**注意**：配置后需**重启 Postgres**，应在维护窗口执行。

`docker/postgres/init_monitoring.sql` 中的 `v_top_slow_queries` 需 DBA 手动执行或加入 `sql/init`。

### 12.2 查询慢查询

```bash
# 在 Postgres 容器内
psql -U erp_user -d xihong_erp -c "SELECT * FROM v_top_slow_queries;"
```

或使用 `get_slow_queries(1000)` 函数（阈值 1000ms）。

## 14. 维护 API 风险

`/api/system/maintenance/cache/clear` 在 `cache_type=all` 或 `cache_type=redis` 且**无 pattern** 时会执行 `flushdb`，**清空整个 Redis DB**（含 Celery broker/result）。**生产环境慎用**；仅在有 pattern 时按模式清理。

## 15. deploy_remote_production.sh 说明

当前脚本**不会**自动加载 cloud-4c8g、metabase.4c8g overlay。4 核 8G 用户需手动追加 overlay 或配置 `CLOUD_PROFILE=4c8g`（若实现）。

## 16. 单机后续优化（4c8g 落地项）

在 4 核 8G 单机上已落地或可落地的优化（参见变更 `optimize-4c8g-single-server-follow-up`）：

- **Backend 对 Metabase 健康检查/熔断**：集中健康状态 + 熔断（失败阈值、熔断窗口、半开探测），不可用时返回 `error_code=METABASE_UNAVAILABLE`。
- **前端 Dashboard 超时与错误提示**：前端超时 70s，与后端 60s 对齐；至少区分「请求超时」与「Metabase 不可用/熔断」文案。
- **RESOURCE_MONITOR 告警对接**：超阈值时支持 Webhook/钉钉（配置见上表）；告警冷却、发送失败重试上限 3 次，配置仅从环境变量读取。
- **缓存预热与写时失效**：见下 16.1 写时失效、16.3 缓存预热。
- **Postgres statement_timeout**：见本文档「Postgres statement_timeout」小节。

### 16.1 写时失效

Dashboard 相关缓存（经营概览、年度总结等）在数据变更后需主动失效，避免用户看到旧数据。

- **Key 约定**：删除时使用前缀匹配，清理 `xihong_erp:dashboard_*` 与 `xihong_erp:annual_summary_*`。具体 key 格式为 `xihong_erp:{cache_type}:{hash}`，由 CacheService 统一生成。
- **调用方式**：
  - **异步**（路由、异步任务）：`await get_cache_service().invalidate_dashboard_business_overview()`
  - **同步**（Celery 等同步上下文）：`get_cache_service().invalidate_dashboard_cache_sync()`
- **触发事件**（业务侧在以下成功后调用上述接口，失败仅打 warning，不影响主流程）：
  - 单文件数据同步任务完成（`data_sync_tasks` 中 complete_task 成功后）
  - 批量数据同步任务完成且至少成功 1 个文件（`sync_batch_task` 中 complete_task 成功后）
  - 经营目标创建/更新/删除（`target_management` 的 create_target、update_target、delete_target 成功后）

### 16.2 健康检查与熔断（Metabase）

Backend 对 Metabase 不做独立定时健康检查，仅在每次请求前检查熔断状态；请求失败时更新失败计数，用于后续熔断判断。

- **触发条件**：连续调用 Metabase API 失败（5xx 或网络错误）达到 **METABASE_CIRCUIT_FAILURE_THRESHOLD** 次（默认 3）即打开熔断，后续请求直接返回 `error_code=METABASE_UNAVAILABLE`，不再访问 Metabase。
- **熔断窗口**：熔断打开后持续 **METABASE_CIRCUIT_OPEN_SECONDS** 秒（默认 60）。窗口内所有请求快速失败。
- **恢复行为**：窗口结束后进入半开状态，下一次请求会真实发往 Metabase 作为探测；若成功则清零失败计数、恢复正常；若失败则再次打开熔断并重新计时窗口。
- **环境变量**（可选）：`METABASE_CIRCUIT_FAILURE_THRESHOLD`、`METABASE_CIRCUIT_OPEN_SECONDS`；不配置则使用上述默认值。

### 16.3 缓存预热

在 Backend 启动后（或定时任务中）对 Dashboard P1 业务概览 Question 进行**串行**预热，减轻首访或高峰时对 Metabase/DB 的压力。

- **预热时机**：Backend 启动后延迟 N 秒（`METABASE_CACHE_WARMUP_DELAY_SECONDS`，默认 10）执行一次；不阻塞启动，失败仅打日志。定时预热可后续通过 Celery Beat 或运维脚本调用同一预热接口实现。
- **覆盖范围**：默认 P1 = 核心 KPI、期间对比、店铺赛马、流量排名、库存积压、经营指标、清仓排名（见 `cache_warmup_service` 中 `_DEFAULT_P1_QUESTIONS`）。可通过 `METABASE_WARMUP_P1_QUESTIONS` 覆盖（逗号分隔 question name）。P2/P3 一般不预热。
- **限流策略**：串行执行（一次只打一个 Question），避免一次性打满 Metabase/DB。
- **健康联动**：当 Metabase 不可用或熔断时**跳过本轮预热**并记录日志；单次预热失败或超时记录告警日志但**不阻塞 Backend 启动**。
- **P1 列表维护**：列表来源为环境变量 `METABASE_WARMUP_P1_QUESTIONS` 或代码内默认常量；禁止在业务代码中散落硬编码 Question ID。新增/减少 P1 时修改默认列表或 ENV 并更新本文档。

**不包含**（需多机或独立部署）：Redis 与 Celery 分离、Metabase 单独部署、Metabase Guest embedding。

## 17. 进阶/后续规划

以下为可选后续优化，**不在单机 4c8g 必选范围内**：

- Redis 与 Celery 分离（独立实例）
- Metabase 单独部署
- **Metabase Guest embedding**：仅适合单一独立报表页（如全屏销售图），**不适合**业务概览等多维度集成、多业务筛选页面

## 18. 4c8g 单机验收参考（变更 optimize-4c8g-single-server-follow-up）

在 4 核 8G 单机环境部署完成后，可按下述项做人工验证（非自动化测试）：

1. **健康检查/熔断**：停止 Metabase 容器或使 Metabase 连续返回 5xx，在 Dashboard 页面多次刷新；应出现「Metabase 不可用」类提示而非长时间转圈或白屏；恢复 Metabase 后，等待熔断窗口（默认 60s）结束再刷新，应能恢复数据。
2. **前端超时与错误提示**：确认 Dashboard 请求超时时间约 70s；超时或 Metabase 不可用时，页面展示明确文案区分「请求超时」与「Metabase 不可用」。
3. **RESOURCE_MONITOR 告警**：将 CPU/内存阈值临时调低或压测使资源超阈值，确认配置的 Webhook/钉钉能收到告警，且同类型告警在冷却期内不重复发送。
4. **写时失效**：完成一次数据同步或经营目标变更后，打开 Dashboard/年度总结，确认数据已更新（无旧缓存）。
5. **Postgres statement_timeout**：若已按 §11 配置，可在 DB 中执行长时间查询验证超时生效（需在维护窗口或测试环境进行）。
