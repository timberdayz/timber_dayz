# PostgreSQL Dashboard Granularity Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy cross-granularity fallback and misleading zero-filling so that dashboard data strictly follows the frontend-selected granularity.

**Architecture:** Fix the problem at the source in `mart` SQL, then adjust API/service aggregation so missing values stay missing instead of being silently coerced to zero. Keep the current route surface stable while making the returned numbers match the new collection standard.

**Tech Stack:** PostgreSQL views, FastAPI service layer, Python, pytest

---

## File Structure

**SQL assets**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_week_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_month_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\platform_month_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\annual_summary_shop_month.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\business_overview_operational_metrics_module.sql`

**Backend service layer**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\annual_cost_aggregate.py`

**Tests**

- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_granularity_alignment_sql.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_postgresql_dashboard_service_null_preservation.py`
- Modify: existing PostgreSQL dashboard/data-pipeline tests if needed

## Task 1: Remove weekly/monthly fallback to daily at the mart layer

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_week_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_month_kpi.sql`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_granularity_alignment_sql.py`

- [ ] **Step 1: Write failing SQL-level tests for weekly/monthly no-fallback behavior**

Cover these cases:
- monthly rows exist and daily rows also exist: month view must use monthly only
- monthly rows missing and daily rows exist: month view must not synthesize month data from daily
- weekly rows missing and daily rows exist: week view must not synthesize week data from daily

- [ ] **Step 2: Run the new tests to verify failure**

Run: `pytest backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`

Expected: FAIL because current SQL still falls back from `weekly/monthly` to `daily`.

- [ ] **Step 3: Rewrite `shop_week_kpi.sql` to read only `granularity = 'weekly'`**

Required changes:
- remove `weekly_order_candidates`
- remove `weekly_traffic_candidates`
- aggregate directly from weekly rows only
- preserve missing-side nullability instead of synthesizing rows from daily fallback

- [ ] **Step 4: Rewrite `shop_month_kpi.sql` to read only `granularity = 'monthly'`**

Required changes:
- remove `monthly_order_candidates`
- remove `monthly_traffic_candidates`
- aggregate directly from monthly rows only
- preserve missing-side nullability instead of synthesizing rows from daily fallback

- [ ] **Step 5: Run the SQL-level tests again**

Run: `pytest backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_granularity_alignment_sql.py sql/mart/shop_week_kpi.sql sql/mart/shop_month_kpi.sql
git commit -m "fix: remove dashboard granularity fallback"
```

## Task 2: Stop coercing missing metrics to zero in mart rollups

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_day_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_week_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_month_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\platform_month_kpi.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\annual_summary_shop_month.sql`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_granularity_alignment_sql.py`

- [ ] **Step 1: Extend tests to distinguish real zero from missing data**

Cover these cases:
- order-side data exists but traffic-side data missing: `visitor_count/page_views/conversion_rate` should be `NULL`
- traffic-side data exists but order-side data missing: `gmv/order_count/profit` should be `NULL`
- platform rollups should not convert all-null monthly traffic into `0`

- [ ] **Step 2: Run tests to verify current failure**

Run: `pytest backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`

Expected: FAIL because current SQL uses `COALESCE(..., 0)` broadly.

- [ ] **Step 3: Change mart views to preserve nullability for missing-side metrics**

Required changes:
- avoid unconditional `COALESCE(..., 0)` in final projection where it hides absent source rows
- only compute derived rates when required inputs are present and valid
- keep true aggregated zero if source rows exist and aggregate to zero

- [ ] **Step 4: Adjust `platform_month_kpi.sql` and `annual_summary_shop_month.sql` to respect null-preserving upstream values**

Required changes:
- stop forcing null visitor/profit/cost inputs to zero when that would misrepresent missing data
- ensure rollups only aggregate the selected granularity’s actual data

- [ ] **Step 5: Run tests again**

Run: `pytest backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_granularity_alignment_sql.py sql/mart/shop_day_kpi.sql sql/mart/shop_week_kpi.sql sql/mart/shop_month_kpi.sql sql/mart/platform_month_kpi.sql sql/mart/annual_summary_shop_month.sql
git commit -m "fix: preserve missing dashboard metrics as null"
```

## Task 3: Make service reducers preserve missing values instead of flattening to zero

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_postgresql_dashboard_service_null_preservation.py`

- [ ] **Step 1: Write failing service tests for null preservation**

