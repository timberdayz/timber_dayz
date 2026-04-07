# Dim Shops Runtime Alignment Investigation

**Date:** 2026-03-28
**Scope:** `DimShop` ORM ownership, backend runtime search path, and production physical table state

## Core finding

`dim_shops` is not a normal duplicate-cleanup candidate.

It is currently a runtime/schema alignment defect with three layers of contradiction:

1. ORM model ownership originally resolved to `public`
2. backend runtime search path puts `public` ahead of `core`
3. production live rows exist only in `core.dim_shops`

That combination means unqualified runtime access to `dim_shops` is structurally biased toward the empty `public` table, not the populated `core` table.

## Evidence

### 1. ORM model

- `modules/core/db/schema.py`
  - `DimShop.__tablename__ = "dim_shops"`
  - no schema is declared
- Original result:
  - ORM full name = `dim_shops`
  - effective schema = `public`

- Phase A result:
  - ORM full name = `core.dim_shops`
  - effective schema = `core`

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

## Phase A outcome

Phase A runtime alignment is now landed locally:

- `DimShop` ORM is explicitly bound to `core`
- schema-level foreign key references that pointed at unqualified `dim_shops` were updated to `core.dim_shops`
- a dedicated Alembic migration now ensures `core.dim_shops` exists in upgraded environments without forcing `public.dim_shops` retirement in the same step
- focused read/write tests for target management, performance, and employee-shop assignment paths pass against the canonical `core.dim_shops`

## Phase B readiness

The active unqualified `dim_shops` references that still blocked direct archive were reduced in the runtime-facing paths:

- `modules/services/data_validator.py`
- `modules/services/mapping_engine.py`
- `modules/apps/data_management_center/app.py`
- `sql/metabase_questions/business_overview_operational_metrics.sql`

All four now target `core.dim_shops`.

Phase B retirement artifacts now exist locally:

- archive migration for `public.dim_shops`
- temporary PostgreSQL rehearsal proving:
  - `public.dim_shops` exists before upgrade
  - `public.dim_shops` is renamed away after upgrade
  - `public.dim_shops__archive_retired` exists after upgrade
  - `core.dim_shops` remains present
  - schema completeness still passes

## Recommended next step

Do not draft a `dim_shops` cleanup migration yet.

Instead, run a dedicated alignment task:

1. keep `core.dim_shops` as the only runtime canonical table
2. review the local archive migration against production rollout timing
3. if approved, apply the `public.dim_shops` archive migration in a controlled environment

## Conclusion

`dim_shops` has now been removed from generic wave-2 duplicate cleanup handling and moved into a dedicated runtime/schema-alignment track, with local Phase A and Phase B archive work both implemented and rehearsed.
