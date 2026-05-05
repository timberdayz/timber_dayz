# Business Overview Read Model Unification (Follow-up Track Plan)

## Metadata

- Date: 2026-05-05
- Track: Parallel follow-up for project simplification
- Design SSOT: `docs/superpowers/specs/2026-04-30-business-overview-read-model-unification-design.md`
- Policy baseline: Online Query Policy (B) for business overview
- Status: Implemented and merged to `main` on 2026-05-05

## Objective

Unify the business overview read path so production homepage queries remain stable, fast, and consistent with the `b_class -> semantic -> mart -> api` architecture.

This track is successful only if the policy is enforceable via automated gates, not only documented.

## Scope

In scope:

- business overview dashboard endpoints under `backend/routers/dashboard_api_postgresql.py`
- `backend/services/postgresql_dashboard_service.py` business overview read paths
- read models under `sql/api_modules/business_overview_*`
- data pipeline dependencies and refresh targeting for impacted read models
- tests that enforce the Query Policy (B)

Out of scope:

- changing business formulas (unless required to restore consistency)
- broad dashboard redesign beyond the business overview page
- replacing the PostgreSQL dashboard architecture

## Work Items

### Task 1: Confirm current read paths and violations

- [x] Enumerate the production read SQL per endpoint (kpi/comparison/operational/shop_racing/traffic_ranking/inventory_backlog)
- [x] Record the violations against Online Query Policy (B)
- [x] Define the intended source per endpoint (api vs mart fallback)

#### Endpoint inventory (as-implemented in this worktree)

**Critical tier (homepage / bootstrap)**

- `GET /api/dashboard/business-overview/bootstrap` (cache: `dashboard_business_overview_bootstrap`)
  - Backend service calls:
    - `PostgresqlDashboardService.get_business_overview_kpi()` → `FROM api.business_overview_kpi_module`
    - `PostgresqlDashboardService.get_business_overview_comparison()` → `FROM api.business_overview_comparison_platform_module`
    - `PostgresqlDashboardService.get_business_overview_operational_metrics()` → `FROM api.business_overview_operational_metrics_module`
  - Policy: compliant with Online Query Policy (B) (no `raw_data->>`, no `REGEXP_REPLACE`, no `FROM b_class.`)

- `GET /api/dashboard/business-overview/kpi` (cache: `dashboard_kpi`)
  - Service: `get_business_overview_kpi()`
  - Read models:
    - monthly: `FROM api.business_overview_kpi_module` (primary)
    - non-monthly: `FROM mart.platform_*_kpi` (fallback, allowed)
  - Policy: compliant (monthly path no longer parses raw JSON)

- `GET /api/dashboard/business-overview/comparison` (cache: `dashboard_comparison`)
  - Service: `get_business_overview_comparison()`
  - Read models: `FROM api.business_overview_comparison_platform_module` (+ `a_class.*` targets via ORM helper)
  - Policy: compliant

- `GET /api/dashboard/business-overview/operational-metrics` (cache: `dashboard_operational_metrics`)
  - Service: `get_business_overview_operational_metrics()`
  - Read models: `FROM api.business_overview_operational_metrics_module` (+ `a_class.*` targets + operating expenses summary helper)
  - Policy: compliant

**Secondary tier (non-bootstrap / potentially heavy)**

- `GET /api/dashboard/business-overview/traffic-ranking` (cache: `dashboard_traffic_ranking`)
  - Service: `get_business_overview_traffic_ranking()`
  - Read models: `FROM api.business_overview_traffic_ranking_module` (+ joins to `core.*` dimensions)
  - Policy: compliant

- `GET /api/dashboard/business-overview/shop-racing` (cache: `dashboard_shop_racing`)
  - Service: `get_business_overview_shop_racing()`
  - Read models:
    - monthly: `FROM api.business_overview_shop_racing_monthly_module`
    - non-monthly: `FROM api.business_overview_shop_racing_module`
  - Policy: compliant (legacy non-module path removed)

- `GET /api/dashboard/business-overview/inventory-backlog` (cache: `dashboard_inventory_backlog`)
  - Service: `get_business_overview_inventory_backlog()`
  - Read models:
    - summary: `FROM api.business_overview_inventory_backlog_module` / `FROM api.inventory_backlog_summary_module`
    - detailed rows: `FROM api.business_overview_inventory_backlog_module`
  - Policy: compliant (online service path no longer reads `semantic.fact_orders_atomic`)

- `GET /api/dashboard/clearance-ranking` (cache: `dashboard_clearance_ranking`)
  - Service: `get_clearance_ranking()`
  - Read models: `FROM api.clearance_ranking_module`
  - Policy: compliant (legacy request-time raw JSON / `b_class` parsing removed)

### Task 2: Remove KPI monthly runtime-heavy path

- [x] Migrate KPI monthly reads to `api.business_overview_kpi_module` (or approved `mart` aggregate)
- [x] Ensure labor efficiency computation remains correct and stable
- [x] Confirm no request-time `raw_data` parsing remains in KPI runtime code

### Task 3: Unify traffic ranking read model usage

- [x] Decide: (A) standardize reads on `api.business_overview_traffic_ranking_module`, or (B) retire the module and document the sanctioned `mart` read path
- [x] Implement the chosen direction
- [x] Ensure joins to dimension tables remain lightweight and predictable

### Task 4: Add enforcement gates

- [x] Add/extend tests that capture executed SQL and assert it does not contain:
  - `raw_data->>`
  - `REGEXP_REPLACE`
  - `FROM b_class.`
- [x] Extend the online query gate to forbid `FROM semantic.fact_*_atomic` on governed endpoints
- [x] Add/extend tests that assert critical-tier modules prefer `api.*` read models

Note:

- A broader dashboard gate now also covers store analysis, annual summary, and cost analysis modules to prevent regressions in other page modules.

### Task 5: Optional bootstrap endpoint (after correctness gates)

- [x] Add `/api/dashboard/business-overview/bootstrap` returning critical tier:
  - KPI
  - comparison
  - operational metrics
- [x] Add staged frontend loading adoption only after backend is stable

## Verification Strategy

Minimum:

- run business-overview pipeline/dashboard unit tests under `backend/tests/data_pipeline`
- confirm the new gates fail when policy is violated (negative test scenario), then pass

## Rollback Strategy

- keep existing endpoints intact while improving read-model usage
- keep changes isolated so a rollback can revert only business overview service logic and tests
