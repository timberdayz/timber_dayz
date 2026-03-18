# Change: Refactor DSS Query Convergence

## Why

The repository currently holds conflicting architectural truths:

- project docs describe `DSS/Metabase` as the preferred query architecture
- the active application still exposes materialized-view management as a normal API path
- parts of the codebase continue to mix route handlers, direct SQL, and legacy read paths

This change creates a single convergence direction so follow-up refactors stop drifting between incompatible models.

## What Changes

- Reclassify materialized-view APIs as legacy compatibility tooling, not the preferred dashboard/query path
- Clarify that dashboard and analytical read flows should prefer Metabase or explicitly controlled backend query services
- Document the convergence path in OpenSpec so later code changes can be implemented against a consistent contract
- Capture the first concrete implementation step: repair the legacy `/api/mv` router so it is operational while the rest of the convergence work proceeds
- Deprecate legacy Celery MV refresh tasks so they stop executing materialized-view refresh SQL during the convergence period

## Impact

- Affected specs: `dashboard`, `materialized-views`
- Affected code: `backend/routers/mv.py`, `backend/tasks/scheduled_tasks.py`, `backend/main.py`, future dashboard/query handlers
