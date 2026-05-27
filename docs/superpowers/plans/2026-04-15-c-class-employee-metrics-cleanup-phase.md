# C-Class Employee Metrics Cleanup Phase Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Chinese-column fallback logic and eventually drop legacy Chinese physical columns from `c_class.employee_performance` and `c_class.employee_commissions` after the English-column migration has been verified stable.

**Architecture:** Execute cleanup in two safe layers. First remove runtime fallback logic while keeping the Chinese columns intact, and verify all payroll, performance, commission, and income paths still succeed against the already-migrated English-column tables. Only after that verification passes should a separate destructive migration drop the Chinese columns.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest

---

## File Map

### Runtime cleanup

- Modify: `backend/domains/business/routers/hr_commission.py`
- Modify: `backend/domains/business/routers/performance_management.py`
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/services/hr_income_calculation_service.py`

### Cleanup migration

- Create: `migrations/versions/<new_revision>_drop_c_class_employee_metric_chinese_columns.py`

### Tests

- Modify: `backend/tests/test_hr_commission_profit_basis_routes.py`
- Modify: `backend/tests/test_payroll_generation_service.py`
- Modify: `backend/tests/test_hr_income_calculation_service.py`
- Modify: `backend/tests/test_performance_management_person_fallback.py`
- Add: `backend/tests/test_c_class_employee_metrics_cleanup_contract.py`

### Docs and progress

- Modify: `progress.md`
- Modify: `findings.md`

## Task 1: Add Cleanup Contract Tests

**Files:**
- Add: `backend/tests/test_c_class_employee_metrics_cleanup_contract.py`

- [ ] **Step 1: Write failing cleanup contract tests**

```python
from pathlib import Path


def test_runtime_no_longer_contains_employee_performance_cn_fallback():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    assert "_load_employee_performance_cn_fallback" not in source


def test_runtime_no_longer_contains_employee_commissions_cn_fallback():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    assert "_load_employee_commissions_cn_fallback" not in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_cleanup_contract.py -v`
Expected: FAIL because fallback logic still exists today

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_c_class_employee_metrics_cleanup_contract.py
git commit -m "test: add c-class employee metrics cleanup contract"
```

## Task 2: Remove Reader Fallback From HR Commission Routes

**Files:**
- Modify: `backend/domains/business/routers/hr_commission.py`
- Modify: `backend/tests/test_hr_commission_profit_basis_routes.py`

- [ ] **Step 1: Replace fallback-specific tests with English-column success tests**

Write tests that prove:

- `list_employee_performance` works using English-column ORM shape
- `list_employee_commissions` works using English-column ORM shape

- [ ] **Step 2: Run tests to verify they fail before cleanup**

Run: `python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py -v`
Expected: FAIL if route still depends on old fallback-only assumptions

- [ ] **Step 3: Remove route fallback helpers**

Delete:

- `_load_employee_performance_cn_fallback`
- `_load_employee_commissions_cn_fallback`

Then simplify routes to pure English-column ORM reads.

- [ ] **Step 4: Run route tests**

Run: `python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/business/routers/hr_commission.py backend/tests/test_hr_commission_profit_basis_routes.py
git commit -m "refactor: remove hr commission chinese fallback"
```

## Task 3: Remove Reader Fallback From Payroll Generation

**Files:**
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/tests/test_payroll_generation_service.py`

- [ ] **Step 1: Replace fallback-specific tests with English-column success tests**

Write tests that prove:

- `generate_employee_month()` succeeds with English-column reads only
- `generate_month()` succeeds with English-column reads only

- [ ] **Step 2: Run tests to verify they fail before cleanup**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py -v`
Expected: FAIL if tests still depend on fallback or service still exposes fallback behavior

- [ ] **Step 3: Remove transitional fallback loaders**

Delete:

- `_load_employee_commission()` Chinese fallback branch
- `_load_employee_performance()` Chinese fallback branch
- `_load_employee_commission_rows()` Chinese fallback branch
- `_load_employee_performance_rows()` Chinese fallback branch

Keep only English-column ORM reads.

