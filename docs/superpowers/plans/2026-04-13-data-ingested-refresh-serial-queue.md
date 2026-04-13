# Data-Ingested Refresh Serial Queue Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace in-process concurrent `DATA_INGESTED` PostgreSQL refresh execution with a durable global serial refresh queue.

**Architecture:** Add a queue table plus a queue service for enqueue/claim/complete operations. Convert `DATA_INGESTED` listeners to enqueue refresh work instead of launching immediate refresh tasks, then add a dedicated Celery consumer task plus beat schedule that processes one queue item at a time.

**Tech Stack:** FastAPI backend, SQLAlchemy async, Alembic, Celery, PostgreSQL, pytest

---

### Task 1: Add Queue Schema Contract Tests

**Files:**
- Create: `backend/tests/test_refresh_queue_contract.py`
- Reference: `modules/core/db/schema.py`
- Reference: `migrations/versions/`

- [ ] **Step 1: Write failing tests for the queue ORM/table contract**

Test for:
- queue model exists
- expected status field exists
- required JSON fields exist

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_refresh_queue_contract.py -q`
Expected: FAIL because the queue model does not exist yet

- [ ] **Step 3: Add minimal ORM model in schema**

Modify `modules/core/db/schema.py` to add `RefreshQueueTask` with:
- `job_id`
- `pipeline_name`
- `trigger_type`
- `dedupe_key`
- `targets_json`
- `context_json`
- `status`
- `attempt_count`
- `last_error`
- timestamps

- [ ] **Step 4: Re-run the contract test**

Run: `python -m pytest backend/tests/test_refresh_queue_contract.py -q`
Expected: PASS

### Task 2: Add Migration For Queue Table

**Files:**
- Create: `migrations/versions/20260413_add_refresh_queue_tasks.py`
- Test: `backend/tests/test_refresh_queue_contract.py`

- [ ] **Step 1: Write a migration-chain test for the new refresh queue migration file**

Ensure the migration file exists and references the expected revision chain.

- [ ] **Step 2: Run the migration-chain test to verify it fails**

Run: `python -m pytest backend/tests/test_refresh_queue_contract.py -q`
Expected: FAIL on missing migration file if you added that assertion

- [ ] **Step 3: Add Alembic migration**

Create `core.refresh_queue_tasks` with:
- indexes on `status`, `dedupe_key`, `created_at`

- [ ] **Step 4: Run syntax check**

Run: `python -m py_compile migrations/versions/20260413_add_refresh_queue_tasks.py`
Expected: PASS

### Task 3: Add Queue Service

**Files:**
- Create: `backend/services/data_pipeline/refresh_queue_service.py`
- Create: `backend/tests/data_pipeline/test_refresh_queue_service.py`

- [ ] **Step 1: Write failing queue service tests**

Cover:
- enqueue inserts pending row
- enqueue coalesces identical pending work
- claim returns one oldest pending row
- complete marks queue row completed
- fail marks queue row failed

- [ ] **Step 2: Run queue service tests and verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_refresh_queue_service.py -q`
Expected: FAIL because service does not exist yet

- [ ] **Step 3: Implement minimal queue service**

Methods:
- `enqueue_refresh(...)`
- `claim_next_refresh_task()`
- `mark_running(...)`
- `mark_completed(...)`
- `mark_failed(...)`

- [ ] **Step 4: Re-run queue service tests**

Run: `python -m pytest backend/tests/data_pipeline/test_refresh_queue_service.py -q`
Expected: PASS

### Task 4: Convert Event Listener To Enqueue

**Files:**
- Modify: `backend/services/event_listeners.py`
- Modify: `backend/tests/data_pipeline/test_event_listeners.py`

- [ ] **Step 1: Write failing event-listener tests for enqueue behavior**

Cover:
- `DATA_INGESTED` calls queue enqueue
- listener no longer directly spawns in-process refresh work for this path

