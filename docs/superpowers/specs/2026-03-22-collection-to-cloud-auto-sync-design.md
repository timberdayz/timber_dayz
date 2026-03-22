# Collection-to-Cloud Auto Sync Design

**Date:** 2026-03-22

## Goal

Build an automatic local-to-cloud B-class sync workflow that starts only after local `b_class` ingestion succeeds, reuses the existing collection/ingestion/event framework, and avoids introducing a second orchestration stack for the same pipeline.

## Non-Goals

Out of scope for the first implementation:
- bidirectional sync
- row-level real-time CDC
- syncing directly from browser collection output before local ingestion
- introducing a brand new external queue/worker platform only for cloud sync

## Key Decision

The correct trigger boundary is **local ingestion success**, not **collection task completion**.

Reason:
- `CollectionTask` only proves browser collection finished.
- cloud sync reads from local `b_class.fact_*` tables, so the first safe sync point is after `DataIngestionService` commits local writes.
- this prevents syncing an empty or partially-ingested local table.

## Existing Framework To Reuse

### 1. Existing event entrypoint

The repository already emits `DATA_INGESTED` after successful local ingestion:
- `backend/services/data_ingestion_service.py`
- `backend/utils/events.py`
- `backend/services/event_listeners.py`

Today that listener only logs because the old materialized-view automation was disabled. This is the best insertion point for cloud auto sync.

### 2. Existing table-name resolution

The repository already has the correct SSOT for dynamic B-class table naming:
- `backend/services/platform_table_manager.py`

This service already resolves:
- `fact_{platform}_{data_domain}_{granularity}`
- `fact_{platform}_{data_domain}_{sub_domain}_{granularity}`

Cloud auto sync must reuse this service instead of hardcoding table names.

### 3. Existing scheduling pattern

The repository already has an in-process scheduler:
- `backend/services/collection_scheduler.py`

This should be reused for:
- periodic retry scan
- pending-job healing after restart
- optional fallback full-table sync jobs

### 4. Existing queue/concurrency pattern

The repository already has a queue/status-transition model for collection tasks:
- `backend/services/task_service.py`

The optimistic-locking and queued/running/completed state machine are worth copying conceptually, but **not** by overloading `CollectionTask` itself.

### 5. Existing persistent progress model

The repository already has file/task progress persistence:
- `backend/services/sync_progress_tracker.py`
- `backend/routers/data_sync.py`

The API and state-shape conventions are reusable, but the current tracker is file-centric. Cloud sync should not force-fit table sync into `SyncProgressTask`.

### 6. Existing cloud sync core implementation

The validated manual sync implementation already exists in the `local-cloud-b-class-sync` worktree branch, including:
- tunnel management
- readiness checks
- checkpointed table sync
- projection refresh

This implementation should be merged first and then used as the execution core for automation, rather than being reimplemented inside the main collection codepath.

## What Not To Reuse

Do not reuse these as the primary automation backbone:

- `CollectionTask` table itself
  - it models browser collection lifecycle, not cloud replication lifecycle
- old disabled MV refresh logic
  - the event hook is reusable, the old target action is not
- Celery-first orchestration for v1
  - cloud sync needs stable SSH key/tunnel execution on the same machine profile
  - the repository already has an APScheduler + in-process background-task pattern

## Recommended Architecture

## Control Plane

Add a new local task table, for example:
- `cloud_b_class_sync_tasks`

Purpose:
- represent sync jobs at the **source-table** level
- track retries, failures, and projection refresh state
- provide an admin-visible queue independent of `CollectionTask`

Suggested fields:
- `id`
- `job_id`
- `source_table_name`
- `platform_code`
- `data_domain`
- `sub_domain`
- `granularity`
- `trigger_source` (`manual`, `auto_ingest`, `scheduled_retry`, `repair`)
- `source_file_id`
- `status` (`pending`, `running`, `partial_success`, `completed`, `failed`, `retry_waiting`, `cancelled`)
- `attempt_count`
- `next_retry_at`
- `last_error`
- `projection_preset`
- `projection_status`
- `metadata` (JSONB)
- `created_at`
- `claimed_at`
- `finished_at`

This table is the **control-plane queue**.

The existing:
- `cloud_b_class_sync_checkpoints`
- `cloud_b_class_sync_runs`

remain the **data-plane state** and should not be overloaded to behave like a task queue.

## Data Plane

Reuse the already-validated cloud sync services:
- tunnel service
- readiness service
- checkpoint service
- canonical sync service
- projection service

Execution contract:
1. ensure tunnel is healthy
2. sync the affected local `b_class` source table to cloud canonical
3. refresh projection if a stable preset exists
4. update control-plane task status

## Trigger Design

### Primary trigger

Extend `DataIngestedEvent` so it carries enough routing metadata:
- `sub_domain`
- `source_table_name`
- optional `projection_preset`

Then change `EventListener.handle_data_ingested()` from a logging-only stub into:
- enqueue cloud sync task
- do **not** perform cloud sync inline

This preserves the existing event framework and keeps ingestion latency bounded.

### Why enqueue instead of syncing inline

