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

- Route-level wrapper references: 107
- Unique wrapper files: 105
- Duplicate-aware baseline also records each wrapper route occurrence in router order, including repeated specifiers.

Notable repeated route specifiers still present in the router baseline:

- `../views/SalesDashboard.vue` appears twice
- `../views/sales/OrderManagement.vue` appears twice

## Schema next split order

Recommended next decomposition order for `modules/core/db/schema.py` remains:

1. `collection`
2. `platform`
3. `data_platform`
4. `business`

Reasoning: move the smaller, already-bounded operational slices first and leave the broadest business aggregate surface for last.
