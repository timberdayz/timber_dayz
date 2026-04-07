# Collection-to-Cloud Auto Sync Preparation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the control-plane and runtime wiring needed to run automatic local-to-cloud B-class sync safely after ingestion succeeds.

**Architecture:** First land the manual canonical sync core defined in the 2026-03-18 design/plan. Then add a durable task queue, enqueue-only event handling, and a dedicated worker that claims, retries, and observes table-level sync work without coupling ingestion latency to cloud availability.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, APScheduler, pytest

---

## Prerequisite

This plan assumes the manual canonical sync core from the following documents is either already landed or executed first in the same implementation stream:

- `docs/superpowers/specs/2026-03-18-local-cloud-b-class-canonical-sync-design.md`
- `docs/superpowers/plans/2026-03-18-local-cloud-b-class-canonical-sync.md`

Automation work should not bypass that prerequisite by creating a second sync core.

### Task 1: Add Cloud Auto Sync Task Schema

**Files:**
- Create: `backend/tests/test_cloud_b_class_auto_sync_task_schema.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from modules.core.db import Base


def test_cloud_auto_sync_task_table_is_registered():
    assert "cloud_b_class_sync_tasks" in Base.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_task_schema.py -q`
Expected: FAIL because the task table is not registered yet.

- [ ] **Step 3: Add the ORM model**

Add `CloudBClassSyncTask` in `modules/core/db/schema.py` with fields for:
- queue identity: `id`, `job_id`, `dedupe_key`
- routing: `source_table_name`, `platform_code`, `data_domain`, `sub_domain`, `granularity`, `source_file_id`
- execution state: `status`, `attempt_count`, `next_retry_at`
- lease state: `claimed_by`, `lease_expires_at`, `heartbeat_at`
- failure state: `last_error`, `error_code`
- projection state: `projection_preset`, `projection_status`
- bookkeeping: `metadata`, `created_at`, `updated_at`, `finished_at`

- [ ] **Step 4: Export the model through package boundaries**

Update `modules/core/db/__init__.py` and `backend/models/database.py` so the new model is reachable from the normal import paths.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_task_schema.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_cloud_b_class_auto_sync_task_schema.py modules/core/db/schema.py modules/core/db/__init__.py backend/models/database.py
git commit -m "feat(sync): add cloud auto sync task schema"
```

### Task 2: Extend Ingestion Event Contract And Enqueue-Only Listener

**Files:**
- Create: `backend/tests/test_cloud_b_class_auto_sync_event_flow.py`
- Modify: `backend/utils/events.py`
- Modify: `backend/services/event_listeners.py`
- Modify: `backend/services/data_ingestion_service.py`

- [ ] **Step 1: Write the failing event contract test**

```python
from backend.utils.events import DataIngestedEvent


def test_data_ingested_event_carries_source_table_metadata():
    event = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        sub_domain=None,
        granularity="daily",
        source_table_name="fact_shopee_orders_daily",
        row_count=10,
    )
    assert event.source_table_name == "fact_shopee_orders_daily"
```

- [ ] **Step 2: Add a failing listener-behavior test**

```python
def test_listener_enqueues_but_does_not_sync_inline(fake_dispatch_service, sample_event):
    fake_dispatch_service.enqueue_or_coalesce.return_value = {"job_id": "job-1"}
    result = EventListener.handle_data_ingested(sample_event)
    assert result["job_id"] == "job-1"
    assert fake_dispatch_service.sync_inline_called is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_event_flow.py -q`
Expected: FAIL because the new event fields and enqueue behavior do not exist yet.

- [ ] **Step 4: Extend `DataIngestedEvent`**

Add at least:
- `sub_domain`
- `source_table_name`
- optional `projection_preset`
- optional `ingest_run_id`

Keep the event DTO lightweight and serialization-friendly.

- [ ] **Step 5: Change the listener to enqueue-only**

Update `EventListener.handle_data_ingested()` so it:
- validates the routing metadata
- delegates to a dispatch service
- returns queue metadata
- does not perform remote sync work inline

- [ ] **Step 6: Populate the event from ingestion code**

Update `backend/services/data_ingestion_service.py` to fill the new event fields using the same table-name rules already used for local B-class writes.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_event_flow.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_cloud_b_class_auto_sync_event_flow.py backend/utils/events.py backend/services/event_listeners.py backend/services/data_ingestion_service.py
git commit -m "feat(sync): make data ingested listener enqueue cloud sync tasks"
```

