# Persistent Task Center Design

**Date:** 2026-03-27
**Last Updated:** 2026-03-27

## Goal

Refactor the long-task tracking model around `backend/services/progress_tracker.py` into a durable task center that can:
- unify state storage for data-sync, collection, and cloud sync long-running work
- survive service restarts
- support lookup by task ID, reverse lookup by file or business object, paginated task lists, and durable error logs
- keep current frontend task surfaces working during a gradual migration

## Non-Goals

Out of scope for the first implementation:
- true browser-session resume for collection tasks after process restart
- removing all legacy task tables in the same release
- replacing domain-specific checkpoint tables such as `cloud_b_class_sync_checkpoints`
- moving task storage to a new ORM base or a separate persistence stack
- redesigning existing frontend pages before the backend compatibility layer exists

## Current Reality Check

The repository already contains multiple task-tracking systems with overlapping scope:

### 1. In-memory field-mapping progress

`backend/services/progress_tracker.py` stores task progress in process memory only.

Characteristics:
- survives only for the lifetime of one API process
- loses all state on restart
- powers legacy field-mapping progress APIs
- is still used by the legacy auto-ingest compatibility wrapper

### 2. Data-sync progress persistence

`backend/services/sync_progress_tracker.py` writes progress rows to `sync_progress_tasks`.

Characteristics:
- durable across restarts
- used by `/data-sync/*`, asyncio fallback workers, and Celery workers
- optimized for counters and lightweight history
- not expressive enough for a generic task center

### 3. Collection task subsystem

`CollectionTask` and `CollectionTaskLog` provide a durable collection-specific task model.

Characteristics:
- supports queue/running/paused/partial_success/cancelled/interrupted
- supports verification screenshot, verification resume, retry lineage, and per-task logs
- execution still runs via `asyncio.create_task()` in the API process
- task records survive restart, but execution does not resume from runtime state

### 4. Cloud sync control plane

`CloudBClassSyncTask` and `CloudBClassSyncCheckpoint` already model a durable worker queue.

Characteristics:
- supports dedupe, retry wait, claim, lease expiry, heartbeat, and error code
- already behaves like a resilient background-worker queue
- currently scoped only to B-class cloud sync

### 5. Celery execution state

Data-sync also exposes Celery task IDs and Celery task-state endpoints.

Characteristics:
- useful as execution-layer visibility
- not the business task source of truth
- currently has no durable mapping from `celery_task_id` back to the business task record

## Architecture Problems

### 1. Split-brain task authority

There is no single task source of truth. The system currently spreads task state across:
- in-memory `ProgressTracker`
- `sync_progress_tasks`
- `collection_tasks`
- `cloud_b_class_sync_tasks`
- Celery backend state

This makes list views, restart recovery, cancellation, retry, and historical analysis inconsistent.

### 2. Data-sync already has two progress models in the same runtime path

`DataSyncService` still imports the in-memory `progress_tracker`, while active data-sync APIs and workers use `SyncProgressTracker`.

This indicates an incomplete migration and makes future refactoring ambiguous.

### 3. Reverse lookup is fragmented

Today, reverse lookup depends on different storage anchors:
- `CatalogFile.id`
- `staging_* .ingest_task_id`
- collection task account/config metadata
- cloud sync `source_file_id` and `source_table_name`

There is no indexed, generic task-subject relation table.

### 4. Error logging is inconsistent

Different subsystems store errors differently:
- collection: append-only row logs
- sync progress: JSON arrays
- cloud sync: single `last_error`
- legacy progress: process-local error list

This blocks a consistent task-detail or incident view.

### 5. Status vocabularies diverge

Examples:
- collection: `pending`, `queued`, `running`, `paused`, `completed`, `partial_success`, `failed`, `cancelled`, `interrupted`
- sync progress: `pending`, `processing`, `completed`, `failed`
- cloud sync: `pending`, `running`, `retry_waiting`, `partial_success`, `completed`, `failed`, `cancelled`

Frontend code already normalizes statuses because the backend does not.