Cover these cases:
- KPI rows with null `visitor_count` should not become `0`
- comparison rows with missing metrics should remain missing in the reduced payload where appropriate
- operational-metrics aggregation should not convert absent values to zero during accumulation

- [ ] **Step 2: Run the service tests to verify failure**

Run: `pytest backend/tests/test_postgresql_dashboard_service_null_preservation.py -q`

Expected: FAIL because `_to_float(None)` currently returns `0.0`.

- [ ] **Step 3: Replace blanket `_to_float(None) -> 0.0` behavior with explicit nullable helpers**

Required changes:
- add separate helpers for “numeric sum with null-ignore” versus “preserve null”
- update `reduce_business_overview_kpi_rows`
- update `reduce_business_overview_comparison_rows`
- update `aggregate_comparison_source_rows`
- update `reduce_annual_summary_kpi_rows`
- update operational metrics aggregation loop

- [ ] **Step 4: Re-run service tests**

Run: `pytest backend/tests/test_postgresql_dashboard_service_null_preservation.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_postgresql_dashboard_service_null_preservation.py backend/services/postgresql_dashboard_service.py
git commit -m "fix: preserve missing dashboard values in service reducers"
```

## Task 4: Fix annual cost aggregate to use correct parameter types and align with the dashboard chain

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\annual_cost_aggregate.py`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_annual_cost_aggregate.py`

- [ ] **Step 1: Write failing tests for the monthly parameter bug and alignment behavior**

Cover these cases:
- monthly query passes `date` objects, not strings, into asyncpg
- B-side GMV is non-zero when monthly order rows exist
- aggregate output aligns with `api.annual_summary_kpi_module` for the same month at total level

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest backend/tests/test_annual_cost_aggregate.py -q`

Expected: FAIL because the current service can collapse B-side values to zero after query failure.

- [ ] **Step 3: Fix date parameter typing and remove silent false-zero behavior**

Required changes:
- build `period_start/period_end` as `date` objects
- keep query failures observable
- do not silently return `gmv=0` / `total_cost_b=0` when the B query actually failed

- [ ] **Step 4: Decide the long-term posture**

Implement the minimal safe step now:
- keep service behavior correct for current callers
- add TODO or follow-up note if full migration to `semantic / mart / api` reuse is deferred

- [ ] **Step 5: Re-run annual cost tests**

Run: `pytest backend/tests/test_annual_cost_aggregate.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_annual_cost_aggregate.py backend/services/annual_cost_aggregate.py
git commit -m "fix: correct annual cost aggregate month typing"
```

## Task 5: Verify filter contract alignment for frontend-facing dashboard routes

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\api\dashboard.js`
- Test: route/service tests as appropriate

- [ ] **Step 1: Write failing tests or assertions for filter parameter propagation**

Cover these cases:
- KPI/comparison/operational-metrics currently accept `platform` only
- traffic/shop-ranking routes accept `platforms`/`shops`, but service calls ignore part of that filter surface
- frontend API contract must match backend route surface exactly

- [ ] **Step 2: Run the focused tests or validation script to verify failure**

Run the most focused available backend route tests or add one if absent.

- [ ] **Step 3: Choose one contract and make frontend/backend consistent**

Required rule:
- if the UI supports single-platform filtering, standardize on `platform`
- if multi-platform filtering is required, propagate `platforms` all the way through service queries
- do not keep parameters that are accepted but ignored

- [ ] **Step 4: Re-run route contract verification**

Expected: all accepted route params are either honored or removed.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/dashboard_api_postgresql.py frontend/src/api/dashboard.js
git commit -m "fix: align dashboard filter parameter contract"
```

## Task 6: End-to-end verification

**Files:**
- Verify only

- [ ] **Step 1: Run focused dashboard/data-pipeline tests**

Run:
- `pytest backend/tests/data_pipeline -q`
- `pytest backend/tests/test_postgresql_dashboard_service_null_preservation.py -q`
- `pytest backend/tests/test_annual_cost_aggregate.py -q`

- [ ] **Step 2: Run the dashboard smoke script**

Run:
- `python scripts/smoke_postgresql_dashboard_routes.py --base-url http://localhost:8001`

- [ ] **Step 3: Run one SQL audit sample manually**

Verify one real sample month/shop:
- no cross-granularity fallback
- missing metrics stay missing
- annual cost aggregate no longer returns false zeroes

- [ ] **Step 4: Commit any final stabilization edits**

```bash
git add .
git commit -m "test: verify dashboard granularity alignment"
```
