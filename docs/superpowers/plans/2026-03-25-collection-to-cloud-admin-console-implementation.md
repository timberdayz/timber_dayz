# Collection-to-Cloud Admin Console Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize collection-to-cloud auto sync as an admin-only capability by wiring the worker into the runtime, exposing production-grade health and control APIs, and adding a dedicated `/cloud-sync` operations console in the frontend.

**Architecture:** Keep canonical sync execution centered on the existing `cloud_b_class_sync_*` services, but move runtime ownership and admin-facing state reads into explicit backend contracts. The backend should expose one real health endpoint, one table-centric state endpoint, enriched task endpoints, and a small set of controlled admin actions. The frontend should consume those contracts through a dedicated admin-only page under the existing data collection menu, with table state as the primary operational surface and task/event detail as secondary inspection tools.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, Pinia, Vite, pytest, Playwright/manual smoke

---

## File Structure

### Backend
- Create: `backend/schemas/cloud_sync_admin.py`
- Create: `backend/services/cloud_sync_admin_query_service.py`
- Create: `backend/services/cloud_sync_admin_command_service.py`
- Modify: `backend/main.py`
- Modify: `backend/routers/cloud_sync.py`
- Modify: `backend/services/cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/services/cloud_b_class_auto_sync_factory.py`
- Modify: `backend/services/cloud_b_class_auto_sync_worker.py`
- Modify: `backend/services/event_listeners.py`
- Modify: `env.development.example`
- Modify: `env.production.example`
- Modify: `.env.example`

### Frontend
- Create: `frontend/src/api/cloudSync.js`
- Create: `frontend/src/stores/cloudSync.js`
- Create: `frontend/src/views/CloudSyncManagement.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`

### Tests
- Create: `backend/tests/test_cloud_sync_admin_query_service.py`
- Create: `backend/tests/test_cloud_sync_admin_command_service.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_router.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_factory.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_worker.py`

### Docs
- Create: `docs/deployment/CLOUD_SYNC_ADMIN_CONSOLE_RUNBOOK.md`
- Modify: `docs/deployment/CLOUD_SYNC_OPERATION_NOTES.md`

---

## Task 1: Wire The Cloud Sync Worker Into The Application Lifecycle

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/services/cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/services/cloud_b_class_auto_sync_factory.py`
- Test: `backend/tests/test_cloud_b_class_auto_sync_runtime.py`
- Test: `backend/tests/test_cloud_b_class_auto_sync_factory.py`

- [ ] **Step 1: Write failing lifecycle tests**

Capture the intended runtime behavior first:

```python
async def test_runtime_starts_only_when_worker_enabled(app_settings):
    runtime = build_runtime_from_settings(app_settings)
    assert runtime is None
```

```python
async def test_runtime_health_reports_not_configured_without_cloud_target():
    runtime = CloudBClassAutoSyncRuntime(worker_factory=None)
    started = await runtime.start()
    assert started is False
    assert runtime.get_health()["status"] == "not_configured"
```

- [ ] **Step 2: Run runtime tests to verify the gap**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_factory.py -q`

Expected: FAIL because the current startup path does not yet own full worker enablement and fail-fast config rules.

- [ ] **Step 3: Add explicit runtime/config construction**

Implement a single construction path in `backend/services/cloud_b_class_auto_sync_factory.py` that validates:
- worker enabled flag
- `CLOUD_DATABASE_URL`
- SSH/tunnel related prerequisites if the worker depends on them
- poll interval
- worker id / deployment role behavior

Make `backend/main.py` own:
- creating the runtime once
- storing it on `app.state.cloud_sync_runtime`
- starting it during lifespan startup
- stopping it during shutdown

- [ ] **Step 4: Keep the worker role single-owner**

Ensure runtime start rules make it impossible for every API process to claim tasks by accident. The implementation should be driven by explicit enablement, not implicit import side effects.

- [ ] **Step 5: Re-run runtime/factory tests**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_factory.py -q`

Expected: PASS with explicit health states such as `not_started`, `running`, `stopped`, `not_configured`, and `error`.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/services/cloud_b_class_auto_sync_runtime.py backend/services/cloud_b_class_auto_sync_factory.py backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_factory.py
git commit -m "feat: wire cloud sync worker into app lifecycle"
```

---

