# Collection Config Shop Scope And Scheduler Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild collection config management around single-platform shop-scope records and make scheduler changes take effect immediately without restarting the collection backend.

**Architecture:** Keep `CollectionConfig` as the config-header model for shared fields, introduce one shop-scope child model as the execution truth, and move both manual execution and scheduled execution onto one shared config-expansion service. Treat database schedule fields as the only source of truth and make every create/update/delete operation synchronize APScheduler state in the same backend flow.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, existing migration stack under `migrations/`, Vue 3, Element Plus, APScheduler, existing collection task runtime

---

## File Structure

### Existing files to modify

- `modules/core/db/schema.py`
  Responsibility: add the shop-scope ORM model and config-header relationships.
- `modules/core/db/__init__.py`
  Responsibility: export the new ORM model.
- `backend/schemas/collection.py`
  Responsibility: replace global account/domain config contracts with config-header plus `shop_scopes` contracts.
- `backend/routers/collection_config.py`
  Responsibility: update config CRUD, add save-time validation, and expose the new config-detail payload.
- `backend/routers/collection_schedule.py`
  Responsibility: keep explicit schedule endpoints aligned with the new save-time scheduler synchronization flow.
- `backend/routers/collection_tasks.py`
  Responsibility: stop relying on frontend per-shop loops and reuse the backend config execution service for config runs.
- `backend/services/collection_contracts.py`
  Responsibility: centralize shop-scope validation, capability filtering, and domain/sub-domain normalization helpers.
- `backend/services/collection_scheduler.py`
  Responsibility: sync jobs immediately after config changes and enforce runtime prechecks before scheduled execution.
- `backend/main.py`
  Responsibility: startup scheduler load remains the recovery path and should still load all enabled configs under the new model.
- `frontend/src/api/collection.js`
  Responsibility: switch config payloads to `shop_scopes` and add a backend-driven config-run entry point if implemented.
- `frontend/src/constants/collection.js`
  Responsibility: reuse domain labels/helpers and add shop-scope-specific helpers if the page needs them.
- `frontend/src/views/collection/CollectionConfig.vue`
  Responsibility: move from global domain selection to per-shop domain selection while keeping config-header controls on the same screen.
- `backend/tests/test_collection_config_api.py`
  Responsibility: cover config CRUD behavior under the new contract.
- `backend/tests/test_collection_scheduler_capability_filter.py`
  Responsibility: verify scheduled execution still respects capability filtering after moving to shop scopes.
- `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: lock the frontend-facing contract changes.

### New files to create

- `migrations/versions/20260406_collection_config_shop_scopes.py`
  Responsibility: add the new shop-scope table and any supporting indexes/constraints.
- `backend/services/collection_config_execution.py`
  Responsibility: expand one config into per-shop runnable tasks for both manual and scheduled execution.
- `backend/tests/test_collection_config_shop_scope_api.py`
  Responsibility: verify create/update/read validation for the new config-header plus shop-scope payload.
- `backend/tests/test_collection_config_schedule_sync_api.py`
  Responsibility: verify save-time scheduler registration, reschedule, disable, and delete behavior.
- `backend/tests/test_collection_config_execution_service.py`
  Responsibility: verify one config expands into per-shop tasks and preserves shop-specific domains.
- `frontend/scripts/collectionConfigShopScopeUi.test.mjs`
  Responsibility: verify the config page structure and payload usage match the shop-scope design.

---

### Task 1: Add Shop-Scope Persistence And Migration

**Files:**
- Create: `migrations/versions/20260406_collection_config_shop_scopes.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Test: `backend/tests/test_collection_config_shop_scope_api.py`

- [ ] **Step 1: Write the failing persistence/API test**

Add coverage for:
- a config header storing only shared fields
- one child scope row per shop account
- one config owning multiple shop scopes under the same platform
- deletion cascading from config header to child scopes

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
pytest backend/tests/test_collection_config_shop_scope_api.py -q
```

Expected: FAIL because the shop-scope model/table does not exist yet.

- [ ] **Step 3: Implement the minimal schema and migration**

Add:
- `CollectionConfigShopScope` in `modules/core/db/schema.py`
- relationship wiring from `CollectionConfig`
- export in `modules/core/db/__init__.py`
- migration file creating the new table, foreign key, unique constraint on `(config_id, shop_account_id)`, and supporting indexes

Do not drop old `CollectionConfig.account_ids` / `CollectionConfig.data_domains` columns in this task. Leave them untouched to reduce migration risk while the new execution truth moves to shop scopes.

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
pytest backend/tests/test_collection_config_shop_scope_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260406_collection_config_shop_scopes.py modules/core/db/schema.py modules/core/db/__init__.py backend/tests/test_collection_config_shop_scope_api.py
git commit -m "feat: add collection config shop scope persistence"
```

