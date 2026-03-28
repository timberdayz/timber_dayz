# Dim Shops Runtime Alignment Investigation

**Date:** 2026-03-28
**Scope:** `DimShop` ORM ownership, backend runtime search path, and production physical table state

## Core finding

`dim_shops` is not a normal duplicate-cleanup candidate.

It is currently a runtime/schema alignment defect with three layers of contradiction:

1. ORM model ownership still resolves to `public`
2. backend runtime search path puts `public` ahead of `core`
3. production live rows exist only in `core.dim_shops`

That combination means unqualified runtime access to `dim_shops` is structurally biased toward the empty `public` table, not the populated `core` table.

## Evidence

### 1. ORM model

- `modules/core/db/schema.py`
  - `DimShop.__tablename__ = "dim_shops"`
  - no schema is declared
- Result:
  - ORM full name = `dim_shops`
  - effective schema = `public`

### 2. Backend runtime search path

- `backend/models/database.py`
  - PostgreSQL sync engine sets:
    - `search_path=public,b_class,a_class,c_class,core,finance`
- Production backend container probe confirmed:
  - `SHOW search_path` -> `public,b_class,a_class,c_class,core,finance`
  - `current_schema()` -> `public`
  - `SELECT count(*) FROM dim_shops` -> `0`
  - `SELECT count(*) FROM public.dim_shops` -> `0`
  - `SELECT count(*) FROM core.dim_shops` -> `29`

### 3. Production physical table state

- `public.dim_shops` exists but is empty
- `core.dim_shops` exists and contains live rows
- latest observed `core.updated_at`:
  - `2026-01-27 13:51:47.359293+00`

### 4. Runtime usage breadth

Audited active code shows `DimShop` participates in both reads and writes:

- read paths:
  - `backend/routers/hr_commission.py`
  - `backend/routers/performance_management.py`
  - `backend/routers/sales_campaign.py`
  - `backend/routers/target_management.py`
  - `backend/services/clearance_ranking_service.py`
  - `backend/services/c_class_data_service.py`
  - `sql/metabase_questions/business_overview_operational_metrics.sql`
- write paths:
  - `backend/services/shop_sync_service.py`
  - `backend/routers/account_management.py`
  - `backend/routers/target_management.py`

## Why this matters

If the application relies on unqualified `DimShop` ORM access, then current runtime semantics point to the empty `public.dim_shops` table first.

That means the cleanup problem is secondary. The first-order problem is:

- why is production live data in `core.dim_shops`
- while current ORM/runtime path still points to `public.dim_shops`

## Recommended next step

Do not draft a `dim_shops` cleanup migration yet.

Instead, run a dedicated alignment task:

1. identify whether current business flows that query `DimShop` are degraded, bypassed, or backfilled through other sources
2. decide the canonical ownership target:
   - move ORM to `core`
   - or repopulate `public`
3. only after runtime ownership is corrected, revisit duplicate cleanup

## Conclusion

`dim_shops` should be removed from generic wave-2 duplicate cleanup handling and tracked as a dedicated runtime/schema-alignment investigation.
