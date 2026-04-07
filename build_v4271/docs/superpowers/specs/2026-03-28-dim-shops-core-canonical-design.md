# Dim Shops Core Canonical Design

## Goal

Make `core.dim_shops` the single canonical runtime table and eliminate the current ambiguity where production data lives in `core` but ORM/runtime still resolves `DimShop` through `public`.

## Current Problem

The current system is internally inconsistent:

- ORM model `DimShop` is defined without schema, so it resolves to the default schema
- backend runtime search path is `public,b_class,a_class,c_class,core,finance`
- production data exists only in `core.dim_shops`
- `public.dim_shops` exists but is empty

This means unqualified runtime access is structurally biased toward the empty `public` table.

## Design Decision

`core.dim_shops` becomes the only canonical runtime table.

This implies:

- the `DimShop` ORM model must explicitly bind to `core`
- read and write paths that use `DimShop` must continue to work through the ORM after the schema binding change
- `public.dim_shops` cleanup is deferred until after runtime alignment is proven

## Non-Goals

- do not archive or drop `public.dim_shops` in the same phase
- do not fold `entity_aliases` or `staging_raw_data` into this work
- do not redesign broader schema search-path policy in the same phase

## Options

### Option A: Recommended

Bind `DimShop` explicitly to `core`, keep current write paths, and verify the main ORM-backed read/write paths continue to work.

### Option B: Backfill `public` and leave ORM unchanged

Not recommended because it preserves dual truth and postpones the real fix.

### Option C: Compatibility bridge first

Not recommended because a bridge/view layer is more complex than needed before trying an explicit-schema fix.

## Phase Structure

### Phase A: Runtime alignment

Scope:

- bind `DimShop` ORM to `core`
- add targeted tests for active read/write paths
- verify the backend runtime no longer depends on `public.dim_shops`

### Phase B: Public copy retirement

Scope:

- assess whether `public.dim_shops` can be archived or dropped
- only after Phase A proves no active path still depends on it

This phase is explicitly deferred.

## Affected Runtime Paths

### Write paths

- `backend/services/shop_sync_service.py`
- `backend/routers/account_management.py`
- `backend/routers/target_management.py`

### Read paths

- `backend/routers/hr_commission.py`
- `backend/routers/performance_management.py`
- `backend/routers/sales_campaign.py`
- `backend/routers/target_management.py`
- `backend/services/clearance_ranking_service.py`
- `backend/services/c_class_data_service.py`

### SQL to review

- `sql/metabase_questions/business_overview_operational_metrics.sql`

## Testing Strategy

1. Model ownership tests
2. Write-path tests
3. Read-path regression tests
4. Search-path independence checks
5. Existing schema-cleanup regression suite

## Success Criteria

- `DimShop` is explicitly bound to `core`
- active read/write paths that use `DimShop` still pass
- `public.dim_shops` cleanup remains deferred to a later dedicated phase
