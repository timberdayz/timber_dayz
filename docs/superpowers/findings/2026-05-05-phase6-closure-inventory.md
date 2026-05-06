# Phase 6 Closure Inventory (Task 1)

## Authority and scope

This note is a summary only.

- The authoritative backend residual baseline lives in `backend/tests/test_domain_legacy_router_boundary.py`.
- The authoritative frontend wrapper baseline lives in `frontend/scripts/domainBridgeInventory.test.mjs`.
- If either residual surface changes intentionally, update the corresponding test first, then refresh the summary numbers here.

## Backend compat summary

Current allowlisted residual files in the backend guard test:

- Platform: 2 files
- Collection: 5 files
- Data platform: 3 files
- Business: 11 files
- Total files with allowlisted `backend.routers` runtime imports: 21

Guard detail now preserved in the test baseline:

- `import ... as alias` remains distinct from the same import with another alias.
- `from backend.routers import name as alias` remains distinct from the non-aliased form.

Notable exceptions still intentionally retained:

- `backend/domains/platform/compat/notifications.py` keeps legacy notification hooks for compat callers and monkeypatch-based tests.
- `backend/domains/platform/routers/users.py` still bridges `users_admin` and `users_me`, but now labels them as explicit legacy subrouters instead of treating them as implicit wildcard surface.
- `backend/domains/collection/routers/collection_tasks.py` retains `router` plus `_execute_collection_task_background` as the only explicit legacy re-export.

Task 2 backend residual refinement:

- All allowlisted business / collection / data-platform wrapper files now use explicit `router` shims instead of `from backend.routers... import *`.
- No allowlisted backend residual file outside `backend/domains/platform/compat/notifications.py` keeps notification monkeypatch compatibility logic.

## Frontend wrapper summary

Current router-to-wrapper inventory baseline recorded in the frontend test:

- Route-level wrapper references: 0
- Direct route-to-domain imports: 107
- Direct domain ownership counts:
  - `platform`: 39
  - `data_platform`: 9
  - `collection`: 6
  - `business`: 53
- Wrapper baseline reduced from `107` route references / `105` unique files to `0` route references / `0` unique route wrappers.

Wrapper cleanup status after Task 3:

- Deleted 75 unreferenced domain wrappers under `frontend/src/views/**`.
- Continued cleanup removed the last 30 test-only wrappers after migrating script tests to canonical domain paths.
- Remaining route wrapper files: 0.
- `frontend/src/views/**` now only keeps non-wrapper legacy view files that are outside the Phase 6 Task 3 route-bridge scope.

## Schema residual summary

Task 4 schema decomposition is now landed in the Phase 6 worktree:

- Added `modules/core/db/schema_parts/collection.py`
- Added `modules/core/db/schema_parts/platform.py`
- Added `modules/core/db/schema_parts/data_platform.py`
- Added `modules/core/db/schema_parts/business.py`
- `modules/core/db/schema.py` is now a re-export/import-contract surface and no longer owns in-file ORM class definitions.
- Public import compatibility preserved for representative symbols across `dimensions`, `facts`, `collection`, `platform`, `data_platform`, and `business`, including package-level re-export usage through `modules.core.db`.
