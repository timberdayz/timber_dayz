# Store Analysis Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `StoreAnalysis` as a PostgreSQL-first store drill-down page with Shopee hourly daily traffic support and TikTok capability-aware daily fallback, without destabilizing the active sync pipeline.

**Architecture:** Keep the raw sync chain unchanged and add derived assets on top of the current analytics pipeline. Build a new store-analysis traffic path through `semantic -> mart -> api -> backend -> frontend`, with Shopee-only hourly mart support, platform capability metadata, and a capability-driven frontend that does not fabricate unsupported grains.

**Tech Stack:** PostgreSQL views, FastAPI, SQLAlchemy async, Vue 3, Element Plus, Node test runner, pytest

---

## File Structure

**SQL / data pipeline**

- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_hour_traffic_kpi.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_capability_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_traffic_summary_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_traffic_trend_module.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\data_pipeline\refresh_registry.py`

**Backend**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`

**Frontend**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\api\dashboard.js`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\store\StoreAnalytics.vue`

**Tests**

- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_store_analysis_hour_traffic_sql.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_store_analysis_dashboard_routes.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\scripts\storeAnalysisCapabilityUi.test.mjs`

## Task 1: Add Store-Hour Traffic Mart

**Files:**
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\shop_hour_traffic_kpi.sql`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_store_analysis_hour_traffic_sql.py`

- [ ] **Step 1: Write the failing SQL asset test**

Cover these assertions:
- `mart.shop_hour_traffic_kpi` exists
- It reads from `semantic.fact_analytics_atomic`
- It groups by `platform_code`, `shop_id`, `metric_date`, `period_hour`
- It aggregates `visitor_count` and `page_views`
- It only includes rows with non-null hourly timestamps

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py -q`
Expected: FAIL because the mart file does not exist yet.

- [ ] **Step 3: Create the minimal mart SQL**

Implementation requirements:
- Read from `semantic.fact_analytics_atomic`
- Derive `period_hour` from `period_start_time`
- Filter to `platform_code = 'shopee'`
- Filter to rows with non-null `period_start_time`
- Group by store and hour bucket
- Sum `visitor_count` and `page_views`
- Recompute `conversion_rate` from aggregated inputs, do not average precomputed percentages blindly
- Output `source_row_count` for audit visibility

- [ ] **Step 4: Run the mart SQL test to verify it passes**

Run: `pytest backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py sql/mart/shop_hour_traffic_kpi.sql
git commit -m "feat: add shopee hourly traffic mart"
```

## Task 2: Add Store Analysis API Modules

**Files:**
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_capability_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_traffic_summary_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\store_analysis_traffic_trend_module.sql`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\data_pipeline\refresh_registry.py`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_store_analysis_hour_traffic_sql.py`

- [ ] **Step 1: Extend the failing SQL test to cover API modules**

Add assertions that:
- `api.store_analysis_capability_module` exists
- `api.store_analysis_traffic_summary_module` exists
- `api.store_analysis_traffic_trend_module` exists
- trend module can express both `requested_granularity` and `effective_granularity`
- capability module exposes `supports_hourly_daily`

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py -q`
Expected: FAIL because the API module files do not exist yet.

- [ ] **Step 3: Create the capability module**

Required fields:
- `platform_code`
- `shop_id`
- `supports_hourly_daily`
- `supported_daily_mode`
- `supported_long_range_mode`

Rules:
- Shopee returns hourly support for daily mode
- TikTok returns daily support for daily mode

- [ ] **Step 4: Create the traffic summary module**

Required fields:
- `platform_code`
- `shop_id`
- `period_start`
- `period_end`
- `visitor_count`
- `page_views`
- `conversion_rate`
- `page_views_per_visitor`

Data sources:
- use existing day/week/month marts where appropriate

- [ ] **Step 5: Create the traffic trend module**

Required behavior:
- support `daily`, `weekly`, `monthly`, `quarterly`, `yearly`
- translate those requests into effective grains
- use `mart.shop_hour_traffic_kpi` for Shopee daily
- use day-level marts for TikTok daily and all weekly/monthly/quarterly requests
- use month-level marts for yearly

- [ ] **Step 6: Register new targets in refresh registry**

Update dependencies and target paths in:
- `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 7: Run SQL tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py backend/services/data_pipeline/refresh_registry.py sql/api_modules/store_analysis_capability_module.sql sql/api_modules/store_analysis_traffic_summary_module.sql sql/api_modules/store_analysis_traffic_trend_module.sql
git commit -m "feat: add store analysis traffic api modules"
```