### Task 2: Replace Config Contracts With Header Plus Shop Scopes

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/tests/test_collection_config_api.py`
- Modify: `backend/tests/test_collection_frontend_contracts.py`
- Test: `backend/tests/test_collection_config_api.py`

- [ ] **Step 1: Write the failing contract tests**

Cover:
- config create/update accepts `shop_scopes[]` instead of global `account_ids` and global `data_domains`
- every active shop for the selected platform must appear in `shop_scopes`
- every scope must have at least one `data_domain`
- selected domains and sub-domains must be capability-valid for that shop
- config detail responses return header fields plus full `shop_scopes`

- [ ] **Step 2: Run the focused backend contract tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: FAIL because the router/schema still exposes the old global model.

- [ ] **Step 3: Implement the minimal backend contract changes**

Add:
- new Pydantic models for `CollectionConfigShopScopePayload`
- create/update/detail response shapes using `shop_scopes`
- reusable helper(s) in `backend/services/collection_contracts.py` for:
  - required active-shop expansion by platform
  - per-shop domain/sub-domain normalization
  - capability validation

Keep list endpoints lightweight by returning summary data plus shop counts, but make the single-config detail endpoint return the full child-scope payload.

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/services/collection_contracts.py backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: expose collection configs as header plus shop scopes"
```

### Task 3: Synchronize Scheduler State During Save-Time Mutations

**Files:**
- Create: `backend/tests/test_collection_config_schedule_sync_api.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/collection_schedule.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_collection_config_schedule_sync_api.py`

- [ ] **Step 1: Write the failing scheduler-sync tests**

Cover:
- create config with `schedule_enabled=true` registers a job immediately
- update config cron reschedules the existing job immediately
- disable schedule removes the job immediately
- delete config removes the job immediately
- scheduled execution aborts if the config is inactive, `schedule_enabled=false`, or cron state is stale

- [ ] **Step 2: Run the focused scheduler-sync test and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_schedule_sync_api.py -q
```

Expected: FAIL because config saves do not currently synchronize APScheduler state.

- [ ] **Step 3: Implement the minimal synchronization flow**

Add or refactor logic so:
- config create/update/delete triggers scheduler synchronization from the backend
- explicit `/schedule` endpoints reuse the same synchronization helper
- scheduled execution rechecks config runtime state before expanding tasks

If a save requests schedule enablement and job synchronization fails, treat the whole save as failed and roll back.

- [ ] **Step 4: Re-run the focused scheduler-sync test**

Run:

```bash
pytest backend/tests/test_collection_config_schedule_sync_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/collection_config.py backend/routers/collection_schedule.py backend/services/collection_scheduler.py backend/main.py backend/tests/test_collection_config_schedule_sync_api.py
git commit -m "feat: sync collection scheduler state during config saves"
```

### Task 4: Unify Manual And Scheduled Config Execution

**Files:**
- Create: `backend/services/collection_config_execution.py`
- Create: `backend/tests/test_collection_config_execution_service.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/tests/test_collection_scheduler_capability_filter.py`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Test: `backend/tests/test_collection_config_execution_service.py`

- [ ] **Step 1: Write the failing config-execution service test**

Cover:
- one config expands into one task per shop scope
- each created task carries that shop’s own `data_domains` and `sub_domains`
- shops with unsupported domains are filtered per shop, not globally
- one blocked shop does not prevent other shops from getting tasks

- [ ] **Step 2: Run the focused execution test and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_execution_service.py backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: FAIL because manual execution and scheduled execution still use different expansion paths.

- [ ] **Step 3: Implement the shared execution service**

Create one backend service that:
- loads config header plus child scopes
- expands the config into per-shop task payloads
- applies shop-level capability filtering
- creates `CollectionTask` rows and starts background execution

Then:
- make scheduler-triggered runs call this service
- replace frontend per-shop task loops with one backend config-run call if needed to remove duplicate logic from the UI

- [ ] **Step 4: Re-run the focused execution tests**

Run:

```bash
pytest backend/tests/test_collection_config_execution_service.py backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_config_execution.py backend/routers/collection_tasks.py backend/services/collection_scheduler.py backend/tests/test_collection_config_execution_service.py backend/tests/test_collection_scheduler_capability_filter.py frontend/src/api/collection.js frontend/src/views/collection/CollectionConfig.vue
git commit -m "feat: unify collection config execution across manual and scheduled runs"
```

### Task 5: Rebuild The Config Page Around Shop-Scope Editing

**Files:**
- Create: `frontend/scripts/collectionConfigShopScopeUi.test.mjs`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/constants/collection.js`
- Test: `frontend/scripts/collectionConfigShopScopeUi.test.mjs`