Because cloud sync depends on:
- SSH tunnel health
- remote database availability
- projection refresh success

These are operational concerns and must not block:
- file ingestion responses
- auto-ingest orchestration
- local transaction completion

## Dispatcher / Worker Design

Add a service such as:
- `CloudBClassAutoSyncDispatchService`
- `CloudBClassAutoSyncWorker`

Responsibilities:

### Dispatch service

- accept `DATA_INGESTED` events
- coalesce duplicate jobs for the same `source_table_name`
- resolve default projection preset from data domain / table name
- create or update a pending job row

Coalescing rule:
- if the same table already has a `pending`, `running`, or `retry_waiting` task, do not enqueue another independent task
- instead update `metadata.latest_trigger_at` and increment `metadata.trigger_count`

This avoids a queue explosion during batch ingest.

### Worker

- claim runnable tasks
- ensure background tunnel is healthy
- call `sync_table(source_table_name)`
- optionally refresh projection
- update task status and retry metadata

Claiming model:
- single-writer per row via optimistic update or `FOR UPDATE SKIP LOCKED`
- initial concurrency should be `1`

Reason:
- table-level checkpoint sync is already incremental
- tunnel and projection paths are easier to stabilize with serialized execution first

## Projection Strategy

Use existing validated presets where available.

Rule:
- if table has a stable preset, auto-refresh projection
- if no preset exists, sync canonical only and mark `projection_status = skipped`

This keeps canonical replication authoritative while not blocking on schema/preset coverage gaps.

## Failure and Retry Strategy

### Retry classes

Retryable:
- tunnel not healthy
- cloud DB unavailable
- transient SSH/process failures
- projection refresh runtime failure

Non-retryable without code/data fix:
- invalid table naming
- unsupported preset mapping contract
- permanent configuration missing (`CLOUD_DATABASE_URL`, SSH key path)

### Backoff

Recommended initial backoff:
- attempt 1: immediately
- attempt 2: +1 minute
- attempt 3: +5 minutes
- attempt 4: +15 minutes
- attempt 5: +60 minutes

After retry limit:
- mark task `failed`
- keep checkpoint unchanged
- surface to admin endpoint / logs / alerting

Because checkpoint advancement is commit-after-write only, re-running a failed table sync remains safe.

## Tunnel Strategy

Do not create a new tunnel implementation.

Reuse the validated model:
- one reusable background local tunnel
- health/status probe before each task
- restart once if unhealthy

Operational rule:
- auto sync must run only on hosts with non-interactive SSH key access
- password-interactive tunnel mode is not acceptable for unattended automation

## API Surface

Add a small admin API set, reusing the style of `backend/routers/data_sync.py`:

- `POST /api/cloud-sync/tasks/trigger`
  - manual trigger by table
- `GET /api/cloud-sync/tasks`
  - list queue tasks
- `GET /api/cloud-sync/tasks/{job_id}`
  - inspect one task
- `POST /api/cloud-sync/tasks/{job_id}/retry`
  - force retry
- `GET /api/cloud-sync/health`
  - tunnel + cloud DB + worker health

Do not add a second UI-only progress format. Follow the existing sync/progress response style where practical.

## Rollout Plan

### Phase 0: Merge prerequisite cloud sync core

Before automation, merge the validated `local-cloud-b-class-sync` implementation into the main line:
- sync service
- checkpoint/run tables
- tunnel tooling
- projection tooling

Without this, auto sync would be forced to reimplement already-validated logic.

### Phase 1: Re-enable event path for cloud sync enqueue

- extend `DataIngestedEvent`
- implement enqueue-only listener behavior
- add `cloud_b_class_sync_tasks`

Success criteria:
- every successful local ingestion can create or coalesce a cloud sync task
- no cloud write happens inline inside ingestion request flow

### Phase 2: Add in-process dispatcher

- add worker service
- add scheduler-driven retry/poll loop
- support single-table automatic sync

Success criteria:
- pending tasks are automatically claimed and completed
- failures retry with backoff

### Phase 3: Add projection automation

- preset resolver
- projection refresh after canonical success
- partial-success semantics if projection fails

### Phase 4: Add admin visibility and alerts

- API endpoints
- health endpoint
- failure summary / alert hook

### Phase 5: Soak and hardening

- long-running tunnel observation
- restart recovery
- duplicate-event coalescing verification

## Why This Design Avoids Duplicate Work

This design intentionally reuses:
- existing `DATA_INGESTED` event emission
- existing `PlatformTableManager`
- existing scheduler pattern
- existing queue/state-machine ideas
- existing cloud sync execution core from the validated worktree

It deliberately avoids creating:
- a second event framework
- a second scheduler framework
- a second table-name resolver
- a second cloud sync implementation
- a direct cloud-sync call path embedded into Playwright collection execution

## Recommendation

Implement the first version as:

1. merge the validated manual cloud sync core
2. extend `DATA_INGESTED`
3. enqueue source-table sync tasks
4. run a single-threaded in-process worker with retry
5. auto-refresh projection only when a stable preset exists

That is the smallest implementation that is operationally safe, aligned with the repository’s current architecture, and avoids repeating work already done elsewhere.
