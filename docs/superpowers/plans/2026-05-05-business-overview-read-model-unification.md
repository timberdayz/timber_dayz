# Business Overview Read Model Unification (Follow-up Track Plan)

## Metadata

- Date: 2026-05-05
- Track: Parallel follow-up for project simplification
- Design SSOT: `docs/superpowers/specs/2026-04-30-business-overview-read-model-unification-design.md`
- Policy baseline: Online Query Policy (B) for business overview
- Status: Draft for implementation

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

- [ ] Enumerate the production read SQL per endpoint (kpi/comparison/operational/shop_racing/traffic_ranking/inventory_backlog)
- [ ] Record the violations against Online Query Policy (B)
- [ ] Define the intended source per endpoint (api vs mart fallback)

### Task 2: Remove KPI monthly runtime-heavy path

- [ ] Migrate KPI monthly reads to `api.business_overview_kpi_module` (or approved `mart` aggregate)
- [ ] Ensure labor efficiency computation remains correct and stable
- [ ] Confirm no request-time `raw_data` parsing remains in KPI runtime code

### Task 3: Unify traffic ranking read model usage

- [ ] Decide: (A) standardize reads on `api.business_overview_traffic_ranking_module`, or (B) retire the module and document the sanctioned `mart` read path
- [ ] Implement the chosen direction
- [ ] Ensure joins to dimension tables remain lightweight and predictable

### Task 4: Add enforcement gates

- [ ] Add/extend tests that capture executed SQL and assert it does not contain:
  - `raw_data->>`
  - `REGEXP_REPLACE`
  - `FROM b_class.`
- [ ] Add/extend tests that assert critical-tier modules prefer `api.*` read models

### Task 5: Optional bootstrap endpoint (after correctness gates)

- [ ] Add `/api/dashboard/business-overview/bootstrap` returning critical tier:
  - KPI
  - comparison
  - operational metrics
- [ ] Add staged frontend loading adoption only after backend is stable

## Verification Strategy

Minimum:

- run business-overview pipeline/dashboard unit tests under `backend/tests/data_pipeline`
- confirm the new gates fail when policy is violated (negative test scenario), then pass

## Rollback Strategy

- keep existing endpoints intact while improving read-model usage
- keep changes isolated so a rollback can revert only business overview service logic and tests

