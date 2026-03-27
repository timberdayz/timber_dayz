# Persistent Task Center Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a durable task center that becomes the common control-plane for long-running data-sync, collection, and cloud-sync work while preserving current frontend task APIs during migration.

**Architecture:** Add new generic `task_center_*` tables and a dedicated task-center service first. Migrate data-sync onto the new store before replacing the in-memory legacy progress path, then mirror collection and cloud-sync into the task center through compatibility adapters so existing APIs remain stable while storage converges.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Celery, APScheduler, pytest

---

## Prerequisite

Use this plan together with:
- `docs/superpowers/specs/2026-03-27-persistent-task-center-design.md`

Do not skip directly to collection or cloud-sync migration before the generic task-center schema and service are landed.

### Task 1: Add Generic Task Center Schema

**Files:**
- Create: `backend/tests/test_task_center_schema.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`

- [ ] **Step 1: Write the failing schema registration test**

```python
from modules.core.db import Base


def test_task_center_tables_are_registered():
    assert "task_center_tasks" in Base.metadata.tables
    assert "task_center_logs" in Base.metadata.tables
    assert "task_center_links" in Base.metadata.tables
```

- [ ] **Step 2: Run the focused schema test to verify it fails**

Run:
```powershell
pytest backend\tests\test_task_center_schema.py -q
```

Expected:
- FAIL because the new task-center tables do not exist yet.

- [ ] **Step 3: Add ORM models in `modules/core/db/schema.py`**

Implement:
- `TaskCenterTask`
- `TaskCenterLog`
- `TaskCenterLink`

Include at least:
- common lifecycle fields
- runner mapping fields
- retry and lease fields
- progress counters
- `details_json`
- log linkage
- subject-link indexes

- [ ] **Step 4: Export the new models through package boundaries**

Update:
- `modules/core/db/__init__.py`
- `backend/models/database.py`

Make sure the new models are reachable through the normal repository import paths.

- [ ] **Step 5: Re-run the focused schema test**

Run:
```powershell
pytest backend\tests\test_task_center_schema.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```powershell
git add backend\tests\test_task_center_schema.py modules\core\db\schema.py modules\core\db\__init__.py backend\models\database.py
git commit -m "feat(tasks): add generic task center schema"
```

### Task 2: Add Task Center Service, Logs, And Reverse Links

**Files:**
- Create: `backend/tests/test_task_center_service.py`
- Create: `backend/services/task_center_service.py`
- Create: `backend/services/task_center_repository.py`

- [ ] **Step 1: Write the failing service contract test**

```python
async def test_task_center_service_creates_task_and_log(async_session):
    service = TaskCenterService(async_session)
    task = await service.create_task(task_id="task-1", task_family="data_sync", task_type="single_file")
    await service.append_log("task-1", level="info", event_type="state_change", message="created")
    loaded = await service.get_task("task-1")
    assert loaded["task_id"] == "task-1"
```

- [ ] **Step 2: Add a failing reverse-link test**

```python
async def test_task_center_service_links_catalog_file(async_session):
    service = TaskCenterService(async_session)
    await service.create_task(task_id="task-1", task_family="data_sync", task_type="single_file")
    await service.add_link("task-1", subject_type="catalog_file", subject_id="42")
    rows = await service.list_by_subject(subject_type="catalog_file", subject_id="42")
    assert len(rows) == 1
```

- [ ] **Step 3: Run the service tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_service.py -q
```

Expected:
- FAIL because the task-center service layer does not exist yet.

- [ ] **Step 4: Implement the repository/service layer**

Implement methods for:
- `create_task()`
- `update_task()`
- `set_runner()`
- `append_log()`
- `add_link()`
- `get_task()`
- `list_tasks()`
- `list_logs()`
- `list_by_subject()`

Centralize all write semantics here so later migrations do not hand-roll dual-write logic in routers.

- [ ] **Step 5: Re-run the service tests**

