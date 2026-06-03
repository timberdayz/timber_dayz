# Safe Change Zones

This document defines which layers are low-risk, high-risk, or do-not-touch for common product, dashboard, and data-flow work.

Use it before changing any dashboard, settlement, performance, expense, or shop-identity related behavior.

## Core Data Flow

Active runtime data flow:

```text
b_class raw -> semantic -> mart -> api -> backend router -> frontend
```

Layer intent:

- `b_class`: raw collected facts, append-oriented ingestion truth
- `sql/semantic/`: normalization, field parsing, identity resolution, atomic facts
- `sql/mart/`: reusable aggregates shared by multiple pages/modules
- `sql/api_modules/`: page-facing read models and stable query contracts
- `backend/domains/*/routers/`: API entrypoints and runtime policy gates
- `frontend/src/api/`: frontend read/write wrappers
- `frontend/src/domains/`: page and component rendering

## Safe Zones

These are the preferred change zones for routine product work. Default to these first.

### 1. Frontend Rendering And Interaction

Best for:

- shop display name changes
- alias + canonical-name dual display
- table readability improvements
- filter UX
- empty-state handling
- badges, status labels, and visual grouping

Examples:

- `frontend/src/domains/**`
- `frontend/src/utils/shopDisplay.js`
- `frontend/src/api/*` wrapper additions that do not change backend contracts

Why safe:

- does not change raw data truth
- does not change metric semantics
- failures tend to be page-local

### 2. Backend Read-Only Reference / Aggregation Layer

Best for:

- new production-safe reference endpoints
- display-only enrichment
- runtime readiness and diagnostics
- safe contract aggregation over existing data

Examples:

- `GET /api/reference/shop-directory`
- dashboard asset readiness reporting
- page-level read-model composition in routers/services

Why safe:

- preserves lower-layer facts
- can be added incrementally
- easier to validate by direct endpoint checks

### 3. Runtime Diagnostics And Governance

Best for:

- bootstrap checks
- asset-state consistency
- logging and traceability
- failure visibility improvements

Examples:

- `backend/services/data_pipeline/dashboard_bootstrap.py`
- `backend/services/data_pipeline/refresh_runner.py`
- deploy/bootstrap helper scripts

Why safe:

- improves observability without changing business semantics

## High-Risk Zones

Change these only when you have concrete evidence the issue originates here, and validate with targeted regression tests.

### 1. Semantic Atomic Fact SQL

Examples:

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic_mv.sql`
- `sql/semantic/analytics_atomic.sql`
- `sql/semantic/analytics_monthly_atomic_mv.sql`
- `sql/semantic/shop_identity_resolution_candidates.sql`

Why risky:

- shared by many downstream marts and API modules
- changes can silently reassign shop identity
- affects both correctness and performance

Only change when:

- display-layer or read-model fixes are insufficient
- evidence shows the semantic layer is wrong or too slow
- affected downstream modules are explicitly enumerated and re-tested

### 2. Mart KPI Aggregates

Examples:

- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/platform_day_kpi.sql`
- `sql/mart/platform_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`
- `sql/mart/platform_month_kpi.sql`

Why risky:

- shared by multiple dashboards and business modules
- one metric change can affect many pages at once

Only change when:

- the issue is truly metric-definition or aggregation logic
- impacted API modules are listed and revalidated

### 3. API Module SQL

Examples:

- `sql/api_modules/business_overview_*.sql`
- `sql/api_modules/inventory_*.sql`
- `sql/api_modules/b_cost_analysis_*.sql`

Why risky:

- closer to pages, but still often reused by multiple routes or modules
- easy to introduce subtle contract drift

Preferred usage:

- additive, contract-preserving changes
- page-specific fields only after checking whether the data belongs in reference/read composition instead

## Avoid First / Treat As Last Resort

These are not forbidden, but should not be your first move for normal product work.

### 1. Raw Fact Tables

Examples:

- `b_class.fact_*`
- ingestion persistence shape
- collection export payload assumptions

Why:

- this is source-of-truth storage
- changing it to solve frontend or reporting issues is usually the wrong layer

### 2. Collection / Ops Interfaces For Production Business Pages

Examples:

- `shop-accounts`
- `shop-account-aliases`
- `platform-shop-discoveries`
- collection config / recorder routes

Why:

- business pages must not depend on ops/collection-only capabilities
- production-safe pages should consume `business/common/reference` style interfaces instead

## Recommended Change Order

For shop display, dashboard, settlement, and performance work, follow this order:

1. Verify the issue is not just frontend presentation.
2. Prefer frontend rendering and filter changes.
3. If shared display data is needed, add or use a production-safe reference endpoint.
4. If runtime status is unclear, improve diagnostics and readiness checks.
5. Only then investigate `api_modules`.
6. Only after evidence, touch `mart`.
7. Touch `semantic` last.

## Practical Rules

### Shop Display Changes

Default:

- use `shop-directory`
- derive `display_name`, `secondary_name`, `search_text`
- do not modify semantic shop identity logic just to show aliases

### Dashboard Readiness Problems

Default:

- inspect asset state
- inspect real object existence
- inspect bootstrap / refresh diagnostics
- do not start by changing frontend pages

### Slow Monthly / Atomic Refresh

Default:

- inspect source row counts
- inspect query plans
- inspect identity-resolution joins and indexes
- do not rewrite SQL until the hot path is proven

## Acceptance Checklist Before Touching High-Risk Layers

Before editing `semantic`, `mart`, or shared `api_modules`, answer yes to all:

- Is the issue reproduced outside the frontend?
- Is the failing or slow layer proven with query/output evidence?
- Have safer alternatives been ruled out?
- Is the affected downstream surface enumerated?
- Do targeted regression tests exist for the changed layer?

If any answer is no, stay in a safer layer.
