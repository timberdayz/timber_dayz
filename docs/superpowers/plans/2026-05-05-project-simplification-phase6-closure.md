# Project Simplification Phase 6 Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the post-Phase-5 simplification cleanup by shrinking the remaining legacy compatibility surface across backend domains, frontend view bridges, and the schema SSOT aggregator without changing runtime behavior.

**Architecture:** Phase 1-5 already established the new runtime/bootstrap model, domain registration ownership, frontend domain folders, and the first `schema_parts` split. Phase 6 is a closure phase: convert the remaining compatibility layers from "active runtime path" to "thin transitional shim", keep public import and route contracts stable, and add guard tests so future work cannot silently re-expand the legacy surfaces.

**Tech Stack:** FastAPI, SQLAlchemy ORM, pytest, Vue 3, Vue Router, Vite, vue-tsc, Node.js

---

## Scope

In scope:
- remaining runtime imports from `backend.routers.*` inside `backend/domains/**` and `backend/services/**`
- remaining Vue view bridge wrappers under `frontend/src/views/**`
- continued internal decomposition of `modules/core/db/schema.py` into `modules/core/db/schema_parts/**`
- guard tests and lightweight inventory artifacts for the closure state

Out of scope:
- changing public API routes, auth contracts, or runtime-mode behavior
- redesigning frontend pages
- changing ORM table names, columns, constraints, or migrations
- deleting all legacy shims in one pass

## Phase 6 Exit Criteria

- active backend runtime code only retains explicitly documented legacy compat hooks
- frontend route components resolve directly to domain-owned files for the main route table, or all remaining wrappers are intentionally documented
- `modules/core/db/schema.py` is primarily a re-export surface with most model families owned by `schema_parts/*`
- regression suites and new guard tests pass on `main`

## Current Residual Surfaces

### Backend compat/runtime surfaces

Known remaining `backend.routers.*` dependencies:
- `backend/domains/platform/routers/users.py`
- `backend/domains/platform/routers/notifications.py`
- `backend/domains/platform/compat/notifications.py`
- `backend/domains/collection/routers/{shop_account_aliases.py,main_accounts.py,component_versions.py,component_recorder.py,collection_tasks.py}`
- `backend/domains/data_platform/routers/{field_mapping_status.py,field_mapping_ingest.py,field_mapping_files.py}`
- `backend/domains/business/routers/{dashboard_api_postgresql.py,follow_investment.py,hr_attendance.py,hr_department.py,hr_commission.py,hr_employee.py,profit_basis.py,performance_management.py,mv.py,monthly_profit_settlement.py,hr_salary.py}`

### Frontend bridge surface

Current compatibility wrappers under `frontend/src/views/**` still importing `@/domains/...`:
- about 100+ files, spanning `platform`, `business`, `data_platform`, and `collection`
- route table remains pointed at wrapper files in `frontend/src/router/index.js`

### Schema SSOT surface

Already split:
- `modules/core/db/schema_parts/base.py`
- `modules/core/db/schema_parts/dimensions.py`
- `modules/core/db/schema_parts/facts.py`

Still largely aggregated inside `modules/core/db/schema.py`:
- collection/task-center/approval/training models
- platform account and shop identity models
- data-platform ingestion / field-mapping models
- business finance / inventory / procurement / accounting models

---

### Task 1: Add closure guard inventories and tests

**Files:**
- Create: `backend/tests/test_domain_legacy_router_boundary.py`
- Create: `frontend/scripts/domainBridgeInventory.test.mjs`
- Create: `docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md`
- Read: `backend/domains/**`
- Read: `backend/services/**`
- Read: `frontend/src/router/index.js`
- Read: `frontend/src/views/**`

- [x] **Step 1: Write a failing backend guard test for legacy runtime imports**

Create `backend/tests/test_domain_legacy_router_boundary.py` to scan:
- `backend/domains/**/*.py`
- `backend/services/**/*.py`

The test should:
- fail if new `backend.routers.*` imports appear outside an explicit allowlist
- encode the current intentional exceptions in one place

- [x] **Step 2: Run the backend guard test to verify it fails for the current residual set**

Run:
```powershell
python -m pytest backend/tests/test_domain_legacy_router_boundary.py -q
```
Expected: FAIL, showing the current allowlist candidates.

- [x] **Step 3: Add a frontend bridge inventory test**

Create `frontend/scripts/domainBridgeInventory.test.mjs` that:
- parses `frontend/src/router/index.js`
- resolves route component imports under `frontend/src/views/**`
- counts wrappers that only delegate to `@/domains/**`

The test should print or assert against an expected baseline count stored in the test file.

- [x] **Step 4: Run the frontend inventory test**

Run:
```powershell
cd frontend
node --test scripts/domainBridgeInventory.test.mjs
```
Expected: PASS with a baseline count for tracked wrappers.

