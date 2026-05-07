# Business Overview Standardization (Phase-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Business Overview（排除 inventory-backlog）5 个模块 + bootstrap 的参数/输出/分层/性能策略标准化，并给出可复现的验收证据（pytest + probes + Postgres 慢 SQL）。

**Architecture:** 以“service/router 参数归一化 + module 响应 envelope(meta+data) + api_modules SQL 薄化”为主线；必要时在 mart/semantic 增补可复用聚合或 MV+索引，并在 `refresh_registry.py` 明确依赖；每个模块改造后立即跑探针与回归验证。

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL 15, Redis 7, httpx, pytest

---

## Execution Preconditions

- 后端运行在 `http://127.0.0.1:8001`（本地）
- Docker 运行：`xihong_erp_postgres`、`xihong_erp_redis`（用于慢 SQL 与缓存验证）
- Postgres 允许慢 SQL 证据采集：`SHOW log_min_duration_statement;` 建议为 `2s`

## Evidence Artifacts (Outputs)

- `temp/outputs/performance_regression_summary_latest.json`
- `temp/outputs/business_overview_split_probe_latest.json`
- `temp/outputs/business_overview_long_run_latest.json`
- `docker logs xihong_erp_postgres` 中的 `duration:` 片段（按模块对齐）

## Affected Code Areas (File Map)

