# DSS Convergence Status

## Current Rule

- `DSS/Metabase` is the preferred dashboard and analytics query architecture.
- `/api/mv/*` remains available only as legacy compatibility tooling.
- legacy Celery materialized-view refresh tasks are deprecated and now return `skipped` instead of executing refresh SQL.

## What This Means

- New dashboard and analytics work must not introduce fresh primary dependencies on materialized views.
- Existing materialized-view usage is transitional and should be replaced by Metabase questions or explicitly owned backend query services.
- If a compatibility endpoint or task must remain temporarily, it should be marked deprecated and documented as legacy-only.

## Current Compatibility Surfaces

- `backend/routers/mv.py`
- `backend/tasks/scheduled_tasks.py`

## Next Cleanup Targets

- `backend/routers/management.py`
- `backend/routers/data_flow.py`
- `backend/routers/auto_ingest.py`
- `backend/services/c_class_data_service.py`
- `backend/routers/inventory_management.py`
