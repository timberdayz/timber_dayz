# Business Overview And Annual Summary Aggregate Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild dashboard summary SQL so Business Overview (excluding inventory/clearance) and Annual Summary use platform/company aggregate logic that respects domain-specific key semantics and strict day/week/month source selection without breaking unrelated cost/profit chains.

**Architecture:** Keep the existing `B -> semantic -> mart -> api -> backend -> frontend` pipeline, but replace the current dashboard summary branch that incorrectly depends on shop-level full joins and strict completeness gating. Introduce dashboard-specific platform aggregate marts/api views for KPI/comparison/annual-summary while leaving non-dashboard cost/profit modules intact.

**Tech Stack:** PostgreSQL views, FastAPI, async SQLAlchemy, Vue 3, pytest, node test

---

## File Structure

### New SQL assets
- Create: `sql/mart/platform_day_kpi.sql`
- Create: `sql/mart/platform_week_kpi.sql`
- Modify: `sql/mart/platform_month_kpi.sql`
- Modify: `sql/api_modules/business_overview_kpi_module.sql`
- Create: `sql/api_modules/business_overview_comparison_platform_module.sql`
- Modify: `sql/api_modules/annual_summary_kpi_module.sql`
- Modify: `sql/api_modules/annual_summary_trend_module.sql`
- Modify: `sql/api_modules/annual_summary_platform_share_module.sql`

### Backend code
- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/routers/dashboard_api_postgresql.py`

### Frontend code
- Modify: `frontend/src/views/BusinessOverview.vue`
- Optional minimal API compatibility touch only if required: `frontend/src/api/index.js`

### Tests
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Modify: `backend/tests/data_pipeline/test_dashboard_router_switch.py`
- Create: `backend/tests/data_pipeline/test_dashboard_platform_aggregate_sql.py`
- Create: `frontend/scripts/businessOverviewKpiGranularity.test.mjs`

---

### Task 1: Lock down platform aggregate KPI SQL contract

**Files:**
- Create: `backend/tests/data_pipeline/test_dashboard_platform_aggregate_sql.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`

- [ ] **Step 1: Write the failing SQL/service tests**

Add tests that assert:
- platform KPI can produce non-null values even when orders and traffic use different shop keys under the same platform
- monthly KPI no longer nulls the whole platform because one shop row is null
- service KPI query supports `granularity` + `date` and reads the correct platform aggregate source
- annual summary KPI is derived from platform aggregate month rows, not strict shop completeness gating

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_dashboard_platform_aggregate_sql.py backend\tests\data_pipeline\test_postgresql_dashboard_service.py -k "platform_aggregate or business_overview_kpi or annual_summary_kpi" -q
```
Expected: FAIL because current SQL/service still use shop-level joins and month-only KPI query shape.

- [ ] **Step 3: Implement minimal SQL/service support**

Implement dashboard-specific platform aggregate logic:
- `sql/mart/platform_day_kpi.sql`: aggregate daily orders and daily analytics by `(period_date, platform_code)` and compute derived KPI at platform level
- `sql/mart/platform_week_kpi.sql`: aggregate weekly orders and weekly analytics by `(period_week, platform_code)`
- `sql/mart/platform_month_kpi.sql`: aggregate monthly orders and monthly analytics by `(period_month, platform_code)` without `COUNT(col)=COUNT(*)` gating
- `backend/services/postgresql_dashboard_service.py`: make KPI query route by granularity to platform aggregate marts

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_dashboard_platform_aggregate_sql.py backend\tests\data_pipeline\test_postgresql_dashboard_service.py -k "platform_aggregate or business_overview_kpi or annual_summary_kpi" -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/data_pipeline/test_dashboard_platform_aggregate_sql.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py sql/mart/platform_day_kpi.sql sql/mart/platform_week_kpi.sql sql/mart/platform_month_kpi.sql backend/services/postgresql_dashboard_service.py
 git commit -m "fix: add platform aggregate dashboard kpi sources"
```

### Task 2: Rebuild Business Overview KPI API contract for day/week/month

**Files:**
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Modify: `backend/tests/data_pipeline/test_dashboard_router_switch.py`

- [ ] **Step 1: Write the failing router tests**

Add tests that assert:
- `/api/dashboard/business-overview/kpi` accepts `granularity` and `date`
- legacy `month` remains supported for monthly requests
- router forwards the normalized granularity/date pair to service

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_postgresql_dashboard_router.py backend\tests\data_pipeline\test_dashboard_router_switch.py -k "business_overview_kpi" -q
```
Expected: FAIL because router currently only supports `month`.

- [ ] **Step 3: Implement minimal router changes**

Update `dashboard_api_postgresql.py`:
- accept `granularity`, `date`, `month`, `platform`
- normalize `month` into monthly `date`
- call `service.get_business_overview_kpi(granularity=..., target_date=..., platform=...)`

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_postgresql_dashboard_router.py backend\tests\data_pipeline\test_dashboard_router_switch.py -k "business_overview_kpi" -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/dashboard_api_postgresql.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/data_pipeline/test_dashboard_router_switch.py
 git commit -m "feat: support granular business overview kpi requests"
