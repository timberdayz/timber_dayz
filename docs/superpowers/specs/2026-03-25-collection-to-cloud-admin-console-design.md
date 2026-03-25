# Collection-to-Cloud Admin Console Design

**Date:** 2026-03-25  
**Last Updated:** 2026-03-25

## Goal

Design a production-ready, admin-only management surface for collection-to-cloud auto sync, and align the backend runtime and API contracts needed to support it.

The target outcome is:

- automatic local-to-cloud B-class sync runs from a dedicated worker role after local ingestion succeeds
- admins can monitor worker health, queue state, checkpoint state, and projection refresh state from one page
- admins can execute controlled operations such as manual trigger, retry, dry-run, and checkpoint repair without touching the database directly

## Non-Goals

Out of scope for V1:

- non-admin access
- bidirectional sync
- row-level real-time CDC
- full browser-based infrastructure control such as editing SSH config or arbitrary environment variables
- exposing raw credential details in the UI
- making the generic data-sync pages the primary UX for cloud sync operations

## Current Reality

The repository already contains the first working pieces of the cloud sync stack:

- manual canonical sync core
- cloud sync checkpoint / run / task tables
- enqueue-on-`DATA_INGESTED` behavior
- dispatch service
- worker
- `/api/cloud-sync/*` router

What is still incomplete:

- runtime wiring into the main application lifecycle
- dedicated worker-role activation and health reporting
- tunnel/cloud database health checks
- table-level admin visibility
- controlled admin actions beyond the current minimal endpoints
- production-hardening around configuration validation and recovery flows

This means the system is beyond the design-only stage, but still below the threshold of a safe, observable, operator-friendly production feature.

## User And Permission Model

V1 is **admin-only**.

Reason:

- sync operations expose sensitive table names, failure details, and replication state
- checkpoint repair and retry actions can directly affect cloud data correctness
- this page is an operations console, not a general business page

The route, menu item, and every backend operation should require admin permission.

## Page Boundary

Add a **new standalone page**:

- route: `/cloud-sync`
- suggested title: `云端同步管理`
- menu group: `数据采集与管理`

Do not merge this into:

- `/data-sync/files`
- `/data-sync/tasks`
- `/data-sync/history`

Reason:

- file sync is file-centric
- cloud sync is table-centric
- cloud sync additionally depends on worker/tunnel/cloud-DB runtime state

The page should still visually align with the existing admin pages and reuse common page-shell patterns.

## Information Architecture

The page should be a **single admin console** with five zones, ordered from diagnosis to action.

### 1. Health Summary

Top-row cards:

- Worker status
- Tunnel status
- Cloud DB status
- Pending task count
- Running task count
- Oldest pending age
- Last successful sync time

Behavior:

- card click applies filters to the task/table sections below
- health cards are read-first, not action-first

### 2. Table Sync State

Primary operational table. One row per `fact_*` source table.

Fields:

- `source_table_name`
- `platform_code`
- `data_domain`
- `sub_domain`
- latest checkpoint high-water mark
- last successful sync time
- latest task status
- projection preset
- projection status
- latest error summary

Actions:

- trigger sync
- dry-run
- repair checkpoint
- refresh projection
- open task history drawer for this table

This section is the main decision surface for admins.

### 3. Task Queue

Secondary detail table. One row per `cloud_b_class_sync_task`.

Fields:

- `job_id`
- `source_table_name`
- `trigger_source`
- `status`
- `attempt_count`
- `source_file_id`
- `claimed_by`
- `lease_expires_at`
- `heartbeat_at`
- `last_attempt_started_at`
- `last_attempt_finished_at`
- `projection_status`
- `last_error`

Actions:

- view detail
- retry
- cancel stuck task

### 4. Operations Panel

Controlled action panel for admins.

Actions included in V1:

- manual trigger by table
- dry-run by table
- retry failed task
- repair checkpoint for one table
- refresh projection for one table

Optional parameters:

- `batch_size`
- `skip_projection`
- `projection_preset` override only if preset support is already explicit in backend contract

V1 should **not** support direct free-form SQL, credential editing, or unrestricted task mutation.

### 5. Event Timeline

Recent event feed showing:

- `DATA_INGESTED` queued task
- worker claim
- sync completion
- sync failure
- projection refresh result
- admin manual operations

This does not require a new dedicated event store in V1 if the repository can derive enough information from task transitions and existing ops logs.

## UX Direction

This page should feel like an **operations console**, not a business dashboard.

Recommended tone:

- dense but readable
- status-driven
- strong visual distinction between healthy / degraded / failed
- minimal decorative motion

Recommended interaction style:

- summary cards at top
- table-first workflow
- right-side drawers or detail modals for per-task/per-table inspection
- destructive or recovery actions always confirm before execution

## Backend Contract Changes

The current router is not sufficient for the page.

### 1. Health Endpoint Must Become Real

`GET /api/cloud-sync/health`

Current problem:

- tunnel status is placeholder
- cloud DB reachability is not explicit
- queue summary is minimal

Required response shape:

