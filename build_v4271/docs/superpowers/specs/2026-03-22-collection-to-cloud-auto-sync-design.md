# Collection-to-Cloud Auto Sync Design

**Date:** 2026-03-22
**Last Updated:** 2026-03-23

## Goal

Build an automatic local-to-cloud B-class sync workflow that starts only after local `b_class` ingestion succeeds, reuses the existing collection/ingestion/event framework, and avoids introducing a second orchestration stack for the same pipeline.

## Non-Goals

Out of scope for the first implementation:
- bidirectional sync
- row-level real-time CDC
- syncing directly from browser collection output before local ingestion
- introducing a brand new external queue/worker platform only for cloud sync
- making every API worker process responsible for cloud sync execution

## Current Reality Check

The mainline repository does **not** currently contain a merged, runnable B-class manual sync implementation.

What exists today:
- a canonical sync design document:
  - `docs/superpowers/specs/2026-03-18-local-cloud-b-class-canonical-sync-design.md`
- a canonical sync implementation plan:
  - `docs/superpowers/plans/2026-03-18-local-cloud-b-class-canonical-sync.md`
- deployment/docs references that assume local-to-cloud sync exists

What does **not** exist today in mainline:
- `backend/services/cloud_b_class_sync_service.py`
- `backend/services/cloud_b_class_sync_checkpoint_service.py`
- `backend/services/cloud_b_class_mirror_manager.py`
- `scripts/sync_b_class_to_cloud.py`
- checkpoint/run ORM models for cloud B-class sync

That means auto sync cannot be treated as a simple integration task on top of an already-landed manual sync core.

## Key Decisions

### 1. The trigger boundary is local ingestion success

The correct trigger boundary is **local ingestion success**, not **collection task completion**.

Reason:
- `CollectionTask` only proves browser collection finished.
- cloud sync reads from local `b_class.fact_*` tables, so the first safe sync point is after `DataIngestionService` commits local writes.
- this prevents syncing an empty or partially-ingested local table.

### 2. Durable enqueue is the v1 reliability boundary

The automation must not rely on a best-effort in-memory callback as the reliability boundary.

Today:
- `DataIngestionService` creates `DataIngestedEvent`
- then directly calls `event_listener.handle_data_ingested(event)`
- the listener only logs

That callback shape is useful as a **hook**, but not sufficient as a durable automation queue.

For v1, the durable boundary should be:
- local ingestion commit succeeds
- a local cloud-sync task row is persisted
- a worker later claims and executes that task

### 3. Use one dedicated worker role first

Initial execution should be serialized through one dedicated cloud-sync worker role.

Reason:
- SSH tunnel lifecycle is operationally fragile compared with normal DB writes
- table-level checkpoint sync is already incremental
- projection refresh sequencing is easier to reason about with single concurrency
- this is the smallest safe runtime shape

## Existing Assets To Reuse

### 1. Existing event entrypoint

The repository already emits `DATA_INGESTED` after successful local ingestion:
- `backend/services/data_ingestion_service.py`
- `backend/utils/events.py`
- `backend/services/event_listeners.py`

This is still the right orchestration insertion point, but the listener must become **enqueue-only**, not **execute-inline**.

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

However, the scheduler should drive a **cloud-sync worker loop**, not inline cloud writes in normal request handlers.

### 4. Existing queue/concurrency ideas

The repository already has queue/status-transition ideas in:
- `backend/services/task_service.py`

The state-machine pattern is worth copying conceptually, but **not** by overloading `CollectionTask` itself.

### 5. Existing progress/API conventions

The repository already has progress-tracking conventions in:
- `backend/services/sync_progress_tracker.py`
- `backend/routers/data_sync.py`

Cloud sync should reuse response-shape and visibility ideas where practical, but it needs its own table-oriented control plane.

### 6. Existing manual-sync design assets

The repository already defines the intended manual sync contract in:
- `docs/superpowers/specs/2026-03-18-local-cloud-b-class-canonical-sync-design.md`
- `docs/superpowers/plans/2026-03-18-local-cloud-b-class-canonical-sync.md`

These are the prerequisite design assets for:
- canonical payload contract
- checkpoint semantics
- cloud mirror table rules
- idempotent upsert expectations

## What Not To Reuse

Do not reuse these as the primary automation backbone:

- `CollectionTask` table itself
  - it models browser collection lifecycle, not cloud replication lifecycle
- old disabled MV refresh logic
  - the event hook is reusable, the old target action is not
- per-request FastAPI background execution as the reliability boundary
  - cloud sync depends on SSH tunnel health, remote DB reachability, and retryable failures
