# Change: 4 核 8G 单机后续优化（健康检查、告警、缓存、Postgres）

## Why

在完成「生产环境 4 核 8G 云服务器资源配置优化」（`optimize-cloud-4c8g-production-config`）后，单台 4 核 8G 服务器上仍有可做的**单机内**优化，用于提升稳定性与可观测性，无需增加机器或 Metabase 单独部署。本变更仅包含在单机 4 核 8G 上可落地的项，**不包含**：Metabase Guest embedding 评估、Redis 与 Celery 分离（独立实例）。

## What Changes

- **Backend 对 Metabase 健康检查/熔断**：Backend 调用 Metabase API 前或调用中增加健康检查或熔断逻辑，Metabase 不可用或持续超时时快速失败，避免请求长时间挂起、占满连接。
- **前端 Dashboard 超时与错误提示**：前端对 Dashboard 相关请求设置合理超时，并展示明确的超时/错误提示，避免用户长时间白屏或无感知等待。
- **RESOURCE_MONITOR 告警对接**：将现有资源监控（RESOURCE_MONITOR_*）在超阈值时对接钉钉/邮件/Webhook，使运维可感知内存/CPU 异常。
- **缓存预热（启动或定时）**：在 Backend 启动时或定时任务中预热 Dashboard KPI 等热点缓存，减轻首访或高峰时对 Metabase/DB 的压力，重点覆盖业务概览类 Question。
- **写时失效**：在关键数据变更时主动删除相关 cache key（如 `dashboard:business_overview:*` 等 Dashboard 相关前缀 key），保证缓存与 DB 一致性，减少脏数据展示。
- **Postgres statement_timeout 配置**：在生产 Postgres 或应用层配置 `statement_timeout`，限制单条 SQL 最长执行时间，防止单条慢 SQL 长时间占用连接与锁导致拖垮库；推荐的初始区间为 DB 侧 50–60 秒，并保证 DB 超时不高于 Backend→Metabase HTTP 超时（当前为 60 秒）。

### 设计约束与注意事项

- **适用范围**：本变更实现的代码逻辑为**通用**（对所有环境生效），通过环境变量/配置决定在 4c8g 单机环境的具体参数（如预热是否启用与频率、告警阈值、熔断参数等），**禁止**在业务代码中硬编码「仅 4c8g」分支。
- **三层超时对齐**：必须满足 **DB statement_timeout < Backend→Metabase HTTP 超时 < 前端→Backend HTTP 超时**，避免某一层先挂导致下游长时间等待。推荐数值：DB 50–60s、Backend→Metabase 60s、前端→Backend 65–70s（略大于后端以便后端先超时并返回）。
- **健康检查/熔断**：健康状态应**集中维护**（如内存中的状态 + 定时或失败驱动刷新），**禁止**每个请求都直连 Metabase 打 `/api/health`（避免 Metabase 半挂时放大压力）。熔断需约定最小契约：失败阈值、熔断窗口、恢复条件（如半开探测）；熔断或不可用时对前端返回**统一错误协议**（如固定 `error_code`：`METABASE_UNAVAILABLE`），便于前端区分展示。
- **前端错误展示**：至少区分「请求超时」与「Metabase 不可用/熔断」两类文案，并可选择提供重试入口（按钮或自动重试一次）。
- **告警**：需支持**冷却时间**（同一类型告警在 N 分钟内只发一次），避免高负载时告警风暴。Webhook/钉钉/邮件等敏感配置**必须**从环境变量读取，**禁止**写入代码或提交到仓库的示例配置中；告警发送失败时应有重试上限（如最多 3 次）并记录错误日志。
- **缓存预热**：预热需**限流**（如串行或小批次、最大并发数），避免启动/定时一次性打满 Metabase/DB。当 Metabase 健康检查失败时**跳过本轮预热**并记录日志。P1 Question 列表应有明确来源（配置表、常量文件或 ENV），由配置/文档维护，**禁止**在业务代码中散落硬编码 ID。
- **写时失效**：必须挂载写时失效的**事件清单**在 proposal/tasks 中显式列出（见下文），实现时不得少于该清单；写时失效逻辑应**集中**在统一 service/工具层执行，避免在各路由/任务中零散手写删除 key。缓存 key 前缀命名约定需在文档中固化（含是否按 platform/shop 维度）。
- **Postgres statement_timeout**：4c8g 单机部署需在文档中提供 `docker-compose.cloud-4c8g.yml` 或 Postgres 的**可复制配置片段**（可默认启用或在注释中标明建议启用）。开发/测试环境可选用更短超时（如 10–20s）以尽早暴露慢 SQL；若需对少数重报表放宽，仅通过角色/会话级配置单独调整，不建议将全局超时提高到 120s 以上。

### Dashboard 预热与写时失效优先级（说明）

- **P1（必须预热 + 写时失效）**：业务概览首页相关 Question，例如：
  - 核心 KPI 卡片（GMV、利润、订单数等）
  - 期间对比（本期 vs 上期）
  - 店铺赛马 / 店铺排行榜
  - 流量/转化类排行榜
  - 库存积压 / 清仓榜
  - 运营效率指标（发货及时率、退款率等）
- **P2（建议至少写时失效，可按使用情况决定是否预热）**：
  - 年度汇总 / 大盘趋势类报表（Annual KPI / Annual Summary）
  - 访问频率较高的专题管理报表（领导常看的专题页）
- **P3（一般不预热）**：
  - 深钻明细、临时分析类报表，或用户可以接受首次稍慢的页面。

预热与写时失效策略应优先保证 P1 报表在高并发访问（如 50 人同时打开业务概览）场景下基本都命中 Redis 缓存，仅在缓存失效或写时失效后由首个请求触发一次重查询，从而将对 Postgres/Metabase 的压力控制在可预期范围内。

**写时失效必须覆盖的事件（最小清单）**：

- 数据同步/采集任务完成（按数据域或全局，视业务约定）。
- 经营目标/目标值配置更新。
- 与 Dashboard 相关的业务配置更新（如店铺、平台映射等）。
- 后续若新增会直接影响 Dashboard 展示的写操作，应补充到本清单并同步实现写时失效。

**明确排除（不包含在本变更）**：

- Metabase Guest embedding 评估（项目不需要单一独立报表页方案）。
- Redis 与 Celery 分离（独立实例）（需多机或托管 Redis，不适合单台 4 核 8G）。

## Impact

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| 后端 | `backend/services/metabase_question_service.py` 或调用链 | Metabase 健康检查/熔断（可选集成 circuit breaker 或前置 health check） |
| 前端 | Dashboard 相关页面/请求封装 | 超时设置与错误/超时提示文案 |
| 后端 | `backend/services/resource_monitor.py` 或告警模块 | 阈值触发时调用钉钉/邮件/Webhook |
| 后端 | 启动或定时任务 | 缓存预热（Dashboard KPI 等） |
| 后端 | 数据变更入口（如数据同步、配置更新） | 写时失效：变更后删除相关 cache key |
| 配置/文档 | Postgres 配置或 `docker-compose.cloud-4c8g.yml` / 文档 | `statement_timeout` 说明与可复制配置 |

## Capabilities

### Modified Capabilities

- `deployment-ops`：ADDED 单机 4 核 8G 后续优化要求（Metabase 健康/熔断、前端超时与错误提示、RESOURCE_MONITOR 告警、缓存预热、写时失效、Postgres statement_timeout）。