```json
{
  "worker": {
    "status": "running",
    "worker_id": "cloud-sync-worker-1",
    "last_heartbeat_at": "..."
  },
  "tunnel": {
    "status": "healthy",
    "last_checked_at": "...",
    "error": null
  },
  "cloud_db": {
    "status": "reachable",
    "last_checked_at": "...",
    "error": null
  },
  "queue": {
    "pending": 0,
    "running": 0,
    "retry_waiting": 0,
    "failed": 0,
    "partial_success": 0,
    "completed_recent_24h": 0,
    "oldest_pending_age_seconds": null
  }
}
```

### 2. Add Table-Centric State Endpoint

New endpoint:

- `GET /api/cloud-sync/tables`

Purpose:

- aggregate checkpoint state
- latest task state
- projection state

Response per row:

- `source_table_name`
- `platform_code`
- `data_domain`
- `sub_domain`
- `checkpoint`
- `latest_task`
- `projection`
- `last_success_at`

This is the primary data source for the page’s main table.

### 3. Expand Task Endpoints

Current endpoints should expose richer fields:

- `GET /api/cloud-sync/tasks`
- `GET /api/cloud-sync/tasks/{job_id}`

Required additions:

- `attempt_count`
- `trigger_source`
- `source_file_id`
- `claimed_by`
- `lease_expires_at`
- `heartbeat_at`
- `last_attempt_started_at`
- `last_attempt_finished_at`
- `projection_status`
- `last_error`
- `error_code`
- `created_at`
- `updated_at`

Filtering support should be added for:

- `status`
- `source_table_name`
- `trigger_source`
- `limit`

### 4. Controlled Admin Action Endpoints

Keep:

- `POST /api/cloud-sync/tasks/trigger`
- `POST /api/cloud-sync/tasks/{job_id}/retry`

Add:

- `POST /api/cloud-sync/tables/{table_name}/dry-run`
- `POST /api/cloud-sync/tables/{table_name}/repair-checkpoint`
- `POST /api/cloud-sync/tables/{table_name}/refresh-projection`
- `POST /api/cloud-sync/tasks/{job_id}/cancel`

These endpoints must stay narrowly scoped and admin-only.

## Runtime Wiring Changes

### Dedicated Worker Role

The repository should run cloud sync through a dedicated worker role.

Rules:

- API role:
  - persists tasks
  - exposes admin APIs
  - does not claim queue work
- cloud sync worker role:
  - runs the polling loop
  - claims tasks
  - performs sync and optional projection refresh

### Application Startup

`backend/main.py` should:

- validate cloud sync configuration early
- conditionally create `cloud_sync_runtime`
- start it only in the intended deployment role
- stop it cleanly on shutdown

### Required Config

At minimum:

- `CLOUD_SYNC_WORKER_ENABLED`
- `CLOUD_SYNC_WORKER_POLL_INTERVAL_SECONDS`
- `CLOUD_DATABASE_URL`
- SSH key path
- known-hosts path
- deployment role

If required config is missing while the worker is enabled:

- startup should fail fast with explicit error messaging

## State Machine Expectations

### Task status

Use and enforce:

- `pending`
- `running`
- `retry_waiting`
- `completed`
- `partial_success`
- `failed`
- `cancelled`

### Projection status

Use and enforce:

- `pending`
- `completed`
- `failed`
- `skipped`

### Recovery rules

- failed canonical sync must not advance checkpoint
- projection failure after canonical success becomes `partial_success`
- stale leases must be reclaimable
- retry backoff must be deterministic and visible

## Security Model

This feature is sensitive because it touches:

- SSH connectivity
- cloud database access
- replication state
- repair actions

Therefore:

- all endpoints must require admin auth
- no secrets may be returned to the frontend
- error detail should be operator-usable but still redact credentials
- host verification must remain enabled in production paths

## Implementation Order

### Phase 1: Runtime Wiring

- connect `CloudBClassAutoSyncRuntime` into app lifecycle
- add config validation
- establish admin-visible runtime state

### Phase 2: Contract Completion

- complete `health`
- add `tables`
- enrich `tasks`
- add controlled action endpoints

### Phase 3: Frontend Page

- create `/cloud-sync`
- add menu entry
- implement health cards, table state, queue, operations panel, and event timeline

### Phase 4: Stability And Security

- stale-lease recovery
- retry validation
- tunnel/cloud DB health probes
- security review

### Phase 5: Soak And Docs

- restart recovery verification
- duplicate-event coalescing verification
- long-running stability checks
- operator documentation

## Testing Strategy

### Backend

Add or extend tests for:

- runtime activation conditions
- health endpoint contract
- table-state endpoint
- retry / cancel / repair behavior
- stale lease reclaim

### Frontend

Add tests for:

- admin-only route visibility
- correct API calls for list/health/actions
- optimistic refresh behavior after retry/trigger
- status rendering for failed / partial / retry_waiting

### End-to-End

Minimum validation before rollout:

- ingestion emits event
- task row is created
- worker claims task
- sync completes
- health page reflects queue movement
- admin action retry works

## Recommendation

Proceed as a **single cohesive admin console initiative**, not as a page-only effort.

The page is valuable only if the backend runtime, health model, and admin operations are all promoted to first-class production contracts. The correct delivery shape is:

1. runtime wiring
2. contract completion
3. admin page
4. security and soak hardening

That is the smallest path that produces a tool admins can actually trust in production.
