# Data Sync Schema Guardrails Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent data sync delete and quarantine flows from failing at runtime when database tables exist but critical columns are missing, while keeping schema checks out of the data-sync hot path.

**Architecture:** Treat schema correctness as a deploy-time and startup-time contract, not a per-request concern. Add explicit critical-column verification for the data-sync domain, surface actionable migration errors in runtime APIs, and extend health checks/tests so PostgreSQL drift is caught before production traffic reaches delete or sync endpoints.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL, pytest, Vue 3

---

### Task 1: Add regression tests for schema-drift failure handling

**Files:**
- Create: `backend/tests/test_data_sync_schema_guardrails.py`
- Modify: `backend/tests/test_data_sync_file_delete_api.py`
- Reference: `backend/services/catalog_file_delete_service.py`
- Reference: `backend/routers/data_sync.py`

- [ ] **Step 1: Write a failing test for delete-impact on a drifted schema**

```python
async def test_delete_impact_returns_migration_hint_when_quarantine_column_missing(...):
    response = await client.get(f"/api/data-sync/files/{file_id}/delete-impact")
    assert response.status_code == 500
    assert "执行 Alembic 迁移" in response.json()["error"]["detail"]
```

- [ ] **Step 2: Write a failing test for delete execution on a drifted schema**

```python
async def test_delete_file_returns_migration_hint_when_quarantine_column_missing(...):
    response = await client.delete(f"/api/data-sync/files/{file_id}")
    assert response.status_code == 500
    assert response.json()["message"] == "删除文件失败"
    assert "catalog_file_id" in response.json()["error"]["detail"]
```

- [ ] **Step 3: Run focused tests to verify RED**

Run:
```powershell
pytest backend\tests\test_data_sync_file_delete_api.py backend\tests\test_data_sync_schema_guardrails.py -q
```

Expected:
- FAIL because the runtime path still leaks raw schema drift instead of returning a clear migration hint.

### Task 2: Add explicit runtime schema-drift error translation for delete flows

**Files:**
- Modify: `backend/services/catalog_file_delete_service.py`
- Modify: `backend/routers/data_sync.py`
- Reference: `modules/core/db/schema.py`

- [ ] **Step 1: Add a dedicated exception type for data-sync schema drift**

```python
class DataSyncSchemaDriftError(RuntimeError):
    ...
```

- [ ] **Step 2: Translate missing-column failures inside quarantine count/delete helpers**

```python
except ProgrammingError as exc:
    if "catalog_file_id" in str(exc):
        raise DataSyncSchemaDriftError(...)
    raise
```

- [ ] **Step 3: Return an actionable error payload from the router**

The response detail must include:
- missing schema/table/column when known
- a direct migration instruction such as `alembic upgrade heads`
- no ambiguous `"删除文件失败"`-only diagnosis

- [ ] **Step 4: Re-run focused delete tests**

Run:
```powershell
pytest backend\tests\test_data_sync_file_delete_api.py backend\tests\test_data_sync_schema_guardrails.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add backend\services\catalog_file_delete_service.py backend\routers\data_sync.py backend\tests\test_data_sync_file_delete_api.py backend\tests\test_data_sync_schema_guardrails.py
git commit -m "fix(data-sync): surface schema drift errors in delete flows"
```

### Task 3: Extend startup schema verification to include critical data-sync columns

**Files:**
- Modify: `backend/models/database.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_verify_schema_completeness_sync_columns.py`

- [ ] **Step 1: Write a failing test for critical-column verification**

```python
def test_verify_schema_completeness_reports_missing_sync_columns(...):
    result = verify_schema_completeness()
    assert "core.data_quarantine.catalog_file_id" in result["missing_columns"]
```

- [ ] **Step 2: Run test to verify RED**

Run:
```powershell
pytest backend\tests\test_verify_schema_completeness_sync_columns.py -q
```

Expected:
- FAIL because `verify_schema_completeness()` does not currently report missing columns.

- [ ] **Step 3: Add a small critical-column contract list**

Start with:
- `core.data_quarantine.catalog_file_id`
- `core.staging_orders.file_id`
- `core.staging_product_metrics.file_id`
- `core.staging_inventory.file_id`

Do not scan every ORM column in every table. Keep this list intentionally small and data-sync-focused.

- [ ] **Step 4: Update `verify_schema_completeness()` return payload**

Add:
- `missing_columns`
- `all_critical_columns_exist`

- [ ] **Step 5: Make production startup fail on missing critical columns**

`backend/main.py` should refuse startup when the table set is present but a critical data-sync column is missing.