### 6. Collection queue semantics exist in code but are not the real execution path

`TaskService` and `TaskQueueService` define queue/state-transition logic, but current manual and scheduled collection flows still start work via `asyncio.create_task()` directly.

That means:
- queueing semantics are partial
- restart handling is mostly record repair, not runtime recovery
- collection scheduling and execution state are not cleanly separated

### 7. Celery retry and cancellation are structurally incomplete

Current data-sync APIs can:
- submit work
- expose `celery_task_id`
- inspect Celery state
- revoke Celery tasks

But they cannot reliably reconstruct the original task request because there is no durable business-task to runner-task mapping model.

### 8. Compatibility constraints are real

Active frontend surfaces depend on:
- legacy field-mapping progress endpoints
- data-sync progress and task history endpoints
- collection task/detail/log/resume endpoints
- cloud sync admin task views

Any redesign must preserve these response shapes during migration.

## Requirements

### Functional requirements

The new task center must:
1. store long-task state durably
2. support task creation and status updates from multiple task families
3. support lookup by `task_id`
4. support reverse lookup by file, table, account, and future business subjects
5. support list pagination, filtering, and history queries
6. support durable append-only error and audit logs
7. preserve cancellation and retry metadata
8. preserve execution-runner visibility such as Celery IDs where relevant

### Reliability requirements

The new task center must:
- survive service restart without losing task records
- support recovery-friendly states such as `interrupted` or `retry_waiting`
- support worker claim/lease semantics where the runtime needs them
- avoid using request-process memory as the reliability boundary

### Migration requirements

The migration must:
- keep current frontend task entrypoints working
- prefer adapters and projections over a big-bang schema cutover
- allow subsystem-by-subsystem migration
- avoid coupling collection/browser runtime redesign to the first storage migration

## Key Decisions

### 1. Add a new generic task center model instead of overloading an existing table

Do not overload:
- `SyncProgressTask`
- `CollectionTask`
- `CloudBClassSyncTask`

Each of those tables is already biased toward one runtime shape. A generic task center needs a neutral storage model.

### 2. Keep domain-specific checkpoint tables separate

Tables such as:
- `cloud_b_class_sync_checkpoints`
- `cloud_b_class_sync_runs`

are execution/checkpoint tables, not generic task-center records. They should remain specialized even after task-center rollout.

### 3. Use the task center as the common control-plane SSOT

The long-term target is:
- one common task-center control plane
- optional domain-specific execution detail tables behind it

This allows one query model for task pages, audit, filtering, and reverse lookup while still keeping specialized runtime data where needed.

### 4. Introduce runner mapping explicitly

A generic task must be able to store:
- runner kind
- external runner ID

Examples:
- Celery task ID
- collection in-process executor identity
- cloud sync worker claim owner

This makes cancel/retry/diagnostics traceable.

### 5. Introduce generic task-subject links

Do not try to infer reverse lookup only from family-specific tables.

Instead, add explicit task-to-subject link rows for:
- catalog file
- source table
- collection config
- account
- shop
- future business objects

## Recommended Architecture

## New Tables

### 1. `task_center_tasks`

Purpose:
- common durable task record for all long-task families
- canonical place for lifecycle, progress, routing, and runner metadata

Suggested fields:
- `id`
- `task_id`
- `task_family` (`data_sync`, `collection`, `cloud_sync`, `legacy_field_mapping`)
- `task_type`
- `status`
- `trigger_source`
- `priority`
- `runner_kind` (`celery`, `asyncio`, `collection_browser`, `cloud_sync_worker`)
- `external_runner_id`
- `parent_task_id`
- `attempt_count`
- `next_retry_at`
- `claimed_by`
- `lease_expires_at`
- `heartbeat_at`
- `platform_code`
- `account_id`
- `source_file_id`
- `source_table_name`
- `current_step`
- `current_item`
- `total_items`
- `processed_items`
- `success_items`
- `failed_items`
- `skipped_items`
- `total_rows`
- `processed_rows`
- `valid_rows`
- `error_rows`
- `quarantined_rows`
- `progress_percent`
- `error_summary`
- `details_json`
- `created_at`
- `started_at`
- `updated_at`
- `finished_at`