- Celery-first orchestration for v1
  - cloud sync needs stable SSH key/tunnel execution on the same machine profile
  - the repository already has an APScheduler pattern and local-worker expectations

## Recommended Architecture

## Control Plane

Add a new local task table:
- `cloud_b_class_sync_tasks`

Purpose:
- represent sync jobs at the **source-table** level
- track retries, leases, failures, and projection refresh state
- provide an admin-visible queue independent of `CollectionTask`

Suggested fields:
- `id`
- `job_id`
- `dedupe_key`
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
- `claimed_by`
- `lease_expires_at`
- `heartbeat_at`
- `last_attempt_started_at`
- `last_attempt_finished_at`
- `last_error`
- `error_code`
- `projection_preset`
- `projection_status`
- `metadata` (JSONB)
- `created_at`
- `updated_at`
- `finished_at`

This table is the **control-plane queue**.

The existing planned:
- `cloud_b_class_sync_checkpoints`
- `cloud_b_class_sync_runs`

remain the **data-plane execution state** and should not be overloaded to behave like a task queue.

## Data Plane

The data-plane execution core should follow the manual canonical sync design:
- tunnel management
- cloud readiness check
- per-table checkpointed sync
- cloud canonical mirror table management
- optional projection refresh

Execution contract:
1. ensure tunnel is healthy
2. sync the affected local `b_class` source table to cloud canonical
3. refresh projection if a stable preset exists
4. update control-plane task status

## Durable Enqueue Model

The worker queue must be persisted locally.

Preferred v1 behavior:
1. local ingestion transaction commits
2. a cloud-sync task row is created immediately as the durable follow-up action
3. the listener remains enqueue-only

Design rule:
- do **not** perform cloud sync inline inside ingestion request flow
- do **not** treat the Python event callback itself as the durable queue

If ingestion and task creation cannot share one exact DB transaction boundary cleanly in the current code path, the implementation should still enforce:
- ingestion result is committed first
- task creation is attempted immediately after
- task creation failure is surfaced and logged as a distinct operational error

The intended end-state remains a transactional-outbox-style durable enqueue boundary.

## Trigger Design

### Primary trigger

Extend `DataIngestedEvent` so it carries enough routing metadata:
- `sub_domain`
- `source_table_name`
- optional `projection_preset`
- optional `ingest_run_id`

Then change `EventListener.handle_data_ingested()` from a logging-only stub into:
- resolve the affected source table through `PlatformTableManager` rules
- create or coalesce a cloud sync task
- return without remote I/O

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

Add services such as:
- `CloudBClassAutoSyncDispatchService`
- `CloudBClassAutoSyncWorker`

Responsibilities:

### Dispatch service

- accept `DATA_INGESTED` events
- resolve source table identity and default projection preset
- coalesce duplicate jobs for the same source table
- create or update a pending job row

Coalescing rule:
- if the same table already has a `pending`, `running`, or `retry_waiting` task, do not enqueue another independent task
- instead update:
  - `metadata.latest_trigger_at`
  - `metadata.trigger_count`
  - `source_file_id` if the new task carries newer context

This avoids a queue explosion during batch ingest.

### Worker

- claim runnable tasks
- maintain a lease / heartbeat while executing
- ensure background tunnel is healthy
- call the manual sync core `sync_table(source_table_name)`
- optionally refresh projection
- update task status and retry metadata

Claiming model:
- single-writer per row via optimistic update or `FOR UPDATE SKIP LOCKED`
- initial concurrency should be `1`
- stale leases must be reclaimable after timeout

## Runtime Topology

V1 should run with a dedicated cloud-sync worker role:

- API / ingestion role
  - handles ingestion, emits event, persists sync task
- cloud-sync worker role
  - polls runnable tasks
  - executes sync
  - reports health

Do **not** run an independent claiming loop in every API worker process.

APScheduler can still be reused, but only inside the dedicated worker role for:
- retry polling
- startup healing
- periodic repair scans

## Projection Strategy

Use stable presets where available.

Rule:
- if table has a stable preset, auto-refresh projection
- if no preset exists, sync canonical only and mark `projection_status = skipped`

This keeps canonical replication authoritative while not blocking on projection coverage gaps.

Projection must remain a separate concern from canonical correctness:
- canonical sync success + projection failure = `partial_success`
- canonical sync failure = `failed`

## Failure And Retry Strategy

### Retry classes

Retryable:
- tunnel not healthy
- cloud DB unavailable
- transient SSH/process failures
- projection refresh runtime failure
- temporary lock/contention when claiming a task

