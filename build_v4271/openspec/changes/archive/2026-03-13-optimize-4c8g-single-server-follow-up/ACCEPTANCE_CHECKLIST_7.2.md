# 7.2 验收清单：4 核 8G 单机环境验证

本清单对应 tasks.md 中 **7.2 验收**：在 4 核 8G 单机环境验证健康检查/熔断、前端超时与错误提示、告警触发、预热与写时失效、statement_timeout 配置生效。

**前提**：已按 `docs/deployment/CLOUD_4C8G_REFERENCE.md` 完成 4c8g 部署（含 overlay、.env 变量、Postgres statement_timeout 等）。

---

## 0. 自动化验证（本地可执行）

- [x] **单测**：`python -m pytest tests/test_4c8g_follow_up_acceptance.py tests/test_metabase_question_service.py -v` 全部通过。
- [x] **脚本**：`python scripts/run_4c8g_acceptance.py` 运行通过，表示熔断/METABASE_UNAVAILABLE/预热跳过/告警冷却/写时失效接口等逻辑已通过自动化覆盖。
- 可选：后端与 Redis 已启动时，可运行 `python scripts/test_dashboard_cache.py` 验证 Dashboard KPI 缓存命中与耗时。

以下 1～6 为**手动验收**，需在 4 核 8G 单机（或等价）环境中执行。

---

## 1. 健康检查/熔断

- [ ] **触发熔断**：停止 Metabase 容器（如 `docker stop xihong_erp_metabase`），或在 Backend 可访问 Metabase 的前提下人为使 Metabase 连续返回 5xx。
- [ ] **预期**：在 Dashboard 页面多次刷新后，应出现「Metabase 不可用」或类似明确提示，**而非**长时间转圈或白屏。
- [ ] **恢复**：启动 Metabase（如 `docker start xihong_erp_metabase`），等待熔断窗口（默认 60s）结束后再刷新页面，应能恢复数据展示。

---

## 2. 前端超时与错误提示

- [ ] **超时**：确认 Dashboard 相关请求前端超时约 65–70s（略大于后端 60s）；可查看前端 API 或 Network 面板。
- [ ] **超时文案**：人为使后端或 Metabase 慢响应直至超时，页面应展示「请求超时，请稍后重试」类提示。
- [ ] **不可用文案**：在 Metabase 不可用/熔断时，页面应展示「Metabase 不可用」类文案，与「请求超时」区分。
- [ ] **重试**：业务概览/年度总结等页面的「刷新数据」可作为重试入口，点击后能重新请求。

---

## 3. RESOURCE_MONITOR 告警

- [ ] **配置**：在 `.env` 中配置告警渠道之一（如 `RESOURCE_MONITOR_WEBHOOK_URL` 或钉钉相关变量），使用占位或测试 URL。
- [ ] **触发**：将 `RESOURCE_MONITOR_MEMORY_THRESHOLD` / `RESOURCE_MONITOR_CPU_THRESHOLD` 临时调低，或压测使资源超阈值。
- [ ] **预期**：配置的 Webhook/钉钉能收到告警；同一类型告警在冷却期（如 5 分钟）内不重复发送。
- [ ] **失败重试**：告警发送失败时查看 Backend 日志，应有重试与错误日志，且不导致进程异常。

---

## 4. 缓存预热

- [ ] **开关**：设置 `METABASE_CACHE_WARMUP_ENABLED=true`，重启 Backend。
- [ ] **预期**：启动后延迟约 10s（或 `METABASE_CACHE_WARMUP_DELAY_SECONDS`）后，Backend 日志中有预热相关日志（P1 Question 串行请求）；若 Metabase 不可用，应跳过预热并打日志，且**不阻塞** Backend 启动。
- [ ] **首访**：打开业务概览等 P1 页面，首访应能较快返回（若预热成功，数据来自缓存）。

---

## 5. 写时失效

- [ ] **数据同步**：完成一次数据同步或采集任务（单文件或批量均可），确认任务状态为成功。
- [ ] **Dashboard**：打开业务概览或年度总结，确认展示的数据已更新（无旧缓存）。
- [ ] **经营目标**：若有经营目标配置，执行创建/更新/删除后，再打开 Dashboard，确认相关数据已更新。

---

## 6. Postgres statement_timeout

- [ ] **配置确认**：确认 `docker-compose.cloud-4c8g.yml`（或实际使用的 compose）中 postgres 已包含 `statement_timeout=60000`（或 50–60s），或已在库上执行 `ALTER DATABASE ... SET statement_timeout = '60s'`。
- [ ] **验证**（建议在维护窗口或测试环境）：在 DB 中执行一条长时间查询（如 `SELECT pg_sleep(70);`），应在约 60s 内被中断并报 statement_timeout 类错误。

---

## 验收结论

完成上述全部勾选后，可在 tasks.md 中将 **7.2** 标记为完成：

```markdown
- [x] 7.2 验收：上述 1–6 项实现后，在 4 核 8G 单机环境验证……（已按 ACCEPTANCE_CHECKLIST_7.2.md 执行并通过）
```

参考文档：`docs/deployment/CLOUD_4C8G_REFERENCE.md` 第 16、18 节。