- [ ] **Step 1: Write the failing UI contract test**

Cover:
- the page renders config-header controls separately from per-shop scope controls
- all active shops for the selected platform are loaded into the config editor
- each shop has its own domain selection area
- capability auto-apply operates per shop instead of taking a global intersection
- the save payload posts `shop_scopes`
- the run-config path no longer loops on the client with one `createTask` call per shop unless explicitly required by the new backend contract

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: FAIL because the current page still edits one global domain set.

- [ ] **Step 3: Implement the minimal page rebuild**

Add:
- left-side config-header section
- right-side shop-scope cards or rows
- per-shop domain and subtype selection
- bulk helper actions:
  - auto-apply by capability
  - batch domain selection
  - copy one shop scope to other shops
- save flow posting the new payload shape

Do not build a second page. Keep the existing `CollectionConfig.vue` route as the editing surface.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js frontend/src/constants/collection.js frontend/scripts/collectionConfigShopScopeUi.test.mjs
git commit -m "feat: rebuild collection config ui around shop scopes"
```

### Task 6: Add Scheduler Observability And Full Regression Coverage

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_schedule.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Test: `backend/tests/test_collection_config_api.py`
- Test: `backend/tests/test_collection_config_schedule_sync_api.py`
- Test: `backend/tests/test_collection_time_selection_contract.py`
- Test: `backend/tests/test_collection_frontend_contracts.py`
- Test: `frontend/scripts/collectionConfigShopScopeUi.test.mjs`

- [ ] **Step 1: Extend tests for runtime-status visibility**

Cover:
- config list/detail exposes `next_run_time`, `last_run_time`, `last_run_status`, and `job_registered`
- UI renders those values near the schedule controls
- scheduler health endpoints remain truthful under the new save-time sync flow

- [ ] **Step 2: Run the combined regression suite and verify any failures**

Run:

```bash
pytest backend/tests/test_collection_config_shop_scope_api.py backend/tests/test_collection_config_api.py backend/tests/test_collection_config_schedule_sync_api.py backend/tests/test_collection_config_execution_service.py backend/tests/test_collection_scheduler_capability_filter.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_frontend_contracts.py -q
node frontend/scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: FAIL until observability fields and any missed regressions are fixed.

- [ ] **Step 3: Implement the minimal observability changes and regression fixes**

Add:
- scheduler status projection fields to config responses
- lightweight UI rendering for next/last run status
- any final contract glue required to keep manual run, scheduled run, and config list/detail payloads consistent

- [ ] **Step 4: Re-run the full regression suite**

Run:

```bash
pytest backend/tests/test_collection_config_shop_scope_api.py backend/tests/test_collection_config_api.py backend/tests/test_collection_config_schedule_sync_api.py backend/tests/test_collection_config_execution_service.py backend/tests/test_collection_scheduler_capability_filter.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_frontend_contracts.py -q
node frontend/scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_schedule.py backend/routers/collection_config.py frontend/src/api/collection.js frontend/src/views/collection/CollectionConfig.vue backend/tests/test_collection_config_api.py backend/tests/test_collection_config_schedule_sync_api.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_frontend_contracts.py frontend/scripts/collectionConfigShopScopeUi.test.mjs
git commit -m "feat: expose collection scheduler observability for shop-scope configs"
```

## Execution Notes

- Delete old collection configs only after the new CRUD path is working in the isolated worktree.
- Keep old config columns in place during the first implementation wave; use the new shop-scope table as the execution truth first, then decide later whether column cleanup is still worth the risk.
- Prefer backend-driven config execution over frontend fan-out so manual and scheduled runs cannot diverge again.
- Do not loosen the rule that every active shop must appear in the saved payload; make missing scopes a hard validation error.

## Verification Checklist

- Shop-scope config CRUD works end to end.
- Saving with schedule enabled immediately registers a job.
- Editing cron immediately reschedules the job.
- Disabling or deleting a config removes the job.
- Scheduled execution skips stale/disabled configs safely.
- One config expands into one task per shop scope.
- One shop failure does not prevent other shop tasks from running.
- The config page no longer communicates a global shared domain set as the execution truth.
