# Data-Ingested Refresh Serial Queue Design

## Goal
Stabilize the post-ingest PostgreSQL refresh flow by replacing in-process concurrent refresh execution with a durable, globally serialized refresh queue.

## Problem
Current `DATA_INGESTED` handling calls PostgreSQL refresh logic immediately from the event listener. When multiple files finish ingestion in a short window, refresh jobs run concurrently inside the same worker process and compete on shared targets and shared ops log tables.

Observed failures:
- PostgreSQL deadlock on `ops.pipeline_run_log`
- overlapping refreshes on shared semantic/api targets
- poor observability between "event received", "refresh scheduled", and "refresh actually executed"

This is not a data-sync ingestion bug. It is a refresh orchestration bug.

## Design Decision
Introduce a single global refresh queue for `DATA_INGESTED` driven PostgreSQL refresh work.

The queue becomes the control plane:
- `DATA_INGESTED` only enqueues refresh intent
- one refresh worker claims one queue item at a time
- claimed work executes `execute_refresh_plan(...)`
- results are persisted back to the queue row and existing ops logs

## Why Global Serial Instead Of Grouped Parallel
Use a single global queue first because:
- current refresh targets have shared upstream/downstream dependencies
- current failure mode is stability, not throughput
- a single queue is easiest to reason about and verify
- future grouped queues can be built on top of this model if throughput later becomes a real bottleneck

## Scope
This design covers only PostgreSQL refresh work triggered by `DATA_INGESTED`.

It does not change:
- file ingestion logic
- template matching logic
- cloud sync enqueueing
- manual dashboard bootstrap flows except for optional reuse of the same queue model later

## Architecture
### 1. Queue Table
Add a durable queue table in `core`:
- `refresh_queue_tasks`

Suggested fields:
- `id`
- `job_id`
- `trigger_type`
- `pipeline_name`
- `dedupe_key`
- `targets_json`
- `context_json`
- `status`
- `attempt_count`
- `last_error`
- `created_at`
- `started_at`
- `finished_at`

Allowed statuses:
- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

### 2. Enqueue Service
Add a dedicated enqueue/claim/complete service, for example:
- `backend/services/data_pipeline/refresh_queue_service.py`

Responsibilities:
- normalize targets
- generate `dedupe_key`
- insert new pending rows
- coalesce equivalent pending rows instead of duplicating work
- claim exactly one task for execution
- mark running/completed/failed

### 3. Event Listener Change
`backend/services/event_listeners.py`

Replace direct refresh execution for `DATA_INGESTED` with enqueue behavior:
- compute targets
- build queue context
- call queue service
- log queue action

The listener must no longer call `asyncio.create_task(run_pipeline_refresh_for_data_ingested_event(...))` for this path.

### 4. Refresh Consumer
Add a dedicated Celery task, for example:
- `backend/tasks/refresh_queue_tasks.py`

Behavior:
- claim one `pending` queue row
- mark it `running`
- execute `execute_refresh_plan(...)`
- mark final status
- return whether more pending work exists

First release should process one queue item per task invocation.

### 5. Beat Scheduling
Add a beat job that runs frequently, for example every minute:
- consume exactly one pending refresh queue task

This intentionally serializes refresh execution across the whole runtime.

### 6. Dedupe / Coalescing
First release dedupe should be conservative:
- `dedupe_key = pipeline_name + sorted(targets)`

If a matching pending row already exists:
- keep one row
- optionally append recent file IDs into `context_json["related_file_ids"]`

Do not attempt aggressive semantic merging in v1.

## Data Flow
1. ingestion completes
2. `DATA_INGESTED` event is emitted
3. event listener resolves targets
4. listener enqueues refresh intent
5. Celery beat triggers refresh consumer
6. consumer claims one queue row
7. consumer runs `execute_refresh_plan(...)`
8. existing ops logs record target execution
9. queue row records final lifecycle

## Error Handling
### Queue Insert Failure
If enqueue fails:
- log loudly
- do not block the ingestion transaction from completing
- leave the failure observable in application logs

### Refresh Execution Failure
If refresh fails:
- mark queue row `failed`
- store `last_error`
- keep existing ops log failure information

### Retry
Queue worker can retry failed queue items later, but v1 should keep retry policy simple:
- retry at the Celery task level only for transient runtime failures
- do not endlessly retry the same permanently bad queue row

## Observability
Queue layer must make these states visible:
- event was received
- refresh was enqueued
- refresh was coalesced
- refresh started running
- refresh completed or failed

This fills the observability gap that exists today between event listener logs and ops pipeline logs.

## Testing Strategy
Add tests for:
- queue insert on `DATA_INGESTED`
- equivalent pending rows are coalesced
- consumer claims only one row
- consumer marks `running -> completed`
- consumer marks `running -> failed`
- event listener no longer directly runs refresh work for `DATA_INGESTED`
- beat/consumer wiring exists in Celery config

## Acceptance Criteria
- multiple ingested files no longer trigger concurrent in-process refresh execution
- `DATA_INGESTED` path no longer produces refresh deadlocks from same-process overlap
- refresh work is durable and inspectable via queue rows
- equivalent refresh targets are coalesced before execution
- exactly one refresh queue item executes at a time in normal runtime

## Non-Goals
- grouped parallel refresh queues
- advisory-lock based multi-worker parallel refresh
- refactoring unrelated ingestion code
- redesigning pipeline SQL targets themselves