### Task 3: Build Dispatch Service With Coalescing Rules

**Files:**
- Create: `backend/tests/test_cloud_b_class_auto_sync_dispatch_service.py`
- Create: `backend/services/cloud_b_class_auto_sync_dispatch_service.py`

- [ ] **Step 1: Write the failing dispatch-service test**

```python
def test_enqueue_or_coalesce_reuses_existing_pending_task(async_session, sample_event):
    service = CloudBClassAutoSyncDispatchService(async_session)
    first = await service.enqueue_or_coalesce(sample_event)
    second = await service.enqueue_or_coalesce(sample_event)
    assert first["job_id"] == second["job_id"]
```

- [ ] **Step 2: Add a failing trigger-count test**

```python
def test_enqueue_or_coalesce_increments_trigger_count(async_session, sample_event):
    service = CloudBClassAutoSyncDispatchService(async_session)
    await service.enqueue_or_coalesce(sample_event)
    result = await service.enqueue_or_coalesce(sample_event)
    assert result["metadata"]["trigger_count"] == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_dispatch_service.py -q`
Expected: FAIL because the service does not exist yet.

- [ ] **Step 4: Implement the dispatch service**

Create `backend/services/cloud_b_class_auto_sync_dispatch_service.py` with methods for:
- `enqueue_or_coalesce(event)`
- `_build_dedupe_key(event)`
- `_resolve_projection_preset(event)`

Behavior:
- create a new task when no runnable task exists for the source table
- otherwise update the existing task metadata and return its `job_id`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_dispatch_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_cloud_b_class_auto_sync_dispatch_service.py backend/services/cloud_b_class_auto_sync_dispatch_service.py
git commit -m "feat(sync): add cloud auto sync dispatch service"
```

### Task 4: Build Worker Claim, Lease, And Retry Logic

**Files:**
- Create: `backend/tests/test_cloud_b_class_auto_sync_worker.py`
- Create: `backend/services/cloud_b_class_auto_sync_worker.py`

- [ ] **Step 1: Write the failing claim test**

```python
def test_worker_claims_one_runnable_task(async_session):
    worker = CloudBClassAutoSyncWorker(async_session, sync_executor=FakeSyncExecutor())
    task = await worker.claim_next_task(worker_id="worker-1")
    assert task is not None
    assert task.claimed_by == "worker-1"
```

- [ ] **Step 2: Add a failing retry test**

```python
def test_worker_moves_retryable_failure_to_retry_waiting(async_session, pending_task):
    executor = FakeSyncExecutor(should_fail=True, error_code="cloud_db_unavailable")
    worker = CloudBClassAutoSyncWorker(async_session, sync_executor=executor)
    await worker.run_one(worker_id="worker-1")
    refreshed = await async_session.get(type(pending_task), pending_task.id)
    assert refreshed.status == "retry_waiting"
```

- [ ] **Step 3: Add a failing partial-success test**

```python
def test_worker_marks_partial_success_when_projection_fails(async_session, pending_task):
    executor = FakeSyncExecutor(sync_ok=True, projection_ok=False)
    worker = CloudBClassAutoSyncWorker(async_session, sync_executor=executor)
    await worker.run_one(worker_id="worker-1")
    refreshed = await async_session.get(type(pending_task), pending_task.id)
    assert refreshed.status == "partial_success"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_worker.py -q`
Expected: FAIL because the worker does not exist yet.

- [ ] **Step 5: Implement the worker**

Create `backend/services/cloud_b_class_auto_sync_worker.py` with methods for:
- `claim_next_task(worker_id)`
- `run_one(worker_id)`
- `heartbeat(task_id, worker_id)`
- `_compute_next_retry_at(attempt_count, error_code)`

Design rules:
- use row-level claim semantics compatible with `FOR UPDATE SKIP LOCKED`
- set and clear lease fields explicitly
- depend on an injected sync executor instead of reimplementing the manual sync core

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_worker.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_cloud_b_class_auto_sync_worker.py backend/services/cloud_b_class_auto_sync_worker.py
git commit -m "feat(sync): add cloud auto sync worker with lease and retry"
```

