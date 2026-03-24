# Cloud Sync Operation Notes

**Date:** 2026-03-24

## Current State

The repository now contains a first executable version of local-to-cloud B-class canonical sync:

- manual bootstrap:
  - `python scripts/migrate_cloud_sync_tables.py`
- manual sync:
  - `python scripts/sync_b_class_to_cloud.py --batch-size 100`
- manual dry-run:
  - `python scripts/sync_b_class_to_cloud.py --dry-run --batch-size 10`
- auto sync control-plane API:
  - `GET /api/cloud-sync/health`
  - `POST /api/cloud-sync/tasks/trigger`
  - `GET /api/cloud-sync/tasks`
  - `GET /api/cloud-sync/tasks/{job_id}`
  - `POST /api/cloud-sync/tasks/{job_id}/retry`

## Recommended First Verification

Use dry-run first:

```bash
python scripts/migrate_cloud_sync_tables.py
python scripts/sync_b_class_to_cloud.py --dry-run --batch-size 10
python scripts/verify_cloud_sync_local.py --verify-db xihong_erp_cloud_sync_verify --table fact_shopee_orders_monthly
```

Expected result:
- local checkpoint / run / task tables exist
- local `b_class` tables can be enumerated
- canonical payload extraction succeeds
- no cloud database write is attempted
- optional local isolated target verification can complete against `xihong_erp_cloud_sync_verify`

## Runtime Flags

Recommended env vars for the first automatic test:

```env
CLOUD_SYNC_WORKER_ENABLED=true
CLOUD_SYNC_DRY_RUN=true
CLOUD_SYNC_WORKER_POLL_INTERVAL_SECONDS=5
```

Required for real cloud writes:

```env
CLOUD_DATABASE_URL=postgresql://...
```

## Important Boundaries

- `CLOUD_SYNC_DRY_RUN=true` means:
  - no cloud writes
  - no cloud mirror DDL
  - local read + canonical contract verification only
- auto sync currently has:
  - durable task table
  - enqueue-only ingestion listener
  - worker/runtime skeleton
  - health and task APIs
- before production enablement, a dedicated security review is still required for:
  - SSH tunnel / credentials
  - cloud DB access
  - admin API exposure
