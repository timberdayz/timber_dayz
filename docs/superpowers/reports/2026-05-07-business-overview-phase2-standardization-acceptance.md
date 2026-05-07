# Business Overview Phase-2 Standardization Acceptance Report (2026-05-07)

## Scope

Business Overview（排除滞销库存 inventory-backlog）模块：

- `bootstrap`
- `kpi`
- `comparison`
- `traffic-ranking`
- `operational-metrics`
- `shop-racing`

## What Changed

- Contract (non-breaking)
  - 统一为以上模块响应增加顶层 `meta`（保留原有 `data` 结构不变），用于表达：
    - `granularity`
    - `period_key`（归一化为 ISO 日期）
    - `platform_code`
    - `cache.status`（HIT/MISS/BYPASS）
- Bootstrap coverage
  - `bootstrap` 聚合结果补齐 `traffic_ranking` 与 `shop_racing`（与页面模块对齐）
- Tests
  - `backend/tests/data_pipeline/test_business_overview_module_consistency.py` 增加 meta/period_key 归一化与 bootstrap 模块覆盖断言

## Acceptance Targets

- `bootstrap` cache MISS：P95 < 10s
- `bootstrap` cache HIT：P95 < 200ms
- 5 个模块接口：持续运行探针无超时、全为 200

## Evidence

### Performance regression (local)

- Command:
  - `python scripts/verify_performance_regression.py --mode local --base-url http://127.0.0.1:8001`
- Output:
  - `temp/outputs/performance_regression_summary_latest.json`

### Split probe (5 modules)

- Command:
  - `python scripts/business_overview_split_probe.py --rounds 10`
- Output:
  - `temp/outputs/business_overview_split_probe_latest.json`

### Long run probe

- Command:
  - `python scripts/business_overview_long_run.py --duration-seconds 120 --interval-seconds 30`
- Output:
  - `temp/outputs/business_overview_long_run_latest.json`

### Bootstrap cache MISS / HIT sampling

- Method:
  - cache MISS：每次请求前删除 Redis 中 `xihong_erp:dashboard_*` / `xihong_erp:annual_summary_*` 再请求一次
  - cache HIT：连续请求 30 次
- Result (local sampling):
  - cache MISS P95 ≈ 4432ms
  - cache HIT P95 ≈ 5ms

### PostgreSQL slow SQL alignment

- Environment:
  - `SHOW log_min_duration_statement;` = `2s`
- Command:
  - `docker logs --since 30m xihong_erp_postgres | findstr duration:`
- Observation:
  - 可定位到 `api.business_overview_operational_metrics_module` 等模块 SQL 的 `duration:` 记录（用于对齐后端慢请求/模块耗时）

## Rollback Notes

- 本阶段为“非破坏性契约增强”：新增 `meta` 不改变 `data`，如需回滚可直接回退相关 router 变更提交。