### Task 5: Add Worker Role Wiring And Admin API

**Files:**
- Create: `backend/tests/test_cloud_b_class_auto_sync_router.py`
- Create: `backend/routers/cloud_sync.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing router contract test**

```python
def test_cloud_sync_health_endpoint_returns_worker_status(test_client):
    response = test_client.get("/api/cloud-sync/health")
    assert response.status_code == 200
    body = response.json()
    assert "worker" in body
    assert "tunnel" in body
```

- [ ] **Step 2: Add a failing manual-trigger test**

```python
def test_manual_trigger_endpoint_enqueues_task(test_client):
    response = test_client.post("/api/cloud-sync/tasks/trigger", json={"source_table_name": "fact_shopee_orders_daily"})
    assert response.status_code == 200
    assert "job_id" in response.json()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_router.py -q`
Expected: FAIL because the router does not exist yet.

- [ ] **Step 4: Implement the router**

Create `backend/routers/cloud_sync.py` with:
- `POST /api/cloud-sync/tasks/trigger`
- `GET /api/cloud-sync/tasks`
- `GET /api/cloud-sync/tasks/{job_id}`
- `POST /api/cloud-sync/tasks/{job_id}/retry`
- `GET /api/cloud-sync/health`

- [ ] **Step 5: Wire the worker role**

Update startup wiring so:
- API role can expose router endpoints
- dedicated worker role can start the claim/retry loop
- worker role can be toggled by explicit config

Do not start a claiming loop in every API process.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_cloud_b_class_auto_sync_router.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_cloud_b_class_auto_sync_router.py backend/routers/cloud_sync.py backend/services/collection_scheduler.py backend/main.py
git commit -m "feat(sync): add cloud auto sync router and worker-role wiring"
```

### Task 6: Security Hardening, Docs, And Verification

**Files:**
- Modify: `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`
- Modify: `docs/deployment/LOCAL_AND_CLOUD_DEPLOYMENT_ROLES.md`
- Modify: `docs/guides/DATA_MIGRATION_GUIDE.md`

- [ ] **Step 1: Document required environment and runtime rules**

Add:
- worker enable flag
- `CLOUD_DATABASE_URL`
- SSH key path requirements
- known-host verification requirement
- dry-run and repair commands

- [ ] **Step 2: Document the operational workflow**

Document:
- ingestion -> task enqueue
- worker polling/claiming
- checkpointed sync
- projection refresh
- retry and manual repair

- [ ] **Step 3: Run targeted verification**

Run:
`pytest backend/tests/test_cloud_b_class_auto_sync_task_schema.py backend/tests/test_cloud_b_class_auto_sync_event_flow.py backend/tests/test_cloud_b_class_auto_sync_dispatch_service.py backend/tests/test_cloud_b_class_auto_sync_worker.py backend/tests/test_cloud_b_class_auto_sync_router.py -q`

Expected: PASS

- [ ] **Step 4: Run security review before merge**

Review changed files against:
- SQL execution paths
- SSH credential handling
- config validation
- log redaction
- admin API exposure

- [ ] **Step 5: Commit**

```bash
git add docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md docs/deployment/LOCAL_AND_CLOUD_DEPLOYMENT_ROLES.md docs/guides/DATA_MIGRATION_GUIDE.md
git commit -m "docs(sync): document collection-to-cloud auto sync operations"
```
