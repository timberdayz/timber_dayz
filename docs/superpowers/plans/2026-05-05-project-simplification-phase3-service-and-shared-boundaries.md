# Project Simplification Phase 3 Service And Shared Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the backend-facing Phase 3 of project simplification by reducing non-test runtime dependencies on `backend.routers.*`, introducing domain-owned aggregation surfaces where missing, and narrowing cross-domain service/shared boundaries without changing business behavior.

**Architecture:** Phase 1 made runtime composition explicit, and Phase 2 moved route-registration ownership into domain modules. Phase 3 should now remove the remaining "legacy compatibility path as runtime dependency" cases from active backend code. The compatibility layer under `backend/routers/` stays in place for tests, external imports, and gradual migration, but production code should prefer domain-owned router/service entry points. This phase remains behavior-preserving and does not yet split frontend structure or decompose the ORM SSOT.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Python package-level compatibility shims under `backend/routers/`

---

## Scope

In scope:

- `backend/domains/**` router aggregation surfaces that still import `backend.routers.*`
- backend services that still call router internals directly
- compatibility-preserving extraction of router-internal task execution helpers into domain or service-owned call surfaces
- targeted backend regression tests and route/runtime verification
- plan/progress alignment for the active simplification thread

Out of scope:

- frontend domain reorganization
- internal decomposition of `modules/core/db/schema.py`
- deleting `backend/routers/*.py` compatibility shims
- changing route paths, tags, auth contracts, or runtime-mode behavior
- business overview read-model work (tracked in a separate session)

## Phase 3 Exit Criteria

- Active backend runtime code no longer depends on `backend.routers.*` except for deliberate compatibility hooks that are explicitly documented and tested.
- Domain aggregation routers compose domain-owned subrouters instead of legacy router modules where domain subrouters already exist.
- Router-internal execution helpers required by services are exposed through a service/domain-owned boundary instead of importing from legacy compatibility modules.
- `backend/main.py`, `backend/app/bootstrap/*`, and production-path domain routers remain behaviorally compatible under the existing regression suites.

## Residual Boundary Inventory

Current known runtime boundary leaks to eliminate in this phase:

- `backend/domains/collection/routers/collection.py`
  - imports `backend.routers.collection_config`
  - imports `backend.routers.collection_tasks`
  - imports `backend.routers.collection_schedule`
- `backend/domains/business/routers/hr_management.py`
  - imports `backend.routers.hr_department`
  - imports `backend.routers.hr_employee`
  - imports `backend.routers.hr_attendance`
  - imports `backend.routers.hr_salary`
  - imports `backend.routers.hr_commission`
- `backend/domains/data_platform/routers/field_mapping.py`
  - imports `backend.routers.field_mapping_files`
  - imports `backend.routers.field_mapping_ingest`
  - imports `backend.routers.field_mapping_status`
- `backend/services/collection_queue_runner.py`
  - imports `_execute_collection_task_background` from `backend.routers.collection_tasks`
- `backend/domains/platform/routers/auth.py`
  - imports `backend.routers.notifications.*` for notification side effects
- `backend/domains/platform/routers/notifications.py`
  - still uses `backend.routers.notifications.create_notification` for monkeypatch compatibility

The last two platform items are lower-risk compatibility cases. The first four are the primary Phase 3 execution targets.

### Task 1: Replace collection aggregation imports with domain-owned subrouters

**Files:**
- Modify: `backend/domains/collection/routers/collection.py`
- Verify references: `backend/domains/collection/routers/collection_config.py`
- Verify references: `backend/domains/collection/routers/collection_schedule.py`
- Verify references: `backend/domains/collection/routers/collection_tasks.py`
- Test: `backend/tests/test_task_center_collection_projection.py`
- Test: `tests/test_collection_resume_api.py`

- [ ] **Step 1: Update the aggregation imports**

Change `backend/domains/collection/routers/collection.py` to import subrouters from `backend.domains.collection.routers.*` instead of `backend.routers.*`.

- [ ] **Step 2: Preserve backward-compatible helper exposure**

