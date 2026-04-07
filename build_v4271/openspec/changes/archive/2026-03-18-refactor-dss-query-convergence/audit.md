# DSS vs MV Conflict Audit

## Completed In This Change

- `backend/routers/mv.py`
  - fixed `AsyncSession` misuse
  - marked legacy endpoints deprecated
  - retained compatibility behavior without presenting the router as a preferred path
- `backend/tasks/scheduled_tasks.py`
  - deprecated legacy MV refresh tasks
  - changed the tasks to explicit `skipped` compatibility no-ops
- `docs/architecture/DSS_CONVERGENCE_STATUS.md`
  - documented the current preferred architecture and legacy compatibility surfaces

## Remaining High-Priority Conflicts

- `backend/routers/management.py`
  - returns placeholder sales data (`qty=0`, `gmv=0`)
  - still queries `mv_sales_detail_by_product`
  - still builds route-level SQL directly
- `backend/routers/data_flow.py`
  - still uses `SELECT 0` placeholders for order fact counts
  - migration from deleted order models to `b_class` query path is incomplete
- `backend/routers/auto_ingest.py`
  - still refreshes materialized views directly after cleanup flows
- `backend/services/c_class_data_service.py`
  - still contains explicit materialized-view decision paths and MV-backed ranking/health queries
- `backend/routers/inventory_management.py`
  - still labels MV as the active data source in response payloads

## Secondary Conflict Areas

- `backend/services/event_listeners.py`
  - still carries MV-oriented event handling and dependency lists
- `backend/services/database_design_validator.py`
  - still treats materialized views as a first-class validation concern
- repository docs outside this change
  - root `README.md`
  - `docs/README.md`
  - older API/testing guides that still describe MV as a normal or preferred path

## Recommended Next Change Set

1. Refactor `backend/routers/management.py` to remove placeholder returns and route-level MV SQL.
2. Refactor `backend/routers/data_flow.py` to replace deleted-order placeholders with real `b_class` queries.
3. Remove direct MV refresh from `backend/routers/auto_ingest.py`.
4. Split `backend/services/c_class_data_service.py` into DSS-first query paths and isolate any short-term compatibility branches.