- [x] **Step 5: Record the residual inventory**

Create `docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md` documenting:
- allowed backend compat hooks
- current wrapper count
- intended schema slice order

- [ ] **Step 6: Commit**

```powershell
git add backend/tests/test_domain_legacy_router_boundary.py frontend/scripts/domainBridgeInventory.test.mjs docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md
git commit -m "test: add phase6 closure guard inventories"
```

### Task 2: Reduce backend legacy router dependencies to explicit compat surfaces

**Files:**
- Modify: `backend/domains/platform/routers/users.py`
- Modify: `backend/domains/platform/routers/notifications.py`
- Modify: `backend/domains/platform/compat/notifications.py`
- Modify: `backend/domains/collection/routers/{shop_account_aliases.py,main_accounts.py,component_versions.py,component_recorder.py,collection_tasks.py}`
- Modify: `backend/domains/data_platform/routers/{field_mapping_status.py,field_mapping_ingest.py,field_mapping_files.py}`
- Modify: `backend/domains/business/routers/{dashboard_api_postgresql.py,follow_investment.py,hr_attendance.py,hr_department.py,hr_commission.py,hr_employee.py,profit_basis.py,performance_management.py,mv.py,monthly_profit_settlement.py,hr_salary.py}`
- Test: `backend/tests/test_domain_legacy_router_boundary.py`
- Test: `backend/tests/test_domain_route_registration.py`
- Test: `backend/tests/test_runtime_mode_route_registration.py`

- [x] **Step 1: Convert trivial `from backend.routers... import *` wrappers into explicit domain-owned shims**

For each thin wrapper file:
- replace star import with explicit router/helper imports
- keep backward-compatible exports only where truly needed
- document any file that must remain a pure compat shim

- [x] **Step 2: Normalize platform users and notifications onto compat helper boundaries**

Goal:
- `backend/domains/platform/routers/users.py` should prefer domain-local or compat-local imports
- all notification-related legacy monkeypatch support stays behind `backend/domains/platform/compat/notifications.py`

- [x] **Step 3: Update the backend guard test allowlist to the new expected residual set**

The test should now pass only for intentionally retained compat hooks.

- [x] **Step 4: Run targeted route/runtime tests**

Run:
```powershell
python -m pytest backend/tests/test_domain_legacy_router_boundary.py backend/tests/test_domain_route_registration.py backend/tests/test_runtime_mode_route_registration.py -q
```
Expected: PASS.

- [x] **Step 5: Run the expanded backend regression subset**

Run:
```powershell
python -m pytest backend/tests/data_pipeline/test_dashboard_router_switch.py backend/tests/data_pipeline/test_dashboard_rollout_docs.py backend/tests/data_pipeline/test_postgresql_dashboard_immediate_cleanup.py backend/tests/data_pipeline/test_postgresql_dashboard_entrypoints.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py backend/tests/test_employee_task_notifications.py backend/tests/test_user_registration_api.py backend/tests/test_users_admin_routes.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/domains backend/tests/test_domain_legacy_router_boundary.py
git commit -m "refactor: narrow backend legacy router compat surfaces"
```