Non-retryable without code/data fix:
- invalid table naming
- unsupported preset mapping contract
- permanent configuration missing (`CLOUD_DATABASE_URL`, SSH key path, known hosts)
- canonical payload contract mismatch

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

Do not create a second tunnel implementation.

Reuse one operational tunnel model:
- one reusable background local tunnel
- health/status probe before each task
- restart once if unhealthy

Operational rules:
- auto sync must run only on hosts with non-interactive SSH key access
- password-interactive tunnel mode is not acceptable for unattended automation
- new automation code must not introduce `StrictHostKeyChecking=no` in production runtime paths

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

## Observability

The first version must be observable enough for unattended operation.

Minimum signals:
- queue depth by status
- oldest pending age
- last successful sync time by source table
- last error per task
- retry count
- checkpoint high-water mark
- worker heartbeat
- tunnel health

Minimum operator actions:
- trigger one table
- retry one task
- cancel one stuck task
- reset or repair one checkpoint
- run dry-run enumeration

## Security And Configuration

The implementation touches:
- SSH credentials
- remote database access
- task metadata with operational errors
- SQL execution paths

So the production implementation should be reviewed under the repository's `security-review` workflow before merge.

Required config should be explicit and validated at startup:
- `DATABASE_URL`
- `CLOUD_DATABASE_URL`
- SSH key path
- known-hosts path or equivalent host verification config
- worker enable/disable flag
- cloud sync poll interval

Sensitive values must not be logged.

## Runtime Flow

The intended v1 runtime flow is:

1. local ingestion writes to `b_class`
2. local ingestion commits successfully
3. `DataIngestedEvent` is created with source-table routing metadata
4. listener creates or coalesces a `cloud_b_class_sync_tasks` row
5. dedicated worker polls runnable tasks
6. worker claims one task with lease semantics
7. worker ensures tunnel and cloud DB readiness
8. worker runs canonical `sync_table(source_table_name)` using checkpointed batches
9. worker optionally refreshes projection
10. worker updates task/run/checkpoint state
11. health/admin APIs expose the result

## Rollout Plan

### Phase 0: Land the manual sync core first

Before automation, land the prerequisite manual canonical sync core from:
- `docs/superpowers/specs/2026-03-18-local-cloud-b-class-canonical-sync-design.md`
- `docs/superpowers/plans/2026-03-18-local-cloud-b-class-canonical-sync.md`

Required deliverables:
- sync service
- checkpoint/run tables
- tunnel tooling
- projection tooling or explicit projection stub

Without this, auto sync would be forced to invent a new execution core and drift from the canonical-sync design.

### Phase 1: Add durable task control plane

- add `cloud_b_class_sync_tasks`
- add task dedupe/coalescing rules
- add admin-visible task states

Success criteria:
- every successful local ingestion can create or coalesce a cloud sync task
- cloud sync queue is queryable independently of ingestion

### Phase 2: Re-enable event path as enqueue-only

- extend `DataIngestedEvent`
- implement enqueue-only listener behavior
- verify no remote write occurs in ingestion request flow

Success criteria:
- `DATA_INGESTED` produces durable queue work
- ingestion latency is not coupled to tunnel/cloud health

### Phase 3: Add dedicated worker

- add worker service
- add claim / lease / heartbeat behavior
- add scheduler-driven retry/poll loop in the worker role

Success criteria:
- pending tasks are automatically claimed and completed
- failures retry with backoff
- stale tasks can be reclaimed safely

### Phase 4: Add projection automation and admin APIs

- preset resolver
- projection refresh after canonical success
- partial-success semantics
- admin trigger/retry/health endpoints

### Phase 5: Soak and hardening

- long-running tunnel observation
- restart recovery
- duplicate-event coalescing verification
- dry-run and repair procedures
- security review

## Why This Design Avoids Duplicate Work

This design intentionally reuses:
- existing `DATA_INGESTED` event emission
- existing `PlatformTableManager`
- existing scheduler pattern
- existing queue/state-machine ideas
- existing manual canonical sync design assets

It deliberately avoids creating:
- a second event framework
- a second scheduler framework
- a second table-name resolver
- a second cloud sync execution core
- a direct cloud-sync call path embedded into Playwright collection execution

## Recommendation

Implement the first version as:

1. land the manual canonical sync core
2. extend `DATA_INGESTED`
3. enqueue source-table sync tasks durably
4. run a single-threaded dedicated worker with lease + retry
5. auto-refresh projection only when a stable preset exists
6. expose admin and health visibility before enabling unattended execution

That is the smallest implementation that is operationally safe, aligned with the repository's current architecture, and honest about the current mainline gap between design and code.