```

### Task 3: Move Business Overview comparison to platform aggregate source

**Files:**
- Create: `sql/api_modules/business_overview_comparison_platform_module.sql`
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`

- [ ] **Step 1: Write the failing comparison tests**

Add tests that assert:
- platform comparison reads day/week/month platform aggregate sources
- monthly average/current/previous calculations still work
- comparison no longer depends on `mart.shop_*_kpi`

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_postgresql_dashboard_service.py -k "comparison_reads_from_platform or comparison_platform" -q
```
Expected: FAIL because service currently queries `mart.shop_*_kpi`.

- [ ] **Step 3: Implement minimal comparison source change**

- add platform comparison api view or direct platform mart query path
- update service to use platform aggregates for current/previous/average windows
- preserve target loading behavior unless target logic is shown incorrect by tests

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_postgresql_dashboard_service.py -k "comparison_reads_from_platform or comparison_platform" -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add sql/api_modules/business_overview_comparison_platform_module.sql backend/services/postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py
 git commit -m "fix: use platform aggregates for overview comparison"
```

### Task 4: Rebuild Annual Summary KPI/trend/platform share on platform-month aggregate

**Files:**
- Modify: `sql/api_modules/annual_summary_kpi_module.sql`
- Modify: `sql/api_modules/annual_summary_trend_module.sql`
- Modify: `sql/api_modules/annual_summary_platform_share_module.sql`
- Modify: `backend/tests/data_pipeline/test_dashboard_platform_aggregate_sql.py`
- Modify: `backend/tests/data_pipeline/test_dashboard_router_switch.py`

- [ ] **Step 1: Write the failing annual summary tests**

Add tests that assert:
- annual summary KPI returns month-level company aggregate even when shop-level rows are partial
- trend returns non-null monthly GMV/profit from platform-month aggregate
- platform share returns platform GMV without strict shop completeness gating
- target completion uses non-null achieved GMV when KPI is available

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_dashboard_platform_aggregate_sql.py backend\tests\data_pipeline\test_dashboard_router_switch.py -k "annual_summary" -q
```
Expected: FAIL because current annual summary modules read `mart.annual_summary_shop_month` with strict null gating.

- [ ] **Step 3: Implement minimal annual summary rewiring**

- make annual summary KPI/trend/platform share read platform-month aggregate + platform-month cost aggregate
- keep `annual_summary_by_shop_module` untouched for now except compatibility if needed
- keep cost math semantics unchanged; only move aggregation boundary to platform/company level

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_dashboard_platform_aggregate_sql.py backend\tests\data_pipeline\test_dashboard_router_switch.py -k "annual_summary" -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add sql/api_modules/annual_summary_kpi_module.sql sql/api_modules/annual_summary_trend_module.sql sql/api_modules/annual_summary_platform_share_module.sql backend/tests/data_pipeline/test_dashboard_platform_aggregate_sql.py backend/tests/data_pipeline/test_dashboard_router_switch.py
 git commit -m "fix: rebase annual summary on platform aggregate kpi"
```

### Task 5: Align Business Overview operational metrics contract to month semantics

**Files:**
- Modify: `frontend/src/views/BusinessOverview.vue`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Create: `frontend/scripts/businessOverviewKpiGranularity.test.mjs`

- [ ] **Step 1: Write the failing frontend/contract tests**

Add tests that assert:
- Business Overview KPI UI exposes daily/weekly/monthly selector and sends correct request params
- operational metrics control uses month semantics instead of day semantics
- no request path claims day selection while calling month-only backend

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
node --test frontend\scripts\businessOverviewKpiGranularity.test.mjs
```
Expected: FAIL because KPI is currently monthly-only and operational metrics uses a day picker with month API.

- [ ] **Step 3: Implement minimal frontend changes**

- add KPI granularity controls in `BusinessOverview.vue`
- route KPI requests through `granularity + date`
- change operational metrics selector to month picker or otherwise align visible control with actual month contract

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
node --test frontend\scripts\businessOverviewKpiGranularity.test.mjs
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/BusinessOverview.vue frontend/scripts/businessOverviewKpiGranularity.test.mjs backend/tests/data_pipeline/test_postgresql_dashboard_router.py
 git commit -m "feat: align overview kpi and operational metric filters"
```

### Task 6: Full targeted regression for audited modules

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run backend regression suite**

Run:
```powershell
python -m pytest backend\tests\data_pipeline\test_dashboard_platform_aggregate_sql.py backend\tests\data_pipeline\test_postgresql_dashboard_service.py backend\tests\data_pipeline\test_postgresql_dashboard_router.py backend\tests\data_pipeline\test_dashboard_router_switch.py -q
```
Expected: PASS

- [ ] **Step 2: Run frontend regression suite**

Run:
```powershell
node --test frontend\scripts\businessOverviewKpiGranularity.test.mjs frontend\scripts\businessOverviewBoardLimits.test.mjs
```
Expected: PASS

- [ ] **Step 3: Record verification evidence**

Update `findings.md` and `progress.md` with final audited modules, defects fixed, and commands/results.

- [ ] **Step 4: Commit**

```powershell
git add findings.md progress.md
 git commit -m "docs: record dashboard aggregate audit verification"
```