### Task 3: Repoint frontend routes to domain-owned views and shrink wrappers

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/scripts/domainBridgeInventory.test.mjs`
- Modify/Delete: selected wrappers under `frontend/src/views/**`
- Verify domain owners under:
  - `frontend/src/domains/platform/views/**`
  - `frontend/src/domains/business/views/**`
  - `frontend/src/domains/data_platform/views/**`
  - `frontend/src/domains/collection/views/**`
- Test: `frontend/scripts/frontendSmokeShared.test.mjs`

- [x] **Step 1: Write or extend a failing test for direct route-to-domain ownership**

Update `frontend/scripts/domainBridgeInventory.test.mjs` so it can assert a first-wave target:
- route imports for one domain batch no longer point to wrapper files
- wrapper baseline decreases after the migration

- [x] **Step 2: Migrate `platform` route imports in `frontend/src/router/index.js`**

Change route `component: () => import('../views/...')` entries to direct `@/domains/platform/views/...` imports for:
- login/register
- users/roles/permissions
- settings/system/messages
- approval/training/help

Keep route names and paths unchanged.

- [x] **Step 3: Run type-check and build**

Run:
```powershell
cd frontend
npm run type-check
npm run build
node --test scripts/domainBridgeInventory.test.mjs
npm run test:smoke-shared
```
Expected: PASS.

- [x] **Step 4: Repeat for `data_platform`, `collection`, and `business` in small batches**

Suggested order:
1. `data_platform`
2. `collection`
3. `business`

After each batch:
- reduce wrapper count
- verify build and smoke

- [x] **Step 5: Remove wrappers that are no longer referenced by the router or other imports**

Task 3 closure note:
- Frontend script tests that previously hardcoded `src/views/**` collection / training / business / platform wrapper paths were repointed to canonical `src/domains/**/views/**` files, allowing the final 30 route-bridge wrappers to be deleted.

Delete only wrappers proven unused by:
```powershell
rg -n "@/views/|../views/" frontend/src
```

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/router/index.js frontend/src/views frontend/scripts/domainBridgeInventory.test.mjs
git commit -m "refactor(frontend): repoint routes to domain-owned views"
```

### Task 4: Continue schema SSOT decomposition by domain slices

**Files:**
- Modify: `modules/core/db/schema.py`
- Create/Modify:
  - `modules/core/db/schema_parts/collection.py`
  - `modules/core/db/schema_parts/platform.py`
  - `modules/core/db/schema_parts/data_platform.py`
  - `modules/core/db/schema_parts/business.py`
- Modify: `backend/tests/test_schema_ssot_import_contract.py`

- [x] **Step 1: Add a failing identity/import test for the next schema slice**

Extend `backend/tests/test_schema_ssot_import_contract.py` to assert public symbol identity for the first next slice, starting with collection/task-center/approval/training models:
- `CollectionConfig`
- `CollectionTask`
- `TaskCenterTask`
- `EmployeeTask`
- `ApprovalInstance`
- `TrainingProgram`

- [x] **Step 2: Run the schema contract test and verify the new assertions fail**

Run:
```powershell
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: FAIL until the slice is re-exported from `schema_parts`.

- [x] **Step 3: Move collection/task-center/approval/training models into `schema_parts/collection.py`**

Requirements:
- no table or column changes
- preserve `Base` identity
- preserve relationship semantics
- keep `modules.core.db.schema` public symbols unchanged

- [x] **Step 4: Re-run compile and schema contract tests**

Run:
```powershell
python -m py_compile modules/core/db/schema.py modules/core/db/schema_parts/collection.py
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS.

- [x] **Step 5: Repeat by slice for `platform`, `data_platform`, and `business`**

Suggested order:
1. `platform.py`
2. `data_platform.py`
3. `business.py`

After each slice:
- extend identity assertions
- run `py_compile`
- run schema contract tests

- [ ] **Step 6: Commit**

Task 4 status note:
- Completed the required `collection`, `platform`, `data_platform`, and `business` slices.
- `backend/tests/test_schema_ssot_import_contract.py` now covers representative public symbol identity for all four new slice modules.

```powershell
git add modules/core/db/schema.py modules/core/db/schema_parts backend/tests/test_schema_ssot_import_contract.py
git commit -m "refactor(schema): continue phase6 schema slice decomposition"
```

### Task 5: Final Phase 6 verification and closure notes

**Files:**
- Modify: `docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run the backend verification set**

Run:
```powershell
python -m pytest backend/tests/test_domain_legacy_router_boundary.py backend/tests/test_domain_route_registration.py backend/tests/test_runtime_mode_route_registration.py backend/tests/test_schema_ssot_import_contract.py -q
python -m pytest backend/tests/data_pipeline/test_dashboard_router_switch.py backend/tests/data_pipeline/test_dashboard_rollout_docs.py backend/tests/data_pipeline/test_postgresql_dashboard_immediate_cleanup.py backend/tests/data_pipeline/test_postgresql_dashboard_entrypoints.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py backend/tests/test_employee_task_notifications.py backend/tests/test_user_registration_api.py backend/tests/test_users_admin_routes.py -q
```
Expected: PASS.

- [ ] **Step 2: Run the frontend verification set**

Run:
```powershell
cd frontend
npm run type-check
npm run build
node --test scripts/domainBridgeInventory.test.mjs
npm run test:smoke-shared
```
Expected: PASS.

- [ ] **Step 3: Update closure notes**

Document:
- remaining intentional compat hooks
- remaining wrapper count, if any
- remaining model classes still in `schema.py`, if any

- [ ] **Step 4: Commit**

```powershell
git add docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md task_plan.md progress.md findings.md
git commit -m "docs: record phase6 closure status"
```

---

## Risks and Controls

- Risk: direct route repointing breaks lazy-loaded Vue chunks
  - Control: migrate one domain batch at a time and run `type-check`, `build`, and smoke after each batch

- Risk: schema slice extraction introduces import cycles
  - Control: move in domain batches, keep string relationships, and extend symbol-identity tests before each slice

- Risk: backend compat cleanup breaks monkeypatch-based tests or external imports
  - Control: keep compat modules explicit; remove star imports gradually rather than deleting shims wholesale

## Notes

- If Task 3 or Task 4 expands beyond a single focused session, split them into dedicated sub-plans rather than broadening this document further.
- The separate `business overview read model unification` track is already out of scope for this plan and should stay independent.