## Task 2: Define Admin Schemas And Query/Command Service Boundaries

**Files:**
- Create: `backend/schemas/cloud_sync_admin.py`
- Create: `backend/services/cloud_sync_admin_query_service.py`
- Create: `backend/services/cloud_sync_admin_command_service.py`
- Test: `backend/tests/test_cloud_sync_admin_query_service.py`
- Test: `backend/tests/test_cloud_sync_admin_command_service.py`

- [ ] **Step 1: Write failing schema/service tests**

Define the payload shape before coding the service layer:

```python
def test_health_summary_contains_worker_tunnel_cloud_db_queue():
    payload = build_health_summary_fixture()
    assert set(payload.keys()) == {"worker", "tunnel", "cloud_db", "queue"}
```

```python
def test_table_state_row_contains_checkpoint_and_projection_sections():
    row = build_table_state_fixture()
    assert "checkpoint" in row
    assert "latest_task" in row
    assert "projection" in row
```

```python
def test_command_service_rejects_invalid_table_name():
    with pytest.raises(ValueError):
        service.trigger_sync("orders")
```

- [ ] **Step 2: Run the new service tests**

Run: `pytest backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py -q`

Expected: FAIL because the schemas and services do not exist yet.

- [ ] **Step 3: Implement Pydantic admin schemas**

Create `backend/schemas/cloud_sync_admin.py` for:
- health summary
- queue stats
- table state row
- task detail row
- timeline event row
- command request/response payloads

Keep the status vocabulary fixed:
- task: `pending`, `running`, `retry_waiting`, `completed`, `partial_success`, `failed`, `cancelled`
- projection: `pending`, `completed`, `failed`, `skipped`
- health: `running`, `stopped`, `error`, `healthy`, `unhealthy`, `reachable`, `unreachable`, `unknown`, `not_configured`

- [ ] **Step 4: Implement explicit query and command services**

`cloud_sync_admin_query_service.py` should own read-side aggregation for:
- health summary
- task list/detail
- table-centric state list
- event timeline

`cloud_sync_admin_command_service.py` should own controlled admin actions for:
- trigger sync
- retry task
- cancel stuck task
- dry-run by table
- repair checkpoint by table
- refresh projection by table

New code should be async-first and use `get_async_db()` style dependencies rather than the current sync `SessionLocal()` wrappers.

- [ ] **Step 5: Re-run service tests**

Run: `pytest backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py -q`

Expected: PASS with stable response contracts.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/cloud_sync_admin.py backend/services/cloud_sync_admin_query_service.py backend/services/cloud_sync_admin_command_service.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py
git commit -m "feat: add cloud sync admin query and command services"
```

---

## Task 3: Upgrade The Cloud Sync Router Into A Real Admin API

**Files:**
- Modify: `backend/routers/cloud_sync.py`
- Modify: `backend/services/event_listeners.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_router.py`

- [ ] **Step 1: Expand router contract tests first**

Add failing tests for:
- `GET /api/cloud-sync/health`
- `GET /api/cloud-sync/tables`
- enriched `GET /api/cloud-sync/tasks`
- enriched `GET /api/cloud-sync/tasks/{job_id}`
- `POST /api/cloud-sync/tables/{table_name}/dry-run`
- `POST /api/cloud-sync/tables/{table_name}/repair-checkpoint`
- `POST /api/cloud-sync/tables/{table_name}/refresh-projection`
- `POST /api/cloud-sync/tasks/{job_id}/cancel`

Example:

```python
def test_health_requires_admin(client):
    response = client.get("/api/cloud-sync/health")
    assert response.status_code in {401, 403}
```

```python
def test_tables_endpoint_returns_table_rows(admin_client):
    response = admin_client.get("/api/cloud-sync/tables")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run router tests to verify failures**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_router.py -q`

Expected: FAIL because the current router only exposes minimal task endpoints and placeholder health.

- [ ] **Step 3: Refactor the router to async-first dependencies**

Remove the current sync wrapper pattern based on `SessionLocal()`. Use:
- `Depends(require_admin)`
- `Depends(get_async_db)` where needed
- the new query/command services

Keep the router thin. It should validate input, enforce admin access, and call services.

- [ ] **Step 4: Add real queue/health/event behavior**

The router should expose:
- real worker health from `app.state.cloud_sync_runtime`
- tunnel and cloud DB checks from the query service
- queue counts including oldest pending age
- recent events derived from task transitions and manual admin operations

If `event_listeners.py` already emits enough information, reuse it. If not, extend it only enough to support operator-visible events.

- [ ] **Step 5: Re-run router tests**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_router.py -q`