Suggested status vocabulary:
- `pending`
- `queued`
- `running`
- `paused`
- `retry_waiting`
- `partial_success`
- `completed`
- `failed`
- `cancelled`
- `interrupted`

### 2. `task_center_logs`

Purpose:
- append-only operational log stream
- durable error history
- backend-friendly task timeline

Suggested fields:
- `id`
- `task_pk`
- `level`
- `event_type` (`state_change`, `progress`, `warning`, `error`, `verification`, `retry`)
- `message`
- `details_json`
- `created_at`

This becomes the generic equivalent of `CollectionTaskLog`.

### 3. `task_center_links`

Purpose:
- indexed reverse lookup by related object
- task-to-subject joins without parsing arbitrary JSON

Suggested fields:
- `id`
- `task_pk`
- `subject_type` (`catalog_file`, `source_table`, `collection_config`, `account`, `shop`, `business_object`)
- `subject_id`
- `subject_key`
- `details_json`
- `created_at`

Recommended indexes:
- `(subject_type, subject_id)`
- `(subject_type, subject_key)`
- `(task_pk, subject_type)`

## Service Layer

Add a new service layer:
- `backend/services/task_center_service.py`
- optionally `backend/services/task_center_repository.py`
- optionally `backend/services/task_center_mappers.py`

Responsibilities:
- create task rows
- update lifecycle state
- update progress counters
- attach runner metadata
- append log events
- attach subject links
- list and paginate tasks
- fetch task detail with latest summary
- query logs and reverse-linked tasks

## Compatibility Adapters

### 1. Data-sync adapter

Refactor `SyncProgressTracker` into a compatibility adapter over the new task center.

Behavior:
- keep its public methods for current callers
- translate `processing` to `running`
- keep existing response shape for `/data-sync/progress/{task_id}`
- persist `celery_task_id` into `external_runner_id`

### 2. Legacy progress adapter

Refactor `ProgressTracker` into a task-center-backed compatibility wrapper.

Behavior:
- same async method names as today
- same response shape for `/field-mapping/progress/*`
- no in-memory-only state in production path

### 3. Collection adapter

Collection should migrate in two stages:

Stage A:
- keep `CollectionTask` and `CollectionTaskLog` as execution-facing compatibility tables
- dual-write high-level lifecycle and log events into task center
- support new cross-family history without breaking current collection pages

Stage B:
- make task center canonical for collection query/read paths
- keep collection-specific fields either in `details_json` or in a temporary projection until old API surfaces are retired

### 4. Cloud sync adapter

Cloud sync should also migrate in two stages:

Stage A:
- keep `CloudBClassSyncTask` as the execution queue because it already encodes claim/lease semantics
- mirror queue lifecycle into task center for unified read/query

Stage B:
- decide whether `CloudBClassSyncTask` remains an execution table behind task center or is fully folded into task center

The first delivery should prefer mirroring over immediate queue replacement.

## Reverse Lookup Model

Reverse lookup should use explicit links instead of family-specific heuristics.

Examples:
- data-sync task -> `catalog_file`, `source_table`
- collection task -> `collection_config`, `account`, `platform`
- cloud sync task -> `source_table`, `catalog_file` when available

The existing `staging_* .ingest_task_id` fields remain useful as migration bridges and audit anchors, but they should not be the only lookup path.

## Family-Specific Notes

### Data-sync

Data-sync is the best first migration target because:
- it already has a durable `task_id`
- it already has dedicated task history/progress pages
- it already uses asynchronous background execution
- it most obviously suffers from split task metadata between business task and Celery task

### Collection

Collection can only guarantee record recovery in the first migration phase.

V1 restart semantics should be:
- running in-process task is marked `interrupted`
- user can inspect logs and retry
- paused verification task remains visible

Do not promise in-browser resume after process crash until collection execution is moved to a durable worker architecture.