- [ ] **Step 4: Run service tests**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/payroll_generation_service.py backend/tests/test_payroll_generation_service.py
git commit -m "refactor: remove payroll c-class chinese fallback"
```

## Task 4: Remove Writer Fallback From HR Income Calculation

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: Replace fallback-specific tests with English-write assertions**

Write or adjust tests so they prove:

- ORM writes are the only successful path
- no Chinese fallback SQL is expected anymore

- [ ] **Step 2: Run tests to verify they fail before cleanup**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -v`
Expected: FAIL until fallback-specific expectations are removed

- [ ] **Step 3: Remove Chinese fallback write SQL**

Delete fallback SQL branches for:

- `employee_commissions`
- `employee_performance`

The service should only use English-column ORM writes.

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py
git commit -m "refactor: remove hr income chinese fallback writes"
```

## Task 5: Remove Person-Mode Fallback From Performance Management

**Files:**
- Modify: `backend/domains/business/routers/performance_management.py`
- Modify: `backend/tests/test_performance_management_person_fallback.py`

- [ ] **Step 1: Replace fallback-specific tests with English-column tests**

Write tests that prove the person-group performance path works directly against English columns.

- [ ] **Step 2: Run tests to verify they fail before cleanup**

Run: `python -m pytest backend/tests/test_performance_management_person_fallback.py -v`
Expected: FAIL until the route no longer relies on fallback expectations

- [ ] **Step 3: Remove fallback branch**

Delete person-mode Chinese compatibility SQL path and keep the English ORM path only.

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_performance_management_person_fallback.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/business/routers/performance_management.py backend/tests/test_performance_management_person_fallback.py
git commit -m "refactor: remove performance person-mode chinese fallback"
```

## Task 6: Run Code-Only Regression Before Dropping Columns

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: Run the full targeted runtime regression suite**

Run:

```bash
python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_payroll_generation_service.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_hr_payroll_routes.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_performance_management_person_fallback.py -v
```

Expected: PASS with no fallback logic remaining

- [ ] **Step 2: Record results in progress log**

- [ ] **Step 3: Commit**

```bash
git add progress.md
git commit -m "test: verify c-class employee metrics cleanup runtime"
```

## Task 7: Add Column-Drop Migration

**Files:**
- Create: `migrations/versions/<new_revision>_drop_c_class_employee_metric_chinese_columns.py`
- Modify: `backend/tests/test_c_class_employee_metrics_cleanup_contract.py`

- [ ] **Step 1: Add failing migration cleanup tests**

Write tests that assert the new migration exists and references all Chinese columns to be dropped.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_cleanup_contract.py -v`
Expected: FAIL until the migration exists

- [ ] **Step 3: Write migration**

Drop from `c_class.employee_performance`:

- `员工编号`
- `年月`
- `实际销售额`
- `达成率`
- `绩效得分`
- `计算时间`

Drop from `c_class.employee_commissions`:

- `员工编号`
- `年月`
- `销售额`
- `提成金额`
- `提成比例`
- `计算时间`

Keep English constraints and indexes.

- [ ] **Step 4: Run cleanup contract tests**

Run: `python -m pytest backend/tests/test_c_class_employee_metrics_cleanup_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions backend/tests/test_c_class_employee_metrics_cleanup_contract.py
git commit -m "feat: drop c-class employee metric chinese columns"
```

## Task 8: Rehearse Destructive Migration On Local PostgreSQL

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] **Step 1: Run cleanup migration on local PostgreSQL**

Run:

```bash
python -m alembic upgrade <cleanup_revision>
```

Expected:

- migration applies cleanly
- only English columns remain

- [ ] **Step 2: Query information_schema**

Verify:

- Chinese columns absent
- English columns present

- [ ] **Step 3: Run runtime regression again**

Run:

```bash
python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_payroll_generation_service.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_hr_payroll_routes.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_performance_management_person_fallback.py -v
```

Expected: PASS

- [ ] **Step 4: Record migration rehearsal results**

- [ ] **Step 5: Final commit**

```bash
git add findings.md progress.md
git commit -m "docs: record c-class employee metrics cleanup rehearsal"
```

## Risks To Watch

- hidden low-frequency code paths may still assume Chinese columns
- destructive cleanup migration is harder to roll back than the transition migration
- tests must reflect English-column success, not fallback success

## Definition Of Done

- no active runtime fallback logic remains for the two tables
- local PostgreSQL rehearsal succeeds after dropping Chinese columns
- all targeted payroll, performance, commission, and income flows still pass
- the repository no longer carries dual-schema complexity for these two C-class tables

