# C-Class Employee Metrics English Column Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `c_class.employee_performance` and `c_class.employee_commissions` from legacy Chinese physical columns to English physical columns without breaking existing payroll, performance, or commission runtime flows.

**Architecture:** Use a phased in-place migration. First add English columns plus indexes and backfill from existing Chinese columns. Then update runtime write paths to prefer English columns while temporarily keeping fallback readers for safety. Finally verify all critical flows before removing legacy Chinese-column fallback logic and columns in a later cleanup phase.

**Tech Stack:** Alembic, PostgreSQL, SQLAlchemy async, FastAPI, Pydantic, pytest

---

## File Map

### Database migrations

- Create: `migrations/versions/<new_revision>_c_class_employee_metrics_english_columns.py`

### ORM and schema contracts

- Modify: `modules/core/db/schema.py`
- Modify: `backend/schemas/hr.py`

### Runtime writers and readers

- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/routers/hr_commission.py`
- Modify: `backend/routers/performance_management.py` only if any remaining transitional contract adjustment is required

### Tests

- Modify: `backend/tests/test_hr_commission_profit_basis_routes.py`
- Modify: `backend/tests/test_payroll_generation_service.py`
- Add: `backend/tests/test_c_class_employee_metrics_migration_contract.py`
- Add: `backend/tests/test_c_class_employee_metrics_backfill_sql.py`

### Planning and docs

- Modify: `progress.md`
- Modify: `findings.md`
- Modify: `task_plan.md` if currently used for the active execution thread

## Task 1: Add Migration Contract Tests

**Files:**
- Add: `backend/tests/test_c_class_employee_metrics_migration_contract.py`

- [ ] **Step 1: Write failing migration contract tests**

```python
from pathlib import Path


def test_employee_performance_english_column_migration_exists():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("migrations/versions").glob("*.py")
    )
    assert "employee_performance" in source
    assert "employee_code" in source
    assert "actual_sales" in source


def test_employee_commissions_english_column_migration_exists():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("migrations/versions").glob("*.py")
    )
    assert "employee_commissions" in source
    assert "commission_amount" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_migration_contract.py -v`
Expected: FAIL because no migration exists yet for the two C-class tables

- [ ] **Step 3: Commit the failing tests**

```bash
git add backend/tests/test_c_class_employee_metrics_migration_contract.py
git commit -m "test: add c-class employee metrics migration contract"
```

## Task 2: Create Migration To Add English Columns

**Files:**
- Create: `migrations/versions/<new_revision>_c_class_employee_metrics_english_columns.py`
- Test: `backend/tests/test_c_class_employee_metrics_migration_contract.py`

- [ ] **Step 1: Write migration skeleton**

Migration responsibilities:

- add English columns to `c_class.employee_performance`
  - `employee_code`
  - `year_month`
  - `actual_sales`
  - `achievement_rate`
  - `performance_score`
  - `calculated_at`
- add English columns to `c_class.employee_commissions`
  - `employee_code`
  - `year_month`
  - `sales_amount`
  - `commission_amount`
  - `commission_rate`
  - `calculated_at`

- [ ] **Step 2: Add idempotent backfill SQL**

Backfill rules:

```sql
UPDATE c_class.employee_performance
SET employee_code = "员工编号",
    year_month = "年月",
    actual_sales = "实际销售额",
    achievement_rate = "达成率",
    performance_score = "绩效得分",
    calculated_at = "计算时间"
WHERE employee_code IS NULL OR year_month IS NULL;
```

Equivalent SQL is required for `employee_commissions`.

- [ ] **Step 3: Add indexes and unique constraints**

Required parity:

- `employee_performance`
  - unique `(employee_code, year_month)`
  - index on `employee_code`
  - index on `year_month`
- `employee_commissions`
  - unique `(employee_code, year_month)`
  - index on `employee_code`
  - index on `year_month`

- [ ] **Step 4: Run migration contract tests**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_migration_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions backend/tests/test_c_class_employee_metrics_migration_contract.py
git commit -m "feat: add c-class employee metrics english columns"
```

## Task 3: Add Backfill Verification Tests

**Files:**
- Add: `backend/tests/test_c_class_employee_metrics_backfill_sql.py`

- [ ] **Step 1: Write failing backfill SQL asset tests**

```python
from pathlib import Path


def test_migration_backfills_employee_performance_from_chinese_columns():
    migration = Path("migrations/versions/<new_revision>_c_class_employee_metrics_english_columns.py").read_text(encoding="utf-8")
    assert '"员工编号"' in migration
    assert "employee_code" in migration


def test_migration_backfills_employee_commissions_from_chinese_columns():
    migration = Path("migrations/versions/<new_revision>_c_class_employee_metrics_english_columns.py").read_text(encoding="utf-8")
    assert '"提成金额"' in migration
    assert "commission_amount" in migration
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_backfill_sql.py -v`
Expected: FAIL until migration contains explicit backfill logic

