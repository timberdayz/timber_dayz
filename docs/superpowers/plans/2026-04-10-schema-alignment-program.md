# Schema Alignment Program Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a full-schema drift audit and complete the first repair wave that aligns ORM, migrations, runtime helpers, and verification logic for the collection/runtime-critical table family.

**Architecture:** Split the work into two deliverables inside one implementation stream. First, create a canonical audit/report artifact that compares ORM, migrations, and actual runtime schema for the full known table set. Second, repair the wave-1 collection/runtime-critical tables through tests, helper alignment, migration-contract coverage, and narrowly-scoped compatibility or repair work.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL, Alembic migrations under `migrations/versions/`, pytest, existing runtime/schema verification helpers

---

## File Structure

### Existing files to modify

- `backend/models/database.py`
  Responsibility: central runtime schema/time-column helpers and schema verification support.
- `modules/core/db/schema.py`
  Responsibility: canonical ORM definitions and wave-1 table metadata.
- `migrations/versions/20260112_v5_0_0_schema_snapshot.py`
  Responsibility: historical baseline reference for drift comparisons.
- `migrations/versions/20260328_add_task_center_tables.py`
  Responsibility: task-center migration contract reference.
- `scripts/migrate_core_tables.py`
  Responsibility: core-table migration helper; must not hardcode incorrect runtime schemas.
- `scripts/test_search_path.py`
  Responsibility: schema verification script; must respect actual runtime table placement.
- `scripts/verify_restore.py`
  Responsibility: restore verification; currently assumes generic `created_at` freshness.
- `backend/tests/test_database_schema_verification.py`
  Responsibility: schema-alias/runtime revision expectations.
- `backend/tests/test_schema_cleanup_inventory.py`
  Responsibility: inventory/classification behavior for cleanup candidates.
- `backend/tests/test_collection_task_log_timestamp_resilience.py`
  Responsibility: lock `collection_task_logs.timestamp` behavior.

### New files to create

- `docs/reports/2026-04-10-schema-alignment-audit.md`
  Responsibility: canonical full drift audit with wave-1 scope and priority.
- `backend/tests/test_schema_alignment_wave1_contract.py`
  Responsibility: lock the wave-1 target shape and runtime placement expectations.
- `backend/tests/test_schema_alignment_migration_contract.py`
  Responsibility: require explicit migration repair coverage for wave-1 tables once repair migrations are added.
- `scripts/audit_schema_alignment.py`
  Responsibility: machine-readable audit generator comparing ORM, migrations, and actual runtime DB state.

---

### Task 1: Build the Full Drift Audit Artifact

**Files:**
- Create: `scripts/audit_schema_alignment.py`
- Create: `docs/reports/2026-04-10-schema-alignment-audit.md`
- Modify: `backend/tests/test_schema_cleanup_inventory.py`

- [ ] **Step 1: Write the failing audit generator contract**

Add coverage that requires the audit tool to emit, at minimum:
- table name
- ORM schema
- runtime schema
- migration evidence reference
- drift priority (`P0/P1/P2/P3`)
- wave membership

- [ ] **Step 2: Run the focused contract to verify it fails**

Run:

```powershell
python -m pytest backend/tests/test_schema_cleanup_inventory.py -q
```

Expected: FAIL because the new audit generator output contract does not exist yet.

- [ ] **Step 3: Implement the audit script**

The script must:
- read ORM metadata from `modules/core/db/schema.py`
- inspect actual PostgreSQL table placement/columns/defaults
- scan selected migration files for table-definition evidence
- produce machine-readable JSON or stdout suitable for report generation

- [ ] **Step 4: Re-run the audit contract**

Run:

```powershell
python -m pytest backend/tests/test_schema_cleanup_inventory.py -q
```

Expected: PASS

- [ ] **Step 5: Generate and write the reviewed markdown audit report**

The report must contain:
- full drift summary
- classification model applied to discovered tables
- explicit wave-1 table set
- first-wave priorities and rationale

- [ ] **Step 6: Commit the audit artifact**

```powershell
git add scripts/audit_schema_alignment.py backend/tests/test_schema_cleanup_inventory.py docs/reports/2026-04-10-schema-alignment-audit.md
git commit -m "docs(db): add schema alignment audit and wave one scope"
```

---

### Task 2: Lock Wave-1 Runtime Shape With Tests

**Files:**
- Create: `backend/tests/test_schema_alignment_wave1_contract.py`
- Modify: `backend/tests/test_database_schema_verification.py`
- Modify: `backend/tests/test_collection_task_log_timestamp_resilience.py`
- Modify: `backend/models/database.py`

- [ ] **Step 1: Write the failing wave-1 runtime contract tests**

Add tests that prove:
- `catalog_files` runs from `public`
- `collection_tasks` and `collection_task_logs` run from `core`
- `task_center_tasks/logs/links` run from `public`
- `collection_task_logs` uses `timestamp`
- `catalog_files` freshness uses `first_seen_at`

- [ ] **Step 2: Run the wave-1 runtime contract tests to verify they fail**

Run:

```powershell
python -m pytest backend/tests/test_schema_alignment_wave1_contract.py backend/tests/test_database_schema_verification.py backend/tests/test_collection_task_log_timestamp_resilience.py -q
```

Expected: FAIL until the runtime helper and schema expectations are fully aligned.

- [ ] **Step 3: Implement or extend centralized runtime helpers**

In `backend/models/database.py`, ensure there is one authoritative place for:
- runtime schema resolution
- qualified runtime table names
- runtime freshness/time-column resolution

