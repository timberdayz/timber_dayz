# Data Sync Schema Drift Recovery

## Goal

Provide a repeatable recovery path when data sync delete or quarantine flows fail because the running PostgreSQL schema is missing critical columns such as `core.data_quarantine.catalog_file_id`.

## Symptoms

- Data sync file delete returns:
  - `删除文件失败：数据库结构未完成迁移，请执行 Alembic 迁移`
- Backend logs include:
  - `UndefinedColumnError`
  - `no such column`
  - `core.data_quarantine.catalog_file_id`

## Root Cause Pattern

The application code, ORM definitions, and migrations already expect the following critical columns to exist:

- `core.data_quarantine.catalog_file_id`
- `core.staging_orders.file_id`
- `core.staging_product_metrics.file_id`
- `core.staging_inventory.file_id`

If the target database was not fully migrated, runtime delete and quarantine flows can fail before any business cleanup happens.

## Recovery Checklist

1. Run the health check.
2. Confirm which critical columns are missing.
3. Run Alembic migrations.
4. Restart the backend.
5. Re-run delete-impact.
6. Re-run delete.

## Step 1: Run the Health Check

From the project root:

```powershell
python scripts\check_database_health.py
```

Expected:

- The script should report whether `core.data_quarantine.catalog_file_id` or any staging `file_id` columns are missing.

If the script reports missing columns, continue to Step 2 immediately.

## Step 2: Confirm the Drift Scope

Check whether the failure is limited to the known data-sync critical columns or broader schema drift.

Key indicators:

- Missing `core.data_quarantine.catalog_file_id`
- Missing `core.staging_orders.file_id`
- Missing `core.staging_product_metrics.file_id`
- Missing `core.staging_inventory.file_id`
- Alembic revision not up to date

If startup now fails with `Schema missing critical columns`, that is expected behavior after the guardrail changes. Fix the database first, then restart.

## Step 3: Apply Alembic Migrations

Run:

```powershell
python -m alembic upgrade heads
```

If you need a fresh-database rehearsal before touching a real environment, run:

```powershell
python scripts\validate_migrations_fresh_db.py
```

The rehearsal now validates both:

- `alembic upgrade heads` completes
- Data-sync critical columns exist after migration

## Step 4: Restart the Backend

Restart the backend process after migration so startup verification runs against the updated schema.

Expected startup outcome:

- No `Schema incompleteness`
- No `Schema missing critical columns`
- Normal startup completion

## Step 5: Verify Delete Impact

Call the delete-impact endpoint again from the UI or API:

```text
GET /api/data-sync/files/{file_id}/delete-impact
```

Expected:

- HTTP 200
- `success: true`
- impact payload returns counts instead of a schema error

## Step 6: Verify Delete Execution

Retry delete from the file list or API:

```text
DELETE /api/data-sync/files/{file_id}
```

Expected:

- HTTP 200
- file record removed
- associated quarantine/staging/fact cleanup proceeds normally

## Post-Recovery Verification

Run the focused regression suite:

```powershell
pytest backend\tests\test_data_sync_schema_guardrails.py backend\tests\test_verify_schema_completeness_sync_columns.py backend\tests\test_check_database_health_sync_contract.py backend\tests\test_data_sync_file_delete_api.py backend\tests\test_catalog_file_delete_service.py -q
```

Expected:

- All tests pass

## Operational Notes

- Do not add per-request schema inspection to data-sync hot paths.
- Keep schema validation in deploy-time checks, startup checks, and explicit health scripts.
- Treat `create_all()` as a development convenience, not a production migration strategy.
- If a new data-sync table becomes critical to delete/sync correctness, add it to:
  - `backend.models.database.DATA_SYNC_CRITICAL_COLUMNS`
  - `scripts/check_database_health.py`
  - migration rehearsal coverage