- [ ] **Step 2: Run event-listener tests and verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_event_listeners.py -q`
Expected: FAIL because listener still launches refresh directly

- [ ] **Step 3: Implement listener change**

Replace direct refresh execution with:
- resolve targets
- call queue service enqueue
- log enqueue/coalesce result

- [ ] **Step 4: Re-run event-listener tests**

Run: `python -m pytest backend/tests/data_pipeline/test_event_listeners.py -q`
Expected: PASS

### Task 5: Add Serial Queue Consumer Task

**Files:**
- Create: `backend/tasks/refresh_queue_tasks.py`
- Create: `backend/tests/test_refresh_queue_tasks.py`

- [ ] **Step 1: Write failing consumer task tests**

Cover:
- consumer claims one pending queue row
- consumer runs `execute_refresh_plan(...)`
- consumer marks queue row completed
- failure path marks queue row failed

- [ ] **Step 2: Run consumer task tests and verify failure**

Run: `python -m pytest backend/tests/test_refresh_queue_tasks.py -q`
Expected: FAIL because consumer task does not exist yet

- [ ] **Step 3: Implement queue consumer**

Consumer behavior:
- open async DB session
- claim one pending row
- execute refresh
- persist terminal state

- [ ] **Step 4: Re-run consumer tests**

Run: `python -m pytest backend/tests/test_refresh_queue_tasks.py -q`
Expected: PASS

### Task 6: Wire Consumer Into Celery Beat

**Files:**
- Modify: `backend/celery_app.py`
- Modify: `docker-compose.dev.yml` only if queue needs a dedicated worker queue later
- Modify: `backend/tests/test_runtime_config_alignment.py`

- [ ] **Step 1: Write failing runtime/config test for refresh queue beat wiring**

Cover:
- new Celery task module included
- beat schedule contains refresh queue consumer entry

- [ ] **Step 2: Run runtime/config test and verify failure**

Run: `python -m pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: FAIL because beat wiring does not exist yet

- [ ] **Step 3: Implement beat wiring**

Add:
- task include for `backend.tasks.refresh_queue_tasks`
- beat schedule entry for serial queue consumption every minute

- [ ] **Step 4: Re-run runtime/config tests**

Run: `python -m pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: PASS

### Task 7: Remove Old In-Process DATA_INGESTED Refresh Path

**Files:**
- Modify: `backend/services/event_listeners.py`
- Modify: `backend/tests/data_pipeline/test_event_listeners.py`

- [ ] **Step 1: Add failing test that direct in-process refresh is no longer used**

Assert the listener does not call:
- `asyncio.create_task(run_pipeline_refresh_for_data_ingested_event(...))`
- `asyncio.run(run_pipeline_refresh_for_data_ingested_event(...))`
for `DATA_INGESTED`

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest backend/tests/data_pipeline/test_event_listeners.py -q`
Expected: FAIL if old behavior remains

- [ ] **Step 3: Remove the old direct execution branch**

Keep only queue enqueue behavior for `DATA_INGESTED`.

- [ ] **Step 4: Re-run event-listener tests**

Run: `python -m pytest backend/tests/data_pipeline/test_event_listeners.py -q`
Expected: PASS

### Task 8: Add Minimal Observability Surface

**Files:**
- Create: `backend/routers/refresh_queue.py`
- Create: `backend/tests/test_refresh_queue_api.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing API tests for queue visibility**

Cover:
- list queue rows
- filter by status

- [ ] **Step 2: Run API tests and verify failure**

Run: `python -m pytest backend/tests/test_refresh_queue_api.py -q`
Expected: FAIL because API is missing

- [ ] **Step 3: Implement minimal read-only queue API**

Endpoints:
- `GET /api/refresh-queue/tasks`

- [ ] **Step 4: Re-run API tests**

Run: `python -m pytest backend/tests/test_refresh_queue_api.py -q`
Expected: PASS

### Task 9: Verification Sweep

**Files:**
- Verify only

- [ ] **Step 1: Run queue-specific backend tests**

Run: `python -m pytest backend/tests/test_refresh_queue_contract.py backend/tests/data_pipeline/test_refresh_queue_service.py backend/tests/test_refresh_queue_tasks.py backend/tests/data_pipeline/test_event_listeners.py backend/tests/test_refresh_queue_api.py -q`

- [ ] **Step 2: Run runtime/config regression tests**

Run: `python -m pytest backend/tests/test_runtime_config_alignment.py backend/tests/test_celery_async_runtime_reset.py -q`

- [ ] **Step 3: Run syntax checks**

Run: `python -m py_compile backend/services/event_listeners.py backend/services/data_pipeline/refresh_queue_service.py backend/tasks/refresh_queue_tasks.py backend/routers/refresh_queue.py backend/celery_app.py`

- [ ] **Step 4: Manual runtime validation**

Check:
- enqueue happens after ingestion
- only one refresh queue item runs at a time
- no in-process refresh deadlock appears during batch auto-ingest

### Task 10: Commit Series

**Files:**
- All changed files from tasks 1-9

- [ ] **Step 1: Commit schema and migration work**
- [ ] **Step 2: Commit queue service and listener refactor**
- [ ] **Step 3: Commit Celery wiring and API visibility**
- [ ] **Step 4: Commit final verification/doc touch-ups if needed**

Plan complete and saved to `docs/superpowers/plans/2026-04-13-data-ingested-refresh-serial-queue.md`. Ready to execute?