- [ ] **Step 3: Update migration until tests pass**

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_c_class_employee_metrics_backfill_sql.py migrations/versions
git commit -m "test: verify c-class employee metrics backfill sql"
```

## Task 4: Prefer English Writes In HR Income Calculation

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Test: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: Add failing write-path test**

```python
def test_calculate_month_prefers_english_employee_metric_fields(...):
    ...
    assert english_update_or_insert_was_used
```

The test should prove that when English columns exist, the service writes through the ORM/English path and does not depend on Chinese fallback.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -k english -v`
Expected: FAIL or missing coverage before implementation

- [ ] **Step 3: Implement minimal preference logic**

Approach:

- keep existing fallback behavior
- treat English ORM writes as primary path
- preserve Chinese fallback only for compatibility window

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py
git commit -m "feat: prefer english writes for c-class employee metrics"
```

## Task 5: Keep Payroll Generation Compatible During Transition

**Files:**
- Modify: `backend/services/payroll_generation_service.py`
- Test: `backend/tests/test_payroll_generation_service.py`

- [ ] **Step 1: Verify current fallback tests remain green**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py -v`
Expected: PASS

- [ ] **Step 2: Add transition-preference test**

```python
def test_generate_month_prefers_english_fields_when_available(...):
    ...
```

The test should show that if English fields are available, the service uses them without needing Chinese fallback.

- [ ] **Step 3: Implement minimal preference logic**

Goal:

- English-column rows should be the default successful path
- Chinese-column fallback remains only as temporary safety

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/payroll_generation_service.py backend/tests/test_payroll_generation_service.py
git commit -m "feat: prefer english c-class reads in payroll generation"
```

## Task 6: Verify Reader Paths Still Work

**Files:**
- Modify: `backend/routers/hr_commission.py` only if transition logic needs refinement
- Modify: `backend/routers/performance_management.py` only if transition logic needs refinement
- Test: `backend/tests/test_hr_commission_profit_basis_routes.py`
- Test: `backend/tests/test_performance_management_person_fallback.py`

- [ ] **Step 1: Run failing-or-existing reader tests**

Run:
- `python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py -v`
- `python -m pytest backend/tests/test_performance_management_person_fallback.py -v`

Expected: PASS after migration-compatible adjustments

- [ ] **Step 2: Add English-preference reader tests if coverage is missing**

Goal:

- prove readers work when English columns are present
- keep Chinese fallback active during transition

- [ ] **Step 3: Implement minimal changes if needed**

- [ ] **Step 4: Commit**

```bash
git add backend/routers/hr_commission.py backend/routers/performance_management.py backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_performance_management_person_fallback.py
git commit -m "test: verify c-class employee metric readers across transition"
```

## Task 7: Rehearse Real Database Migration

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run migration against the local PostgreSQL database**

Run:

```bash
python -m alembic upgrade <new_revision>
```

Expected:

- migration applies successfully
- English columns appear in both C-class tables

- [ ] **Step 2: Query information_schema to verify columns exist**

Run SQL checks for:

- `c_class.employee_performance`
- `c_class.employee_commissions`

Expected:

- English columns present
- Chinese columns still present during transition

- [ ] **Step 3: Query sample rows to verify backfill**

Expected:

- Chinese and English fields contain matching values

- [ ] **Step 4: Record results in planning files**

- [ ] **Step 5: Commit**

```bash
git add progress.md findings.md
git commit -m "docs: record c-class employee metrics migration rehearsal"
```

## Task 8: Run End-To-End Regression Verification

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: Run payroll and performance test set**

Run:

```bash
python -m pytest backend/tests/test_payroll_generation_service.py backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_hr_payroll_routes.py backend/tests/test_add_performance_income_acceptance.py -v
```

Expected: PASS

- [ ] **Step 2: Run any remaining targeted tests for person-group performance path**

Run:

```bash
python -m pytest backend/tests/test_performance_management_person_fallback.py -v
```

Expected: PASS

- [ ] **Step 3: Verify no new runtime contract regressions**

Review:

- personal income
- payroll refresh
- employee performance list
- employee commissions list

- [ ] **Step 4: Update progress log**

- [ ] **Step 5: Final commit**

```bash
git add progress.md
git commit -m "test: verify c-class employee metrics english-column migration"
```

## Risks To Watch

- some paths may silently remain on Chinese fallback even after English columns exist
- unique constraints may fail if duplicate historical rows exist
- null backfill could expose malformed historical data
- future cleanup must not happen until actual runtime no longer depends on fallback

## Definition Of Done

- both target tables physically expose English columns
- backfill logic exists and is verified
- payroll, performance, commission, and income runtime paths work during transition
- migration can be applied to the local PostgreSQL database
- the codebase is ready for a later cleanup phase that removes Chinese columns and fallback logic