### Cloud sync

Cloud sync already contains the strongest worker semantics in the repository. The task center should adopt its claim/lease/heartbeat ideas rather than forcing cloud sync down to the simpler sync-progress model.

## Pagination and Query Contract

The task center should support:
- family filter
- status filter
- platform filter
- account filter
- subject filter
- created-time range
- page/page_size
- descending default sort on `created_at`

This becomes the common query contract behind:
- `/data-sync/tasks`
- collection history/list
- cloud sync task list
- future `/task-center/tasks`

## Migration Strategy

### Phase 1: Introduce task center without cutting traffic

- add new tables
- add service/repository
- no old API changes yet

### Phase 2: Migrate data-sync

- make `SyncProgressTracker` a task-center adapter
- store `external_runner_id`
- keep `/data-sync/progress` and `/data-sync/tasks` responses compatible

### Phase 3: Replace in-memory legacy progress

- make `ProgressTracker` task-center-backed
- move `/field-mapping/progress/*` off process memory

### Phase 4: Add reverse-link support

- write links for file/table/account subjects
- add query helpers and pagination

### Phase 5: Add collection dual-write

- mirror collection lifecycle and logs to task center
- keep current collection APIs unchanged

### Phase 6: Add cloud-sync mirror or fold-in

- project cloud sync queue rows into task center
- keep checkpoint tables specialized

### Phase 7: Add unified task-center API

- provide a single read surface for cross-family operations
- keep old APIs as compatibility wrappers until frontend migration is complete

### Phase 8: Retire obsolete storage

- remove in-memory `ProgressTracker`
- evaluate retirement of `SyncProgressTask`
- decide whether collection/cloud execution tables remain as specialized projections

## Risks

### 1. Dual-write drift

During migration, old and new rows can diverge if writes are not centralized in one adapter/service layer.

Mitigation:
- one adapter per family
- no direct per-router writes into both models
- parity tests on read outputs

### 2. Overpromising collection recovery

Persisting task state is not the same as resuming browser runtime state.

Mitigation:
- explicitly document `interrupted -> retry` semantics for collection V1

### 3. Cloud sync queue regression

Replacing cloud sync queue semantics too early could break claim/lease safety.

Mitigation:
- mirror first
- replace queue ownership only after parity is proven

### 4. Unindexed reverse lookup

If subject lookup is left in JSON only, list performance will degrade quickly.

Mitigation:
- use explicit `task_center_links` indexes from the first schema version

### 5. Compatibility breakage in frontend polling

Current frontend pages expect family-specific fields and status names.

Mitigation:
- preserve old response shapes behind adapters
- add contract tests before changing backends

## Testing Strategy

### Contract tests

Add API contract tests for:
- `/field-mapping/progress/{task_id}`
- `/field-mapping/progress`
- `/data-sync/progress/{task_id}`
- `/data-sync/tasks`
- `/collection/tasks`
- `/collection/tasks/{task_id}/logs`
- `/api/cloud-sync/tasks`

### Repository/service tests

Add tests for:
- task creation
- progress updates
- log append
- subject linking
- pagination and filtering
- reverse lookup by file/table/account

### Recovery tests

Add tests for:
- data-sync task persists across process restart
- collection running task can be marked `interrupted`
- cloud sync claim/lease/retry state still behaves correctly when mirrored

### Runner mapping tests

Add tests for:
- `task_id -> celery_task_id` persistence
- cancellation path can find the runner from business task metadata
- retry path can reconstruct task submission metadata

### Frontend smoke tests

Re-run focused frontend/task-page smoke checks for:
- `DataSyncFiles.vue`
- `DataSyncTasks.vue`
- `CollectionTasks.vue`
- cloud sync dashboard/store flows

## Recommended Outcome

The recommended path is:
- introduce a new generic task center
- migrate data-sync first
- replace legacy in-memory progress second
- dual-write collection and cloud sync third
- only then decide which old task tables can be retired

This gives the repository one durable control-plane model without forcing a risky big-bang rewrite of every existing task family.