Expected: PASS with stable admin contracts and preserved admin-only access control.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/cloud_sync.py backend/services/event_listeners.py backend/tests/test_cloud_b_class_auto_sync_router.py
git commit -m "feat: expand cloud sync admin router contracts"
```

---

## Task 4: Harden Worker State, Retry Semantics, And Projection Reporting

**Files:**
- Modify: `backend/services/cloud_b_class_auto_sync_worker.py`
- Modify: `backend/services/cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_worker.py`
- Modify: `backend/tests/test_cloud_b_class_auto_sync_runtime.py`

- [ ] **Step 1: Write failing worker-state tests**

Add tests for:
- stale lease reclaim
- heartbeat updates while running
- `partial_success` when canonical sync succeeds but projection refresh fails
- retry transition from failure to `retry_waiting`
- terminal `failed` after retry limit

Example:

```python
def test_worker_marks_partial_success_when_projection_refresh_fails(worker, task):
    result = worker.run_one("worker-1")
    assert result["status"] == "partial_success"
```

- [ ] **Step 2: Run worker/runtime tests**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_worker.py backend/tests/test_cloud_b_class_auto_sync_runtime.py -q`

Expected: FAIL where the current implementation does not yet preserve the final operator-visible semantics.

- [ ] **Step 3: Implement the minimum hardening**

Update the worker/runtime so that:
- health exposes last heartbeat and last error
- projection failure becomes visible as `partial_success`, not a silent pass
- stale leases can be reclaimed safely
- retry state is explicit and inspectable

Do not add free-form recovery logic. Keep all admin repair paths controlled and table/task-scoped.

- [ ] **Step 4: Re-run worker/runtime tests**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_worker.py backend/tests/test_cloud_b_class_auto_sync_runtime.py -q`

Expected: PASS with stable task/projection semantics.

- [ ] **Step 5: Commit**

```bash
git add backend/services/cloud_b_class_auto_sync_worker.py backend/services/cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py backend/tests/test_cloud_b_class_auto_sync_runtime.py
git commit -m "feat: harden cloud sync worker state reporting"
```

---

## Task 5: Add Frontend Cloud Sync API And Store

**Files:**
- Create: `frontend/src/api/cloudSync.js`
- Create: `frontend/src/stores/cloudSync.js`
- Modify: `frontend/src/api/index.js` only if the project still expects aggregate exports there

- [ ] **Step 1: Define the frontend data contract**

Mirror the backend contract with one dedicated API module instead of mixing these calls into the legacy `api/index.js` surface unless compatibility requires it.

The module should expose:
- `getHealth()`
- `getTables(params)`
- `getTasks(params)`
- `getTask(jobId)`
- `getEvents(params)`
- `triggerSync(payload)`
- `retryTask(jobId)`
- `cancelTask(jobId)`
- `dryRunTable(tableName, payload)`
- `repairCheckpoint(tableName, payload)`
- `refreshProjection(tableName, payload)`

- [ ] **Step 2: Write the store contract first**

The Pinia store should own:
- loading flags per panel, not one global page lock
- selected table/task filters
- latest health snapshot
- latest table list
- latest task list
- latest event list
- action methods wrapping controlled admin commands

Use patterns already present in `frontend/src/stores/accounts.js` rather than the older mixed API style in `frontend/src/stores/dataSync.js`.

- [ ] **Step 3: Implement the API module and store**

The store should support:
- independent refreshes for health, tables, tasks, events
- optimistic refresh after manual action success
- clear error messages without exposing credentials or raw secrets

- [ ] **Step 4: Smoke-check the module shape**

Run:
- `npm --prefix frontend run type-check`

Expected: PASS with no missing imports or invalid store exports.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/cloudSync.js frontend/src/stores/cloudSync.js frontend/src/api/index.js
git commit -m "feat: add cloud sync admin frontend data layer"
```

---

## Task 6: Build The Admin-Only `/cloud-sync` Operations Console

**Files:**
- Create: `frontend/src/views/CloudSyncManagement.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`

