# Production Deploy And Migration Report

**Date:** 2026-03-28
**Target Host:** `134.175.222.171`
**OS:** Ubuntu Server 22.04 LTS 64bit
**Checked By:** Codex via SSH (`deploy`)

## Scope

This report covers:
- production code deployment state
- production database migration state
- task center schema alignment
- read-only smoke validation for task center APIs

## Summary

Production is now running the latest task-center migration chain.

Confirmed:
- backend container reports Alembic `current = head = 20260328_task_center_merge`
- `verify_schema_completeness()` returns `all_tables_exist=true`
- task center tables exist in production
- production task-center read APIs respond correctly for list, empty subject lookup, and 404 detail/log cases

Important note:
- task center tables were created in the `public` schema on production:
  - `public.task_center_tasks`
  - `public.task_center_logs`
  - `public.task_center_links`
- this is the actual production result and is currently functional

## Environment Checks

Verified from host:
- deploy root exists at `/opt/xihong_erp`
- running containers are healthy:
  - `xihong_erp_backend`
  - `xihong_erp_frontend`
  - `xihong_erp_postgres`
  - `xihong_erp_redis`
  - `xihong_erp_celery_worker`
  - `xihong_erp_celery_beat`
  - `xihong_erp_nginx`

Relevant backend env values (masked):
- `ENVIRONMENT=production`
- `APP_ENV=production`
- `DATABASE_URL=postgresql://erp_user:***@postgres:5432/xihong_erp`
- `ALLOWED_HOSTS=localhost,127.0.0.1,backend,134.175.222.171,www.xihong.site,xihong.site,backend`
- `VITE_API_BASE_URL=/api`

## Migration Verification

### Alembic status

Inside `xihong_erp_backend`:
- `alembic heads` -> `20260328_task_center_merge (head)`
- `alembic current` -> `20260328_task_center_merge (head) (mergepoint)`

### Application schema verification

Inside `xihong_erp_backend`:

```json
{
  "all_tables_exist": true,
  "missing_tables": [],
  "migration_status": "up_to_date",
  "current_revision": "20260328_task_center_merge",
  "head_revision": "20260328_task_center_merge"
}
```

### Production DB alignment probes

Confirmed:
- `core.account_aliases=true`
- `public.account_aliases=false`
- `catalog_files.source_default='data/raw'::character varying`

Confirmed in `a_class.sales_targets`:
- `target_profit_amount`
- `achieved_profit_amount`
- `target_quantity`
- `achieved_quantity`

## Backup

Attempt to write backup under `/opt/xihong_erp/backups/` with `ubuntu` failed due to permissions.

Successful pre-check backup was created by writing to `/tmp`:
- `/tmp/pre_migration_task_center_20260328_164257.dump`

Recommendation:
- if you want operationally consistent backup retention, align remote writable backup ownership under `/opt/xihong_erp/backups/`

## Task Center Table Check

Observed on production:
- `public.task_center_tasks`
- `public.task_center_logs`
- `public.task_center_links`

Column-level probe for the three tables succeeded.

Current row counts at smoke-test time:
- `task_center_tasks=0`
- `task_center_logs=0`
- `task_center_links=0`

This means:
- schema is present
- no production workload has yet written task-center rows, or current traffic has not exercised those paths yet

## Task Center Smoke Test

Read-only API smoke was executed from the production host against `http://127.0.0.1`.

### 1. List endpoint

Request:
- `GET /api/task-center/tasks?page=1&page_size=5`

Result:
- HTTP `200`
- payload shape present
- `items_len=0`

### 2. Subject lookup endpoint

Request:
- `GET /api/task-center/tasks/by-subject?subject_type=catalog_file&subject_id=1`

Result:
- HTTP `200`
- empty list returned correctly

### 3. Missing detail contract

Request:
- `GET /api/task-center/tasks/__missing_task__`

Result:
- HTTP `404`
- structured error payload returned

### 4. Missing logs contract

Request:
- `GET /api/task-center/tasks/__missing_task__/logs`

Result:
- HTTP `404`
- structured error payload returned

## Operational Findings

### 1. Production repository working tree is not a reliable release audit source

`git -C /opt/xihong_erp status --short` shows a very large dirty working tree with many tracked and untracked files.

This means:
- the checked-out repository on host should not be used as the source of truth for release verification
- container runtime checks and Alembic checks are more trustworthy than host git cleanliness right now

### 2. Task center schema location differs from earlier local expectation

Earlier local rehearsal created the task center tables under `core`.
Production currently has them under `public`.

This is not blocking because:
- the migration is applied
- the runtime is healthy
- smoke tests pass

But it should be treated as a follow-up design/consistency question.

## Recommendation

Production deployment and migration for the task-center work are complete enough to proceed.

Recommended follow-up:
1. Trigger one real task-center-producing workflow in production
2. Re-check `task_center_tasks`, `task_center_logs`, and `task_center_links` counts
3. Decide whether `public` vs `core` is the intended long-term schema for task center tables
4. Clean up host-side repository deployment drift if host git state is meant to remain an operational audit tool
