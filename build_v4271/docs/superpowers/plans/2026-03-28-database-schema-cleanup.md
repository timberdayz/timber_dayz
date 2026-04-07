# Database Schema Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status note (2026-03-28):** This is still an active future plan, not a landed implementation. The current repository state only has the design/plan documents and production audit context; the inventory script, reviewed inventory report, proof tests, and cleanup migrations are still open work. This plan remains part of the live backlog.

**Goal:** Build a safe, evidence-driven cleanup workflow for duplicated and misplaced database tables so production can gradually converge to the intended schema layout without breaking runtime paths.

**Architecture:** Treat cleanup as an inventory-first migration project. First generate a canonical duplicate-table inventory from ORM expectations plus actual database state, then classify candidates by risk, add proof tests for low-risk public duplicates, and only after that land small cleanup migrations wave by wave.

**Tech Stack:** Python, Alembic, PostgreSQL, SQLAlchemy, pytest

---

### Task 1: Create a duplicate-table inventory tool and contract

**Files:**
- Create: `backend/tests/test_schema_cleanup_inventory.py`
- Create: `scripts/analyze_schema_cleanup_candidates.py`

- [ ] **Step 1: Write the failing inventory contract test**

```python
def test_inventory_script_emits_duplicate_groups():
    ...
```

Assert that the script output contains:
- canonical schema
- actual schemas
- candidate risk class

- [ ] **Step 2: Run the test to verify it fails**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_inventory.py -q
```

Expected:
- FAIL because the inventory tool does not exist yet.

- [ ] **Step 3: Implement the inventory script**

The script must:
- read ORM metadata from `modules/core/db/schema.py`
- inspect actual DB table placement
- group duplicated tables
- classify them into keep / likely cleanup / operational / unclear
- emit machine-readable JSON and human-readable markdown summary

- [ ] **Step 4: Re-run the test**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_inventory.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add backend\tests\test_schema_cleanup_inventory.py scripts\analyze_schema_cleanup_candidates.py
git commit -m "feat(db): add schema cleanup inventory tool"
```

### Task 2: Generate and store the first canonical inventory report

**Files:**
- Create: `docs/reports/2026-03-28-schema-cleanup-inventory.md`
- Modify: `docs/deployment/2026-03-28-production-deploy-and-migration-report.md`

- [ ] **Step 1: Run the inventory tool against local DB**

Run:
```powershell
python scripts\analyze_schema_cleanup_candidates.py > temp_schema_cleanup_inventory.json
```

- [ ] **Step 2: Convert the inventory into a reviewed markdown report**

The report must include:
- duplicated table groups
- canonical target schema
- risk classification
- recommended action

- [ ] **Step 3: Add a short pointer from the production migration report**

Link the production report to the new inventory report so cleanup decisions are traceable.

- [ ] **Step 4: Commit**

```powershell
git add docs\reports\2026-03-28-schema-cleanup-inventory.md docs\deployment\2026-03-28-production-deploy-and-migration-report.md
git commit -m "docs(db): record schema cleanup inventory"
```

### Task 3: Add proof tests for low-risk duplicate targets

**Files:**
- Create: `backend/tests/test_schema_cleanup_low_risk_candidates.py`
- Modify: relevant feature tests as needed

- [ ] **Step 1: Write failing proof tests for low-risk duplicates**

Start with:
- `public.performance_config`
- `public.sales_campaigns`
- `public.sales_campaign_shops`
- `public.target_breakdown`

The tests should prove the runtime uses the target schema copy, not the public duplicate.

- [ ] **Step 2: Run focused tests to verify they fail or expose missing proof**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_low_risk_candidates.py -q
```

Expected:
- FAIL or incomplete coverage before proof is added.

- [ ] **Step 3: Add the minimum missing proof coverage**

Do not drop tables yet.
Only add tests and query assertions that prove the target schema is authoritative.

- [ ] **Step 4: Re-run focused tests**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_low_risk_candidates.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add backend\tests\test_schema_cleanup_low_risk_candidates.py
git commit -m "test(db): prove low-risk schema cleanup candidates"
```

### Task 4: Land low-risk cleanup migration wave 1

**Files:**
- Create: `backend/tests/test_schema_cleanup_wave1_migration_contract.py`
- Create: `migrations/versions/YYYYMMDD_hhmm_schema_cleanup_wave1.py`

- [ ] **Step 1: Write failing migration contract test**

The test must require the wave 1 migration to mention exactly the approved low-risk duplicate drops or archive renames.

- [ ] **Step 2: Run focused test to verify it fails**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_wave1_migration_contract.py -q
```

Expected:
- FAIL because wave 1 migration does not exist yet.

- [ ] **Step 3: Implement wave 1 migration**

Use one of two patterns per table:
- conservative rename/archive
- direct drop only if proof is already strong

The migration must be idempotent and reversible enough for operations.

- [ ] **Step 4: Re-run migration contract test**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_wave1_migration_contract.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add backend\tests\test_schema_cleanup_wave1_migration_contract.py migrations\versions\*.py
git commit -m "feat(db): add schema cleanup wave 1 migration"
```

### Task 5: Rehearse cleanup migrations on a temporary PostgreSQL database

**Files:**
- Create: `backend/tests/test_schema_cleanup_rehearsal.py`
- Modify: `docs/reports/2026-03-28-schema-cleanup-inventory.md`

- [ ] **Step 1: Write failing rehearsal test**

The test should require:
- migration upgrades cleanly
- schema completeness still passes
- dropped duplicate tables are actually gone

- [ ] **Step 2: Run rehearsal test to verify it fails**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_rehearsal.py -q
```

Expected:
- FAIL until the cleanup rehearsal path is implemented.

- [ ] **Step 3: Implement rehearsal verification**

Reuse the temporary-DB migration rehearsal pattern already used for production migration checks.

- [ ] **Step 4: Re-run rehearsal test**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_rehearsal.py -q
```

Expected:
- PASS

- [ ] **Step 5: Record the rehearsal result**

Append the result to the inventory report or create a linked follow-up report.

- [ ] **Step 6: Commit**

```powershell
git add backend\tests\test_schema_cleanup_rehearsal.py docs\reports\2026-03-28-schema-cleanup-inventory.md
git commit -m "test(db): rehearse schema cleanup migration wave 1"
```

### Task 6: Plan higher-risk cleanup waves without executing them

**Files:**
- Modify: `docs/reports/2026-03-28-schema-cleanup-inventory.md`
- Create: `docs/superpowers/plans/2026-03-28-database-schema-cleanup-wave2.md`

- [ ] **Step 1: Classify higher-risk duplicates**

Focus on:
- `public.entity_aliases`
- `public.staging_raw_data`
- `public.dim_shops`

- [ ] **Step 2: Write a separate wave 2 plan**

Do not execute drops in this task.
Document:
- required runtime proofs
- rollback approach
- smoke tests needed

- [ ] **Step 3: Commit**

```powershell
git add docs\reports\2026-03-28-schema-cleanup-inventory.md docs\superpowers\plans\2026-03-28-database-schema-cleanup-wave2.md
git commit -m "docs(db): plan higher-risk schema cleanup waves"
```

## Exit Criteria

The cleanup-planning project is complete only when:
- duplicated tables are inventoried
- low-risk cleanup candidates are proven by tests
- wave 1 cleanup migration exists and rehearses cleanly
- higher-risk cleanup waves are documented separately
- no production table is dropped without evidence and rollback coverage