If `_execute_collection_task_background` is still re-exported for compatibility, keep the `# noqa: F401` pattern in the domain aggregator but source it from the domain-owned `collection_tasks.py`.

- [ ] **Step 3: Run targeted collection tests**

Run:

```powershell
python -m pytest backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py -q
```

Expected: all tests pass with no route contract changes.

- [ ] **Step 4: Commit**

```powershell
git add backend/domains/collection/routers/collection.py backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py
git commit -m "refactor: use domain collection subrouters"
```

### Task 2: Replace HR aggregation imports with domain-owned subrouters

**Files:**
- Modify: `backend/domains/business/routers/hr_management.py`
- Create if needed: `backend/domains/business/routers/hr_department.py`
- Create if needed: `backend/domains/business/routers/hr_employee.py`
- Create if needed: `backend/domains/business/routers/hr_attendance.py`
- Create if needed: `backend/domains/business/routers/hr_salary.py`
- Create if needed: `backend/domains/business/routers/hr_commission.py`
- Test: locate the smallest HR route suite already present under `backend/tests/`

- [ ] **Step 1: Inventory whether domain wrappers already exist**

Run:

```powershell
rg --files backend/domains/business/routers | rg "hr_"
```

Expected: if wrappers are missing, create thin domain shims that import from legacy HR subrouters first; if wrappers already exist, skip creation.

- [ ] **Step 2: Change `hr_management.py` to use domain-local imports**

Replace `backend.routers.hr_*` imports with `backend.domains.business.routers.hr_*` imports.

- [ ] **Step 3: Run the smallest relevant HR route tests**

Select existing tests touching HR routes or employee income flows, for example:

```powershell
rg -n "hr_|income|salary|attendance|commission" backend/tests
```

Then run the smallest representative set with `python -m pytest ... -q`.

- [ ] **Step 4: Commit**

```powershell
git add backend/domains/business/routers/hr_management.py backend/domains/business/routers/hr_*.py
git commit -m "refactor: use domain hr subrouters"
```

### Task 3: Replace field-mapping aggregation imports with domain-owned subrouters

**Files:**
- Modify: `backend/domains/data_platform/routers/field_mapping.py`
- Create if needed: `backend/domains/data_platform/routers/field_mapping_files.py`
- Create if needed: `backend/domains/data_platform/routers/field_mapping_ingest.py`
- Create if needed: `backend/domains/data_platform/routers/field_mapping_status.py`
- Test: route or field-mapping related tests under `backend/tests/`

- [ ] **Step 1: Inventory whether domain wrappers already exist**

Run:

```powershell
rg --files backend/domains/data_platform/routers | rg "field_mapping_(files|ingest|status)"
```

Expected: determine whether thin domain wrappers need to be added before rewiring the aggregator.

- [ ] **Step 2: Repoint the aggregator**

Replace legacy router imports in `backend/domains/data_platform/routers/field_mapping.py` with domain-owned imports.

- [ ] **Step 3: Run targeted field-mapping/data-sync tests**

Use the smallest available set after discovery, for example:

```powershell
rg -n "field_mapping|data_sync|template" backend/tests
```

Then run the smallest representative subset with `python -m pytest ... -q`.

- [ ] **Step 4: Commit**

```powershell
git add backend/domains/data_platform/routers/field_mapping.py backend/domains/data_platform/routers/field_mapping_*.py
git commit -m "refactor: use domain field-mapping subrouters"
```

### Task 4: Extract collection task execution helper away from legacy router import

**Files:**
- Modify: `backend/services/collection_queue_runner.py`
- Modify: `backend/domains/collection/routers/collection_tasks.py` or a new service helper module
- Create if needed: `backend/services/collection_task_executor.py`
- Test: `backend/tests/test_task_center_collection_projection.py`
- Test: `tests/test_collection_resume_api.py`

- [ ] **Step 1: Choose a stable ownership point**

Preferred target: create a service-owned helper such as `backend/services/collection_task_executor.py` exposing a function used by both the domain router and queue runner.

- [ ] **Step 2: Move or wrap `_execute_collection_task_background`**

Do not change behavior. Either:

