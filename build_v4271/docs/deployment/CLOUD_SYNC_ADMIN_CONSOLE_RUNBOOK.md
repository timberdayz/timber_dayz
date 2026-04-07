# Cloud Sync Admin Console Runbook

**Date:** 2026-03-26

## Scope

This runbook covers the admin-only collection-to-cloud operations console and the backend worker/runtime it manages.

It is intended for:
- local collection environments that own cloud sync execution
- admins who need to inspect queue state, retry failures, repair checkpoints, and verify worker health

It is not intended for:
- non-admin business users
- direct credential editing from the UI
- arbitrary SQL/database repair

## Runtime Model

Current runtime split:
- collection/local environment:
  - owns ingestion
  - can enqueue cloud sync tasks
  - can run the cloud sync worker
- cloud/dashboard environment:
  - should not run collection scheduling
  - should not claim cloud sync tasks unless explicitly designed to do so later

## Required Environment Variables

Minimum variables for enabling the worker:

```env
ENABLE_COLLECTION=true
DEPLOYMENT_ROLE=local
CLOUD_SYNC_WORKER_ENABLED=true
CLOUD_DATABASE_URL=postgresql://...
```

Recommended operational variables:

```env
CLOUD_SYNC_POLL_INTERVAL_SECONDS=5
CLOUD_SYNC_WORKER_ID=cloud-sync-worker-1
```

## Enablement Rules

The worker only starts when all of the following are true:
- `CLOUD_SYNC_WORKER_ENABLED=true`
- `ENABLE_COLLECTION=true`
- `DEPLOYMENT_ROLE != cloud`
- `CLOUD_DATABASE_URL` is present

If those conditions are not met:
- runtime health should remain `not_started` or `not_configured`
- queue inspection APIs can still be used

## Admin API Surface

Read APIs:
- `GET /api/cloud-sync/health`
- `GET /api/cloud-sync/tables`
- `GET /api/cloud-sync/tasks`
- `GET /api/cloud-sync/tasks/{job_id}`
- `GET /api/cloud-sync/events`

Controlled write APIs:
- `POST /api/cloud-sync/tasks/trigger`
- `POST /api/cloud-sync/tasks/{job_id}/retry`
- `POST /api/cloud-sync/tasks/{job_id}/cancel`
- `POST /api/cloud-sync/tables/{table_name}/dry-run`
- `POST /api/cloud-sync/tables/{table_name}/repair-checkpoint`
- `POST /api/cloud-sync/tables/{table_name}/refresh-projection`

All of the above are admin-only.

## Health Interpretation

Worker:
- `running`: runtime loop is active
- `stopped`: runtime has been cleanly stopped
- `not_started`: runtime exists but has not been started
- `not_configured`: worker prerequisites are missing
- `error`: worker loop crashed, check `last_error`

Queue:
- `pending`: waiting to be claimed
- `running`: claimed by worker
- `retry_waiting`: retryable failure waiting for next attempt
- `failed`: terminal failure requiring admin intervention
- `partial_success`: canonical sync succeeded but projection refresh failed

## Admin Workflow

1. Open `/cloud-sync`
2. Check:
   - worker status
   - tunnel status
   - cloud DB status
   - pending/running counts
3. Use table state as the primary surface:
   - identify the affected `fact_*` table
   - inspect checkpoint and latest task state
4. Use task queue for detail:
   - read last error
   - inspect attempts / claimed worker / timestamps
5. Execute a controlled action only when needed:
   - trigger sync
   - retry task
   - cancel stuck task
   - dry-run
   - repair checkpoint
   - refresh projection

## Recovery Guidance

If worker is `not_configured`:
- verify `CLOUD_SYNC_WORKER_ENABLED`
- verify `ENABLE_COLLECTION`
- verify `DEPLOYMENT_ROLE`
- verify `CLOUD_DATABASE_URL`

If tasks accumulate in `pending`:
- verify worker is actually running
- verify the process with `cloud_sync_runtime` is the intended role

If tasks are stuck in `running`:
- inspect `heartbeat_at` and `lease_expires_at`
- stale leases should be reclaimable by a healthy worker

If tasks end in `partial_success`:
- canonical cloud sync succeeded
- projection refresh did not
- inspect projection status and run projection refresh manually

If tasks end in `failed`:
- inspect `last_error`
- retry only after understanding whether the failure is environmental or data-related

## Security Notes

- Do not expose cloud DB credentials or SSH details to the browser
- Do not add non-admin access to this page without a separate review
- Before production rollout, run a dedicated security review for:
  - admin route exposure
  - runtime error detail leakage
  - SSH/tunnel handling
  - cloud DB access boundaries