- [ ] **Step 1: Add the route and admin-only menu entry**

Follow the existing admin route pattern used by:
- `/account-management`
- `/data-sync/files`
- `/data-sync/tasks`

The route should be:
- path: `/cloud-sync`
- roles: `['admin']`
- permission: reuse `data-sync` unless a dedicated permission is already available and wired

- [ ] **Step 2: Build the page shell before detailed interactions**

Create the page with these sections in order:
- health summary row
- table sync state table
- task queue table
- operations panel
- event timeline

Use Element Plus cards, tables, drawers, dialogs, and tags. Keep the page visually aligned with the existing admin shell rather than introducing a new design system.

- [ ] **Step 3: Implement the primary operator workflow**

Admins should be able to:
- identify degraded worker/tunnel/cloud DB state from the top cards
- locate a problematic `fact_*` table from the table state grid
- inspect task details in a drawer
- run a controlled action with explicit confirmation

Do not expose free-form SQL, raw credentials, or unrestricted task editing.

- [ ] **Step 4: Manual frontend smoke**

Run:
- `npm --prefix frontend run build`

Expected: PASS and produce a bundle without route/import errors.

Then manually verify or use Playwright smoke to confirm:
- admin can open `/#/cloud-sync`
- non-admin cannot access it
- page loads health/tables/tasks
- controlled actions show confirmation and success/error feedback

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/CloudSyncManagement.vue frontend/src/router/index.js frontend/src/config/menuGroups.js
git commit -m "feat: add cloud sync admin console page"
```

---

## Task 7: Document Operations, Recovery, And Deployment Expectations

**Files:**
- Create: `docs/deployment/CLOUD_SYNC_ADMIN_CONSOLE_RUNBOOK.md`
- Modify: `docs/deployment/CLOUD_SYNC_OPERATION_NOTES.md`
- Modify: `.env.example`
- Modify: `env.development.example`
- Modify: `env.production.example`

- [ ] **Step 1: Write the operator runbook**

Document:
- how to enable/disable the worker
- required env vars
- health interpretation
- how to trigger dry-run / retry / checkpoint repair / projection refresh
- what `partial_success` means
- how to investigate tunnel/cloud DB failures

- [ ] **Step 2: Sync environment example files**

Add and describe:
- cloud worker enable flag
- poll interval
- worker id if configurable
- any tunnel/SSH-related required config

- [ ] **Step 3: Verification pass**

Run:
- `pytest backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py -q`
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment/CLOUD_SYNC_ADMIN_CONSOLE_RUNBOOK.md docs/deployment/CLOUD_SYNC_OPERATION_NOTES.md .env.example env.development.example env.production.example
git commit -m "docs: add cloud sync admin console runbook"
```

---

## Task 8: Final Security And Readiness Gate

**Files:**
- Review only unless fixes are required in files above

- [ ] **Step 1: Run a focused security review**

Use the `security-review` skill before merging because this feature includes:
- admin-only control endpoints
- cloud database reachability checks
- SSH/tunnel related operational visibility
- failure detail exposure

The review should explicitly check:
- no credentials or secrets are returned by API payloads
- no raw SSH command strings are exposed to the browser
- admin-only access is enforced on every route
- errors are useful but not sensitive

- [ ] **Step 2: Run a short soak checklist**

Verify:
- worker restarts do not orphan the runtime state
- retrying a failed task updates the queue correctly
- projection failure is visible as `partial_success`
- health remains coherent when the worker is disabled

- [ ] **Step 3: Prepare merge handoff**

Before merging, run:
- `git status --short`
- the full verification commands from Task 7

Then use `verification-before-completion` and `finishing-a-development-branch`.

---

## Notes For Execution

- Prefer implementing backend Tasks 1 through 4 before touching the frontend page.
- Treat the frontend page as dependent on stable backend contracts, not as the place to invent them.
- Keep new backend code async-first. Avoid introducing new sync ORM access patterns in this feature.
- Reuse the current cloud sync tables and services. Do not build a parallel sync system.
- This plan assumes admin-only V1. If role/permission requirements broaden later, split that into a separate follow-up spec and plan.

Plan complete and saved to `docs/superpowers/plans/2026-03-25-collection-to-cloud-admin-console-implementation.md`. Ready to execute.