- [ ] **Step 6: Re-run startup verification test**

Run:
```powershell
pytest backend\tests\test_verify_schema_completeness_sync_columns.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```powershell
git add backend\models\database.py backend\main.py backend\tests\test_verify_schema_completeness_sync_columns.py
git commit -m "feat(db): gate startup on critical data-sync columns"
```

### Task 4: Extend the database health check script for data-sync critical columns

**Files:**
- Modify: `scripts/check_database_health.py`
- Create: `backend/tests/test_check_database_health_sync_contract.py`

- [ ] **Step 1: Write a failing contract test for `data_quarantine` coverage**

```python
def test_health_check_includes_data_sync_critical_columns():
    output = run_health_check(...)
    assert "core.data_quarantine" in output
    assert "catalog_file_id" in output
```

- [ ] **Step 2: Run the contract test to verify RED**

Run:
```powershell
pytest backend\tests\test_check_database_health_sync_contract.py -q
```

Expected:
- FAIL because the current script does not include `data_quarantine` in its critical table coverage.

- [ ] **Step 3: Add data-sync critical table definitions to the script**

At minimum cover:
- `core.data_quarantine`
- `core.staging_orders`
- `core.staging_product_metrics`
- `core.staging_inventory`

- [ ] **Step 4: Ensure recommendations explicitly mention Alembic migration**

The report should say what is missing and recommend migration, not generic manual DDL.

- [ ] **Step 5: Re-run the contract test**

Run:
```powershell
pytest backend\tests\test_check_database_health_sync_contract.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```powershell
git add scripts\check_database_health.py backend\tests\test_check_database_health_sync_contract.py
git commit -m "feat(db): cover data-sync critical columns in health checks"
```

### Task 5: Add a PostgreSQL migration rehearsal for the data-sync guardrails

**Files:**
- Create: `backend/tests/test_data_sync_schema_guardrails_postgres.py`
- Reference: `scripts/validate_migrations_fresh_db.py`
- Reference: `migrations/versions/20260112_v5_0_0_schema_snapshot.py`

- [ ] **Step 1: Write a failing rehearsal test or harness wrapper**

The rehearsal must prove:
- migrations apply on a fresh PostgreSQL database
- `core.data_quarantine.catalog_file_id` exists afterward
- startup schema verification passes

- [ ] **Step 2: Run the rehearsal in RED state if the harness is not wired yet**

Run:
```powershell
pytest backend\tests\test_data_sync_schema_guardrails_postgres.py -q
```

Expected:
- FAIL or SKIP until the rehearsal wrapper is implemented.

- [ ] **Step 3: Implement the rehearsal wrapper using the existing migration-validation pattern**

Prefer reusing:
- `scripts/validate_migrations_fresh_db.py`

Do not introduce a second competing migration-check workflow.

- [ ] **Step 4: Re-run the rehearsal**

Run:
```powershell
pytest backend\tests\test_data_sync_schema_guardrails_postgres.py -q
```

Expected:
- PASS in an environment with PostgreSQL available

- [ ] **Step 5: Commit**

```powershell
git add backend\tests\test_data_sync_schema_guardrails_postgres.py
git commit -m "test(db): rehearse data-sync schema guardrails on postgres"
```

### Task 6: Document the operational recovery path

**Files:**
- Create: `docs/reports/2026-04-03-data-sync-schema-drift-recovery.md`
- Modify: `docs/superpowers/plans/2026-04-03-data-sync-schema-guardrails.md`
- Reference: `scripts/check_database_health.py`
- Reference: `scripts/validate_migrations_fresh_db.py`

- [ ] **Step 1: Write the recovery runbook**

It must include:
- how to confirm the missing column
- how to run health check
- how to apply Alembic migrations
- how to verify delete-impact/delete recovery after migration

- [ ] **Step 2: Add a short “operator checklist” section**

Checklist:
- run health check
- run `alembic upgrade heads`
- restart backend
- retry delete-impact
- retry delete

- [ ] **Step 3: Commit**

```powershell
git add docs\reports\2026-04-03-data-sync-schema-drift-recovery.md docs\superpowers\plans\2026-04-03-data-sync-schema-guardrails.md
git commit -m "docs(data-sync): add schema drift recovery runbook"
```

## Exit Criteria

This project is complete only when:
- delete-impact and delete return actionable migration errors instead of opaque failures
- production startup fails if critical data-sync columns are missing
- database health checks cover data-sync critical columns
- PostgreSQL migration rehearsal proves `core.data_quarantine.catalog_file_id` exists after migration
- the operational recovery path is documented and repeatable
