# DSS Convergence Status

> 历史说明：本文中的 DSS/Metabase 口径仅用于记录收敛过程。
> 当前活跃架构应表述为 PostgreSQL `semantic / mart / api` 主路径。

## Current Rule

- PostgreSQL `semantic / mart / api` is the preferred dashboard and analytics query architecture.
- `DSS/Metabase` is historical-only and must not be treated as an active runtime dependency.
- `/api/mv/*` remains available only as legacy compatibility tooling.
- legacy Celery materialized-view refresh tasks are deprecated and now return `skipped` instead of executing refresh SQL.

## What This Means

- New dashboard and analytics work must not introduce fresh primary dependencies on Metabase.
- Existing materialized-view compatibility usage is transitional and should be replaced by PostgreSQL-owned backend query services where equivalent semantic/mart/api assets exist.
- If a compatibility endpoint or task must remain temporarily, it should be marked deprecated and documented as legacy-only.

## Current Compatibility Surfaces

- `backend/domains/business/routers/mv.py`
- `backend/tasks/scheduled_tasks.py`

## Next Cleanup Targets

- `backend/routers/management.py`
- `backend/routers/data_flow.py`
- `backend/routers/auto_ingest.py` (governance-only surface retained; legacy runtime routes retired)
- `backend/services/c_class_data_service.py`
- `backend/routers/inventory_management.py`