Run:
```powershell
pytest backend\tests\test_task_center_service.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```powershell
git add backend\tests\test_task_center_service.py backend\services\task_center_service.py backend\services\task_center_repository.py
git commit -m "feat(tasks): add task center service and repository"
```

### Task 3: Migrate `SyncProgressTracker` To A Task Center Adapter

**Files:**
- Create: `backend/tests/test_task_center_sync_progress_adapter.py`
- Modify: `backend/services/sync_progress_tracker.py`
- Modify: `backend/routers/data_sync.py`

- [ ] **Step 1: Write the failing adapter compatibility test**

```python
async def test_sync_progress_tracker_uses_task_center_storage(async_session):
    tracker = SyncProgressTracker(async_session)
    await tracker.create_task(task_id="sync-1", total_files=2, task_type="bulk_ingest")
    task = await tracker.get_task("sync-1")
    assert task["task_id"] == "sync-1"
```

- [ ] **Step 2: Add a failing response-shape test for data-sync progress**

```python
async def test_data_sync_progress_endpoint_keeps_legacy_shape(client, seed_sync_task):
    response = client.get(f"/api/data-sync/progress/{seed_sync_task}")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "task_id" in payload
    assert "file_progress" in payload
    assert "success_files" in payload
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_sync_progress_adapter.py -q
```

Expected:
- FAIL because `SyncProgressTracker` still writes directly to `sync_progress_tasks`.

- [ ] **Step 4: Refactor `SyncProgressTracker` into a compatibility adapter**

Keep the current public methods, but route storage through `TaskCenterService`.

Compatibility rules:
- keep the same method signatures
- map `processing` to the canonical `running` state internally if needed
- preserve current response fields for `/data-sync/progress/*`

- [ ] **Step 5: Update data-sync list/progress routes to read through the adapter**

Do not change API payload shape in this task.

- [ ] **Step 6: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_sync_progress_adapter.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```powershell
git add backend\tests\test_task_center_sync_progress_adapter.py backend\services\sync_progress_tracker.py backend\routers\data_sync.py
git commit -m "refactor(tasks): route sync progress through task center"
```

### Task 4: Persist Business Task To Celery Runner Mapping

**Files:**
- Create: `backend/tests/test_task_center_celery_mapping.py`
- Modify: `backend/routers/data_sync.py`
- Modify: `backend/tasks/data_sync_tasks.py`

- [ ] **Step 1: Write the failing runner-mapping test**

```python
async def test_single_sync_submission_persists_celery_runner_id(client, mocker):
    response = client.post("/api/data-sync/single", json={"file_id": 1})
    assert response.status_code == 200
    assert response.json()["data"]["celery_task_id"] is not None
```

- [ ] **Step 2: Add a failing retry-metadata test**

```python
async def test_task_center_stores_submission_metadata_for_retry(async_session):
    task = await TaskCenterService(async_session).get_task("seed-task")
    assert task["details_json"]["submission_args"]["file_id"] == 1
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_celery_mapping.py -q
```

Expected:
- FAIL because there is no durable runner mapping or retry reconstruction metadata yet.

- [ ] **Step 4: Persist runner metadata at submission time**

When data-sync submits Celery tasks:
- write `external_runner_id`
- write `runner_kind="celery"`
- persist submission arguments in `details_json`

- [ ] **Step 5: Update worker completion paths**

Ensure Celery workers:
- load the business task by `task_id`
- update task-center state instead of assuming standalone tracker rows
- keep current error and progress semantics

- [ ] **Step 6: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_celery_mapping.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```powershell
git add backend\tests\test_task_center_celery_mapping.py backend\routers\data_sync.py backend\tasks\data_sync_tasks.py
git commit -m "feat(tasks): persist celery runner mapping for data sync"
```

### Task 5: Replace Legacy In-Memory `ProgressTracker`

**Files:**
- Create: `backend/tests/test_task_center_progress_compat.py`
- Modify: `backend/services/progress_tracker.py`
- Modify: `backend/routers/field_mapping_status.py`
- Modify: `backend/routers/field_mapping_files.py`
- Modify: `backend/services/auto_ingest_orchestrator.py`

- [ ] **Step 1: Write the failing compatibility test**

```python
async def test_legacy_progress_tracker_survives_process_restart(async_session_factory):
    tracker = ProgressTracker(async_session_factory=async_session_factory)
    await tracker.create_task("legacy-1", 1, "bulk_ingest")
    reloaded = ProgressTracker(async_session_factory=async_session_factory)
    task = await reloaded.get_task("legacy-1")
    assert task["task_id"] == "legacy-1"
```

- [ ] **Step 2: Add a failing legacy API contract test**

```python
async def test_field_mapping_progress_endpoint_keeps_legacy_shape(client, seed_legacy_task):
    response = client.get(f"/api/field-mapping/progress/{seed_legacy_task}")
    assert response.status_code == 200
    payload = response.json()["data"]["progress"]
    assert payload["task_id"] == seed_legacy_task
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_progress_compat.py -q
```

Expected:
- FAIL because legacy progress still depends on in-memory process state.

- [ ] **Step 4: Refactor `ProgressTracker` into a task-center-backed wrapper**

Keep:
- method names
- async behavior
- old field names expected by legacy callers

Remove:
- process-local state as the primary persistence boundary

- [ ] **Step 5: Update legacy callers and endpoints**

Touch:
- `backend/routers/field_mapping_status.py`
- `backend/routers/field_mapping_files.py`
- `backend/services/auto_ingest_orchestrator.py`

Preserve old payloads while reading/writing through the new task center.

- [ ] **Step 6: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_progress_compat.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```powershell
git add backend\tests\test_task_center_progress_compat.py backend\services\progress_tracker.py backend\routers\field_mapping_status.py backend\routers\field_mapping_files.py backend\services\auto_ingest_orchestrator.py
git commit -m "refactor(tasks): replace legacy in-memory progress tracker"
```

### Task 6: Add Subject-Link Writes For File And Business Lookup

**Files:**
- Create: `backend/tests/test_task_center_subject_links.py`
- Modify: `backend/services/data_ingestion_service.py`
- Modify: `backend/services/task_center_service.py`
- Modify: `backend/routers/data_sync.py`

- [ ] **Step 1: Write the failing subject-link test**

```python
async def test_data_sync_task_links_catalog_file_and_source_table(async_session):
    task = await TaskCenterService(async_session).get_task("seed-sync-task")
    links = await TaskCenterService(async_session).list_by_subject(subject_type="catalog_file", subject_id="1")
    assert len(links) == 1
```

- [ ] **Step 2: Add a failing reverse-query test**

```python
async def test_task_center_lists_tasks_for_source_table(async_session):
    rows = await TaskCenterService(async_session).list_by_subject(subject_type="source_table", subject_key="fact_shopee_orders_daily")
    assert rows
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_subject_links.py -q
```

Expected:
- FAIL because task-subject links are not being written yet.

- [ ] **Step 4: Write links during ingestion and submission**

At minimum:
- link data-sync tasks to `catalog_file`
- link data-sync tasks to `source_table`
- store linkage consistently through `TaskCenterService`

- [ ] **Step 5: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_subject_links.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```powershell
git add backend\tests\test_task_center_subject_links.py backend\services\data_ingestion_service.py backend\services\task_center_service.py backend\routers\data_sync.py
git commit -m "feat(tasks): add task subject links for file and table lookup"
```

### Task 7: Mirror Collection Tasks Into The Task Center

**Files:**
- Create: `backend/tests/test_task_center_collection_projection.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/services/task_service.py`

- [ ] **Step 1: Write the failing collection mirror test**

```python
async def test_collection_task_creation_writes_task_center_row(client):
    response = client.post("/api/collection/tasks", json={...})
    assert response.status_code == 200
    # assert matching task-center row exists
```

- [ ] **Step 2: Add a failing collection-log mirror test**

```python
async def test_collection_task_log_is_mirrored_to_task_center(async_session):
    logs = await TaskCenterService(async_session).list_logs("collection-task-id")
    assert logs
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_collection_projection.py -q
```

Expected:
- FAIL because collection writes only `CollectionTask` and `CollectionTaskLog`.

- [ ] **Step 4: Add collection dual-write through one adapter path**

Mirror:
- task creation
- state changes
- pause/resume markers
- retry lineage
- task logs

Do not remove `CollectionTask` or `CollectionTaskLog` in this task.

- [ ] **Step 5: Keep collection API payloads stable**

Verify that:
- `/collection/tasks`
- `/collection/tasks/{task_id}`
- `/collection/tasks/{task_id}/logs`
- `/collection/tasks/{task_id}/resume`

still expose the current frontend-facing fields.

- [ ] **Step 6: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_collection_projection.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```powershell
git add backend\tests\test_task_center_collection_projection.py backend\routers\collection_tasks.py backend\services\collection_scheduler.py backend\services\task_service.py
git commit -m "feat(tasks): mirror collection tasks into task center"
```

### Task 8: Mirror Cloud Sync Queue State Into The Task Center

**Files:**
- Create: `backend/tests/test_task_center_cloud_sync_projection.py`
- Modify: `backend/services/cloud_b_class_auto_sync_dispatch_service.py`
- Modify: `backend/services/cloud_b_class_auto_sync_worker.py`
- Modify: `backend/services/cloud_sync_admin_query_service.py`
- Modify: `backend/services/cloud_sync_admin_command_service.py`

- [ ] **Step 1: Write the failing cloud-sync mirror test**

```python
def test_cloud_sync_enqueue_writes_task_center_row(sync_session, sample_event):
    payload = CloudBClassAutoSyncDispatchService(sync_session).enqueue_or_coalesce(sample_event)
    assert payload["job_id"]
    # assert task-center row exists for that job_id
```

- [ ] **Step 2: Add a failing worker-state mirror test**

```python
async def test_cloud_sync_worker_updates_task_center_status(async_session):
    # seed pending cloud-sync task and run worker
    # assert task-center row moved to completed/failed
    ...
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_cloud_sync_projection.py -q
```

Expected:
- FAIL because cloud sync does not mirror queue rows into task-center storage yet.

- [ ] **Step 4: Mirror queue lifecycle into the task center**

Mirror:
- enqueue/coalesce
- claim/running
- heartbeat or lease refresh events where useful
- retry_waiting
- completed/partial_success/failed/cancelled

Keep `CloudBClassSyncTask` and checkpoint tables intact in this task.

- [ ] **Step 5: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_cloud_sync_projection.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```powershell
git add backend\tests\test_task_center_cloud_sync_projection.py backend\services\cloud_b_class_auto_sync_dispatch_service.py backend\services\cloud_b_class_auto_sync_worker.py backend\services\cloud_sync_admin_query_service.py backend\services\cloud_sync_admin_command_service.py
git commit -m "feat(tasks): mirror cloud sync queue state into task center"
```

### Task 9: Add Unified Read APIs And Compatibility Smoke Coverage

**Files:**
- Create: `backend/tests/test_task_center_api.py`
- Create: `backend/routers/task_center.py`
- Create: `backend/schemas/task_center.py`
- Modify: `frontend/src/views/DataSyncTasks.vue`
- Modify: `frontend/src/views/DataSyncFiles.vue`
- Modify: `frontend/src/views/CollectionTasks.vue`
- Modify: `frontend/src/stores/cloudSync.js`

- [ ] **Step 1: Write the failing API contract test**

```python
async def test_task_center_tasks_endpoint_supports_family_and_status_filters(client):
    response = client.get("/api/task-center/tasks?family=data_sync&status=running&page=1&page_size=20")
    assert response.status_code == 200
```

- [ ] **Step 2: Add a failing reverse-lookup API test**

```python
async def test_task_center_can_lookup_tasks_by_catalog_file(client):
    response = client.get("/api/task-center/tasks/by-subject?subject_type=catalog_file&subject_id=1")
    assert response.status_code == 200
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_task_center_api.py -q
```

Expected:
- FAIL because unified task-center read APIs do not exist yet.

- [ ] **Step 4: Implement read-only task-center APIs**

Add endpoints for:
- paginated task list
- task detail
- task logs
- reverse lookup by subject

Keep old family-specific routes unchanged in this task.

- [ ] **Step 5: Add compatibility smoke coverage**

Verify current frontend pages still work against old APIs after task-center migration:
- `DataSyncTasks.vue`
- `DataSyncFiles.vue`
- `CollectionTasks.vue`
- cloud sync dashboard/store flow

This can stay as focused test or smoke-script coverage, but it must be automated.

- [ ] **Step 6: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_task_center_api.py -q
```

Expected:
- PASS

- [ ] **Step 7: Run focused existing task-flow tests**

Run:
```powershell
pytest backend\tests\test_collection_multi_account_verification_contract.py frontend\scripts\collectionTasksVerificationUi.test.mjs -q
```

Expected:
- PASS or update this command to the equivalent task-focused smoke commands available in the harness.

- [ ] **Step 8: Commit**

```powershell
git add backend\tests\test_task_center_api.py backend\routers\task_center.py backend\schemas\task_center.py frontend\src\views\DataSyncTasks.vue frontend\src\views\DataSyncFiles.vue frontend\src\views\CollectionTasks.vue frontend\src\stores\cloudSync.js
git commit -m "feat(tasks): add unified task center read APIs"
```

### Task 10: Retire Obsolete Storage Carefully

**Files:**
- Create: `backend/tests/test_task_center_cleanup_contract.py`
- Modify: `backend/services/progress_tracker.py`
- Modify: `backend/services/sync_progress_tracker.py`
- Modify: any obsolete migration shims proven unused by prior tasks

- [ ] **Step 1: Write the failing cleanup-contract test**

```python
def test_no_runtime_path_requires_in_memory_progress_tracker():
    # assert legacy wrapper no longer owns primary persistence
    ...
```

- [ ] **Step 2: Run the cleanup test to verify it fails**

Run:
```powershell
pytest backend\tests\test_task_center_cleanup_contract.py -q
```

Expected:
- FAIL until the old persistence shims are no longer required as primary runtime storage.

- [ ] **Step 3: Retire only proven-obsolete storage**

Candidates:
- in-memory-only store internals in `ProgressTracker`
- direct `SyncProgressTask` writes if all paths are now task-center-backed

Do not drop old domain tables in this task unless all compatibility readers are already removed.

- [ ] **Step 4: Re-run cleanup and task-flow tests**

Run:
```powershell
pytest backend\tests\test_task_center_cleanup_contract.py -q
```

Expected:
- PASS

- [ ] **Step 5: Review scope drift**

Run:
```powershell
git diff -- docs/superpowers/specs/2026-03-27-persistent-task-center-design.md docs/superpowers/plans/2026-03-27-persistent-task-center.md modules/core/db/schema.py backend/services backend/routers backend/tasks backend/tests frontend/src/views frontend/src/stores
```

Expected:
- changes stay within task-center migration scope

- [ ] **Step 6: Commit**

```powershell
git add docs/superpowers/specs/2026-03-27-persistent-task-center-design.md docs/superpowers/plans/2026-03-27-persistent-task-center.md modules/core/db/schema.py backend/services backend/routers backend/tasks backend/tests frontend/src/views frontend/src/stores
git commit -m "refactor(tasks): converge long-task storage on task center"
```

## Exit Criteria

The plan is complete only when:
- data-sync, legacy field-mapping progress, collection, and cloud sync all have a durable task-center representation
- task rows survive restart
- task lists support pagination and filtering
- reverse lookup by file or source table exists
- durable task logs exist
- existing frontend task pages still function without a big-bang route cutover