```text
Option A: move implementation into service helper and keep router shim
Option B: add service wrapper that delegates to the domain router helper
```

Prefer Option A if the code can move without breaking tests. Prefer Option B if tests directly patch router symbols and the move would create churn.

- [ ] **Step 3: Update queue runner to import from the new owner**

`backend/services/collection_queue_runner.py` should no longer import from `backend.routers.collection_tasks`.

- [ ] **Step 4: Re-run collection task projection tests**

Run:

```powershell
python -m pytest backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py -q
```

Expected: all tests pass and queue-runner execution path remains intact.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/collection_queue_runner.py backend/services/collection_task_executor.py backend/domains/collection/routers/collection_tasks.py
git commit -m "refactor: extract collection task executor boundary"
```

### Task 5: Normalize platform notification compatibility boundaries

**Files:**
- Modify: `backend/domains/platform/routers/auth.py`
- Modify: `backend/domains/platform/routers/notifications.py`
- Create if needed: `backend/domains/platform/compat/notifications.py`
- Test: `backend/tests/test_user_registration_api.py`
- Test: `backend/tests/test_users_admin_routes.py`

- [ ] **Step 1: Centralize the compatibility hook**

Move the explicit `backend.routers.notifications` compatibility import logic into one helper surface, preferably a small compat module under `backend/domains/platform/compat/`.

- [ ] **Step 2: Update `auth.py` and `notifications.py` to use the compat helper**

Goal: keep monkeypatch compatibility while making the boundary explicit and documented.

- [ ] **Step 3: Run targeted platform notification/auth tests**

Run:

```powershell
python -m pytest backend/tests/test_user_registration_api.py backend/tests/test_users_admin_routes.py -q
```

Expected: all tests pass and monkeypatch-based tests still target the legacy compatibility path successfully.

- [ ] **Step 4: Commit**

```powershell
git add backend/domains/platform/routers/auth.py backend/domains/platform/routers/notifications.py backend/domains/platform/compat/notifications.py
git commit -m "refactor: centralize platform notification compatibility"
```

### Task 6: Full Phase 3 verification and document updates

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`
- Modify if needed: `docs/superpowers/plans/2026-05-05-project-simplification-phase3-service-and-shared-boundaries.md`

- [ ] **Step 1: Run route/runtime verification**

Run:

```powershell
python -m pytest backend/tests/test_domain_route_registration.py backend/tests/test_runtime_mode_route_registration.py -q
```

Expected: pass.

- [ ] **Step 2: Run expanded regression subset**

Run:

```powershell
python -m pytest backend/tests/data_pipeline/test_dashboard_router_switch.py backend/tests/data_pipeline/test_dashboard_rollout_docs.py backend/tests/data_pipeline/test_postgresql_dashboard_immediate_cleanup.py backend/tests/data_pipeline/test_postgresql_dashboard_entrypoints.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py backend/tests/test_employee_task_notifications.py backend/tests/test_user_registration_api.py backend/tests/test_users_admin_routes.py -q
```

Expected: pass with no route/runtime regressions.

- [ ] **Step 3: Update execution logs**

Record:

- completed boundary migrations
- any compatibility hooks intentionally retained
- exact verification commands and results

- [ ] **Step 4: Commit**

```powershell
git add task_plan.md findings.md progress.md
git commit -m "chore: record phase 3 simplification progress"
```

## Risks And Controls

### Risk: Aggregation rewiring breaks direct test monkeypatch assumptions
- Control: keep legacy `backend/routers/*.py` shims intact and move compatibility into explicit helper surfaces where needed.

### Risk: Queue-runner extraction accidentally changes collection task execution semantics
- Control: preserve function signature and re-run the collection task projection/resume suites immediately after the extraction step.

### Risk: Phase 3 drifts into schema decomposition too early
- Control: keep `modules/core/db/schema.py` out of scope; only record schema-boundary observations for the later Phase 5 plan.

## Next Slice

After Phase 3 is complete and stable:

- write and execute Phase 4 frontend-domain reorganization plan
- then write and execute Phase 5 schema-SSOT decomposition plan