Do not spread this logic into individual scripts.

- [ ] **Step 4: Re-run the wave-1 runtime contract tests**

Run:

```powershell
python -m pytest backend/tests/test_schema_alignment_wave1_contract.py backend/tests/test_database_schema_verification.py backend/tests/test_collection_task_log_timestamp_resilience.py -q
```

Expected: PASS

- [ ] **Step 5: Commit the wave-1 runtime contracts**

```powershell
git add backend/models/database.py backend/tests/test_schema_alignment_wave1_contract.py backend/tests/test_database_schema_verification.py backend/tests/test_collection_task_log_timestamp_resilience.py
git commit -m "test(db): lock wave one runtime schema contracts"
```

---

### Task 3: Align Scripts and Diagnostics With Wave-1 Reality

**Files:**
- Modify: `scripts/migrate_core_tables.py`
- Modify: `scripts/test_search_path.py`
- Modify: `scripts/verify_restore.py`
- Test: `backend/tests/test_runtime_schema_resolution.py`
- Create: additional focused assertions in `backend/tests/test_schema_alignment_wave1_contract.py`

- [ ] **Step 1: Write the failing script-alignment tests**

Add assertions that forbid:
- hardcoded wrong schema references for wave-1 tables
- hardcoded generic freshness columns where the runtime column is table-specific

- [ ] **Step 2: Run focused script-alignment tests to verify they fail**

Run:

```powershell
python -m pytest backend/tests/test_runtime_schema_resolution.py backend/tests/test_schema_alignment_wave1_contract.py -q
```

Expected: FAIL until scripts use the centralized runtime helpers.

- [ ] **Step 3: Update wave-1 scripts to use centralized runtime helpers**

Required minimum coverage:
- `scripts/migrate_core_tables.py`
- `scripts/test_search_path.py`
- `scripts/verify_restore.py`

Rules:
- no raw `core.catalog_files` assumptions
- no generic `MAX(created_at)` for tables whose freshness column is not `created_at`

- [ ] **Step 4: Re-run focused script-alignment tests**

Run:

```powershell
python -m pytest backend/tests/test_runtime_schema_resolution.py backend/tests/test_schema_alignment_wave1_contract.py -q
```

Expected: PASS

- [ ] **Step 5: Commit the script alignment**

```powershell
git add scripts/migrate_core_tables.py scripts/test_search_path.py scripts/verify_restore.py backend/tests/test_runtime_schema_resolution.py backend/tests/test_schema_alignment_wave1_contract.py
git commit -m "fix(db): align wave one diagnostics with runtime schema"
```

---

### Task 4: Add Migration-Contract Coverage For Wave-1 Repair

**Files:**
- Create: `backend/tests/test_schema_alignment_migration_contract.py`
- Modify: relevant migration files only if a repair migration already exists
- Optionally create: `migrations/versions/YYYYMMDD_wave1_schema_alignment.py`

- [ ] **Step 1: Write the failing migration contract**

The contract must require explicit migration coverage for the wave-1 table family, including:
- schema placement
- critical defaults
- critical time columns
- any approved repair behavior

- [ ] **Step 2: Run the migration contract test to verify it fails**

Run:

```powershell
python -m pytest backend/tests/test_schema_alignment_migration_contract.py -q
```

Expected: FAIL until a clear wave-1 migration contract exists.

- [ ] **Step 3: Decide the minimum migration action**

If the approved target can be expressed as contract-only for now, document that explicitly.
If a repair migration is required, create one narrow wave-1 migration.

Do not broaden into non-wave-1 tables.

- [ ] **Step 4: Re-run the migration contract**

Run:

```powershell
python -m pytest backend/tests/test_schema_alignment_migration_contract.py -q
```

Expected: PASS

- [ ] **Step 5: Commit the migration contract or repair**

```powershell
git add backend/tests/test_schema_alignment_migration_contract.py migrations/versions
git commit -m "test(db): add wave one schema alignment migration contract"
```

---

### Task 5: Run the Wave-1 Verification Bundle

**Files:**
- Modify: `docs/superpowers/plans/2026-04-10-schema-alignment-program.md`
- Verify: `docs/reports/2026-04-10-schema-alignment-audit.md`

- [ ] **Step 1: Run the full wave-1 verification bundle**

Run:

```powershell
python -m pytest backend/tests/test_schema_cleanup_inventory.py backend/tests/test_database_schema_verification.py backend/tests/test_collection_task_log_timestamp_resilience.py backend/tests/test_runtime_schema_resolution.py backend/tests/test_schema_alignment_wave1_contract.py backend/tests/test_schema_alignment_migration_contract.py backend/tests/test_task_center_schema.py -q
```

Expected: PASS

- [ ] **Step 2: Re-read the audit report and confirm wave-1 status**

Update the report if needed so it clearly states:
- audited full scope
- completed wave-1 fixes
- remaining `P2/P3` backlog

- [ ] **Step 3: Commit the verified wave-1 state**

```powershell
git add docs/reports/2026-04-10-schema-alignment-audit.md docs/superpowers/plans/2026-04-10-schema-alignment-program.md
git commit -m "docs(db): record wave one schema alignment completion"
```

---

## Notes

- This plan intentionally starts with audit + wave-1 repair, not whole-database migration.
- Wave 1 is complete only when ORM, helper logic, script logic, and migration contracts all agree.
- CLI component-test `main_account_id` work is explicitly out of scope for this plan unless it becomes part of a wave-1 table contract.
