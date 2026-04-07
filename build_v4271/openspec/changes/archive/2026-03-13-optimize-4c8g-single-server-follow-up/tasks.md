# Tasks: 4 核 8G 单机后续优化

**目标**：在单台 4 核 8G 服务器上落地健康检查/熔断、前端超时与错误提示、资源监控告警、缓存预热、写时失效、Postgres statement_timeout。**不包含** Metabase Guest embedding、Redis 与 Celery 分离。

## 1. Backend 对 Metabase 健康检查/熔断

- [x] 1.1 使用**集中维护**的健康状态（内存状态 + 定时或失败驱动刷新），**禁止**每个请求直连 Metabase 打 health；在调用 Metabase API 前或调用链中依据该状态做熔断/快速失败。
- [x] 1.2 约定熔断最小契约：失败阈值、熔断窗口、恢复条件（如半开探测），并在实现中遵守。
- [x] 1.3 对前端统一错误协议：Metabase 不可用/熔断时返回固定 `error_code`（如 `METABASE_UNAVAILABLE`）及明确 message，便于前端区分展示。
- [x] 1.4 文档：在 CLOUD_4C8G_REFERENCE 或运维文档中说明健康检查/熔断的触发条件与恢复行为。

## 2. 前端 Dashboard 超时与错误提示

- [x] 2.1 满足**三层超时对齐**：DB statement_timeout < Backend→Metabase 超时 < 前端→Backend 超时；对 Dashboard 相关请求设置前端超时（推荐 65–70s，略大于后端 60s），超时后展示明确提示（如「请求超时，请稍后重试」）。
- [x] 2.2 对 Metabase/Backend 返回的错误状态（5xx、超时）在前端展示统一错误提示；**至少区分**「请求超时」与「Metabase 不可用/熔断」两类文案，避免白屏或误导。
- [x] 2.3 可选：为超时或不可用场景提供重试入口（按钮或自动重试一次）。（业务概览/年度总结等页面的「刷新数据」即重试入口；AnnualSummary 已区分超时与不可用文案并提示点击刷新重试。）

## 3. RESOURCE_MONITOR 告警对接

- [x] 3.1 在资源监控超阈值（内存/CPU）时，支持对接钉钉/邮件/Webhook 之一或多种；配置**必须**通过环境变量读取，**禁止**硬编码或提交敏感信息到仓库。
- [x] 3.2 实现**告警冷却**：同一类型告警在 N 分钟内只发一次，避免高负载时告警风暴；告警发送失败时具备重试上限（如最多 3 次）并记录错误日志。
- [x] 3.3 在 env.production.example 或 CLOUD*4C8G_REFERENCE 中补充告警相关变量说明（如 WEBHOOK_URL、DINGTALK*\*、SMTP 等），示例值使用占位符，不包含真实密钥。

## 4. 缓存预热（启动或定时）

- [x] 4.1 在 Backend 启动后或定时任务中，对 Dashboard KPI、对比、店铺赛马等热点 Question 的缓存进行预热，**至少覆盖 proposal 中定义的 P1 业务概览相关 Question**；预热采用**限流**（串行或小批次、明确最大并发数），避免一次性打满 Metabase/DB。
- [x] 4.2 当 Metabase 健康检查失败时**跳过本轮预热**并记录日志；单次预热失败或超时应记录告警日志但**不得阻塞 Backend 启动**。
- [x] 4.3 P1 Question 列表来源明确（配置表、常量文件或 ENV），在文档中说明维护方式；**禁止**在业务代码中散落硬编码 Question ID。
- [x] 4.4 文档：说明预热时机（启动/定时）、覆盖的 Question 范围（P1/P2/P3）、限流策略及对 Metabase/DB 的影响（避免预热过于频繁）。

## 5. 写时失效

- [x] 5.1 在**至少**以下事件触发时执行写时失效（与 proposal 中「写时失效必须覆盖的事件」清单一致）：数据同步/采集任务完成；经营目标/目标值配置更新；与 Dashboard 相关的业务配置更新（如店铺、平台映射等）。实现时不得少于该清单。
- [x] 5.2 写时失效逻辑**集中**在统一 service/工具层（如 CacheService 或专用 invalidation 模块），由各业务入口调用，避免在路由/任务中零散手写删除 key；删除的 key 前缀与文档中命名约定一致（如 `dashboard:business_overview:*`）。
- [x] 5.3 文档：在 CLOUD_4C8G_REFERENCE 或缓存设计中说明哪些变更会触发写时失效、key 命名约定（含是否按 platform/shop 维度）及调用方式。

## 6. Postgres statement_timeout

- [x] 6.1 在 CLOUD_4C8G_REFERENCE 或 Postgres 配置文档中说明：生产环境建议配置 `statement_timeout`（**推荐 DB 侧 50–60s，且不高于 Backend→Metabase HTTP 超时（当前 60s）**），并给出可复制的配置方式（postgres 启动参数或 `ALTER DATABASE`/session 级）。
- [x] 6.2 为 4c8g 单机部署提供 **docker-compose.cloud-4c8g.yml 或 Postgres 的配置片段**（可默认启用或在注释中标明建议启用），便于一键应用。
- [x] 6.3 注明：配置后需重启 Postgres 或仅对新连接生效，应在维护窗口或评估影响后执行；开发/测试环境可选用更短超时（如 10–20s）以暴露慢 SQL；如需对少数重报表放宽，仅通过角色/会话级配置单独调整，不建议将全局超时提升到 120s 以上。

## 7. 文档与验收

- [x] 7.1 在 CLOUD_4C8G_REFERENCE「进阶/后续规划」中增加本变更完成项的引用，或新增「单机后续优化」小节。
- [x] 7.2 验收：上述 1–6 项实现后，在 4 核 8G 单机环境验证健康检查/熔断、前端超时与错误提示、告警触发、预热与写时失效、statement_timeout 配置生效。**执行清单**：见本目录 `ACCEPTANCE_CHECKLIST_7.2.md`。自动化验收已通过（`tests/test_4c8g_follow_up_acceptance.py` + `scripts/run_4c8g_acceptance.py`）；手动清单 1～6 需在 4c8g 环境中按需执行后勾选。