## Task 3: Add Backend Store Analysis Routes

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_store_analysis_dashboard_routes.py`

- [ ] **Step 1: Write the failing route/service test**

Cover these endpoints:
- `GET /api/dashboard/store-analysis/capabilities`
- `GET /api/dashboard/store-analysis/traffic-summary`
- `GET /api/dashboard/store-analysis/traffic-trend`

Cover these behaviors:
- invalid or missing required params return parameter errors
- route payload includes `requested_granularity` and `effective_granularity` where applicable
- TikTok daily request does not return hourly effective grain
- Shopee daily request does return hourly effective grain

- [ ] **Step 2: Run the route test to verify it fails**

Run: `pytest backend/tests/test_store_analysis_dashboard_routes.py -q`
Expected: FAIL because the routes and service methods do not exist yet.

- [ ] **Step 3: Add service methods in `postgresql_dashboard_service.py`**

Required methods:
- `get_store_analysis_capabilities(...)`
- `get_store_analysis_traffic_summary(...)`
- `get_store_analysis_traffic_trend(...)`

Rules:
- validate platform and granularity combinations
- resolve effective granularity explicitly
- never synthesize unsupported hourly TikTok output
- keep cache-friendly, deterministic parameter handling

- [ ] **Step 4: Add routes in `dashboard_api_postgresql.py`**

Required routes:
- `/api/dashboard/store-analysis/capabilities`
- `/api/dashboard/store-analysis/traffic-summary`
- `/api/dashboard/store-analysis/traffic-trend`

Rules:
- reuse the current `success_response` / `error_response` pattern
- integrate with `_resolve_cached_payload`
- keep naming aligned with existing dashboard router style

- [ ] **Step 5: Run route tests to verify they pass**

Run: `pytest backend/tests/test_store_analysis_dashboard_routes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_store_analysis_dashboard_routes.py backend/services/postgresql_dashboard_service.py backend/domains/business/routers/dashboard_api_postgresql.py
git commit -m "feat: add store analysis dashboard routes"
```

## Task 4: Rebuild StoreAnalytics Frontend Around Capability-Aware APIs

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\api\dashboard.js`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\store\StoreAnalytics.vue`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\scripts\storeAnalysisCapabilityUi.test.mjs`

- [ ] **Step 1: Write the failing frontend test**

Cover these UI expectations:
- the page uses dashboard-native store-analysis APIs instead of `/store-analytics/*`
- Shopee-capable state shows hourly daily option
- TikTok-capable state hides or disables hourly daily option
- the page renders a clear message when hourly is unsupported

- [ ] **Step 2: Run the frontend test to verify it fails**

Run: `node --test frontend/scripts/storeAnalysisCapabilityUi.test.mjs`
Expected: FAIL because the page still references legacy endpoints and mock behavior.

- [ ] **Step 3: Add dashboard API methods**

Add to `frontend/src/api/dashboard.js`:
- `queryStoreAnalysisCapabilities`
- `queryStoreAnalysisTrafficSummary`
- `queryStoreAnalysisTrafficTrend`

- [ ] **Step 4: Replace legacy page logic in `StoreAnalytics.vue`**

Required changes:
- remove dependency on `/store-analytics/*`
- remove hardcoded mock shop list usage as the authoritative source
- load capability payload after store selection
- gate granularity controls from capability response
- render KPI summary from `traffic-summary`
- render trend chart from `traffic-trend`

Do not add:
- legacy mock detail dialogs
- fake hourly TikTok rows
- opaque health-score-first layout

- [ ] **Step 5: Keep the page shape intentionally small in V1**

Required layout:
- filter bar
- capability-aware granularity control
- KPI summary block
- one traffic trend chart
- one comparison/explanation block or concise empty state

Avoid in V1:
- multi-tab dashboard sprawl
- placeholder risk/alert sections
- TODO-backed fake detail drawers

- [ ] **Step 6: Run frontend test to verify it passes**

Run: `node --test frontend/scripts/storeAnalysisCapabilityUi.test.mjs`
Expected: PASS

- [ ] **Step 7: Run frontend build verification**

Run: `npm --prefix frontend run build`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/dashboard.js frontend/src/views/store/StoreAnalytics.vue frontend/scripts/storeAnalysisCapabilityUi.test.mjs
git commit -m "feat: rebuild store analysis traffic page"
```

## Task 5: Verify End-to-End Contract And Guardrails

**Files:**
- Verify only
- Optionally update docs if route references or acceptance records need sync

- [ ] **Step 1: Run backend SQL and route tests**

Run:

```bash
pytest backend/tests/data_pipeline/test_store_analysis_hour_traffic_sql.py -q
pytest backend/tests/test_store_analysis_dashboard_routes.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend verification**

Run:

```bash
node --test frontend/scripts/storeAnalysisCapabilityUi.test.mjs
npm --prefix frontend run build
```

Expected: PASS

- [ ] **Step 3: Manually verify guardrails**

Check:
- Shopee daily request renders hourly points
- TikTok daily request renders daily points only
- no request goes to `/store-analytics/*`
- existing sync code paths remain untouched
- no new raw-table DDL was introduced for `b_class.fact_*_analytics_*`

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "test: verify store analysis redesign flow"
```

## Notes For Execution

- Do not change the sync contract in `DataIngestionService` or `RawDataImporter` for V1.
- Do not change `b_class.fact_shopee_analytics_daily` or `b_class.fact_tiktok_analytics_daily` schema in V1.
- Do not rewrite raw-table unique index or `ON CONFLICT` strategy as part of this feature.
- Keep Shopee hourly dedupe in derived mart/API layers.
- Keep TikTok hourly support as a capability gap, not a fabricated fallback.
- If store identity remains unresolved in the inspected dataset, prefer derived filtering safeguards and explicit empty states over pretending the data is store-clean.

## Execution Order

1. Task 1: add Shopee hourly mart
2. Task 2: add capability/summary/trend API modules
3. Task 3: add backend routes and service methods
4. Task 4: rebuild frontend store analysis page
5. Task 5: verify contracts and guardrails