**Backend router/service**
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/services/cache_warmup_service.py`（如需统一 bootstrap warmup 行为）

**SQL modules / pipeline**
- Modify: `sql/api_modules/business_overview_traffic_ranking_module.sql`
- Modify: `sql/api_modules/business_overview_comparison_module.sql`
- Modify: `sql/api_modules/business_overview_kpi_module.sql`
- Modify: `sql/api_modules/business_overview_operational_metrics_module.sql`
- Modify: `sql/api_modules/business_overview_shop_racing_module.sql`
- Modify (if needed): `sql/mart/*` / `sql/semantic/*`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

**Tests / probes**
- Modify/Add: `backend/tests/data_pipeline/test_business_overview_module_consistency.py`
- Run: `python scripts/verify_performance_regression.py --mode local --base-url http://127.0.0.1:8001`
- Run: `python scripts/business_overview_split_probe.py --rounds 10`
- Run: `python scripts/business_overview_long_run.py --duration-seconds 120 --interval-seconds 30`

---

### Task 1: Add Unified Param Normalization + Response Envelope

**Files:**
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Test: `backend/tests/data_pipeline/test_business_overview_module_consistency.py`

- [ ] **Step 1: Write failing contract tests (envelope + normalization)**

Add tests that call:
- `/api/dashboard/business-overview/kpi` with `month=...` and assert response contains `meta.period_key`
- `/api/dashboard/business-overview/comparison` with `date=YYYY-MM` and assert normalization yields monthly `period_key=YYYY-MM-01`
- assert each endpoint returns `{meta, data}` shape

Run: `python -m pytest -q backend/tests/data_pipeline/test_business_overview_module_consistency.py`
Expected: FAIL (missing envelope/normalization fields)

- [ ] **Step 2: Implement normalization helper**

Implement a single helper used by all BO endpoints:
- inputs: `granularity`, `month/date/date_value`, `platform/platform_code`, `shop_id`
- output: canonical dict `{granularity, period_key, platform_code, shop_id}`
- log normalized params once per request (debug/info)

- [ ] **Step 3: Wrap module returns into envelope**

Ensure each BO service method returns:
- `meta` with normalized params + generated_at + cache hint (hit/miss if available)
- `data` is module payload (existing structure preserved inside `data` to reduce diff)

- [ ] **Step 4: Run contract tests**

Run: `python -m pytest -q backend/tests/data_pipeline/test_business_overview_module_consistency.py`
Expected: PASS

- [ ] **Step 5: Commit**

Commit message pattern:
- `feat(business-overview): unify params + response envelope`

---

### Task 2: Standardize `traffic-ranking` (thin SQL + consistent filters)

**Files:**
- Modify: `sql/api_modules/business_overview_traffic_ranking_module.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py` (if dependencies change)
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py` (existing route contract)

- [ ] **Step 1: Add failing test for normalized filter usage**

Assert query uses `period_key` consistently (monthly/week/day) and respects `platform_code` filter when provided.

- [ ] **Step 2: Thin SQL**

Ensure api module only selects required fields and relies on mart aggregates; avoid expensive joins in api layer.

- [ ] **Step 3: Ensure index/mv requirements**

If module needs new helper aggregate: add in `sql/mart/...` and register in refresh graph.

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k traffic`

- [ ] **Step 5: Commit**

Commit: `perf(traffic-ranking): standardize module query`

---

### Task 3: Standardize `comparison`

**Files:**
- Modify: `sql/api_modules/business_overview_comparison_module.sql`
- Modify: `sql/api_modules/business_overview_comparison_platform_module.sql` (if needed)
- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

- [ ] **Step 1: Add failing tests for period range + granularity**
- [ ] **Step 2: Align comparison to canonical period_key semantics**
- [ ] **Step 3: Keep api module thin (push heavy work to mart)**
- [ ] **Step 4: Run `pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k comparison`**
- [ ] **Step 5: Commit `perf(comparison): standardize module contract`**

---

### Task 4: Standardize `kpi`

**Files:**
- Modify: `sql/api_modules/business_overview_kpi_module.sql`
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

- [ ] **Step 1: Add failing tests for `platform_code` filter**
- [ ] **Step 2: Ensure api module exposes `period_key` and platform_code consistently**
- [ ] **Step 3: Run `pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k kpi`**
- [ ] **Step 4: Commit `perf(kpi): standardize module contract`**

---

### Task 5: Standardize `operational-metrics` (slow-path priority)

**Files:**
- Modify: `sql/api_modules/business_overview_operational_metrics_module.sql`
- Modify: `sql/mart/...` or `sql/semantic/...` (if need helper aggregates/MV)
- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

- [ ] **Step 1: Add failing perf guard (no timeout, stable under MISS)**

Run probe pre-change to capture baseline:
- `python scripts/business_overview_split_probe.py --rounds 10`

- [ ] **Step 2: Thin SQL + add missing indexes/MV**

If slow SQL originates from identity resolution or heavy joins, push to mart/semantic and materialize as needed.

- [ ] **Step 3: Verify Postgres slow logs show reduced duration**

Check: `docker logs xihong_erp_postgres | findstr duration: | findstr business_overview_operational_metrics_module`

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k operational`

- [ ] **Step 5: Commit `perf(operational-metrics): standardize + speedup`**

---

### Task 6: Standardize `shop-racing`

**Files:**
- Modify: `sql/api_modules/business_overview_shop_racing_module.sql`
- Modify: `sql/api_modules/business_overview_shop_racing_monthly_module.sql` (if needed)
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

- [ ] **Step 1: Align to canonical params (granularity/period_key/platform_code/shop_id)**
- [ ] **Step 2: Ensure MV usage/refresh registry correctness**
- [ ] **Step 3: Run `pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k shop_racing`**
- [ ] **Step 4: Commit `perf(shop-racing): standardize module contract`**

---

### Task 7: Standardize `bootstrap` (aggregation + meta/warnings + cache behavior)

**Files:**
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Modify: `backend/services/postgresql_dashboard_service.py`
- Test: `backend/tests/data_pipeline/test_business_overview_module_consistency.py`

- [ ] **Step 1: Add failing tests for bootstrap meta + submodule inclusion**
- [ ] **Step 2: Ensure bootstrap uses normalized params and returns meta/data**
- [ ] **Step 3: Keep breakdown logs for kpi/comparison/operational/traffic/shop-racing**
- [ ] **Step 4: Run `pytest -q backend/tests/data_pipeline/test_business_overview_module_consistency.py`**
- [ ] **Step 5: Commit `feat(bootstrap): unify aggregation contract`**

---

### Task 8: Final Acceptance + Evidence Package

**Files:**
- Create/Modify: `docs/superpowers/reports/2026-05-07-business-overview-phase2-standardization-acceptance.md`

- [ ] **Step 1: Run unified regression**

Run: `python scripts/verify_performance_regression.py --mode local --base-url http://127.0.0.1:8001`
Expected: exit 0, all_passed true

- [ ] **Step 2: Run probes**

Run:
- `python scripts/business_overview_split_probe.py --rounds 10`
- `python scripts/business_overview_long_run.py --duration-seconds 120 --interval-seconds 30`

- [ ] **Step 3: Capture Postgres slow SQL snippets**

Command:
- `docker logs --since 30m xihong_erp_postgres | findstr duration:`

- [ ] **Step 4: Write acceptance report**

Include:
- thresholds (bootstrap MISS/HIT)
- probe summaries (p95)
- slow SQL alignment evidence
- rollback notes

- [ ] **Step 5: Commit**

Commit: `report: business overview phase-2 acceptance`

