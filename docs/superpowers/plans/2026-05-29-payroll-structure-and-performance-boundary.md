# Payroll Structure And Performance Boundary Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild payroll and performance boundaries so shop performance, employee performance, operation targets, commission, and payroll each have one clear responsibility and no longer rely on implicit store-score inheritance for employee pay.

**Architecture:** First change backend truth models and contracts, then adapt payroll generation and monthly settlement consumers, and only after that finish the remaining frontend pages. Keep existing shop-performance calculation running while introducing a dedicated employee-performance input/result path.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL/Alembic, Pydantic, Vue 3, Element Plus, pytest, Node built-in test runner

## Execution Status

Status: Substantially completed on 2026-05-29 session.

- Completed:
  - Task 1 salary structure `performance_package_amount`
  - Task 2 dedicated `employee_performance_inputs`
  - Task 3 operation target explicit `scope_type` boundary, migration, runtime enforcement
  - Task 4 employee performance no longer defaults to store-total inheritance
  - Task 5 payroll performance salary switched to performance package formula
  - Task 6 My Income / monthly settlement readers kept payroll-first and snapshot-aware
  - Task 7 employee performance input backend API
  - Task 8 frontend pages aligned to new contracts
  - Task 9 final verification substantially covered by targeted pytest/node tests
- Covered differently from original plan:
  - Some dedicated test filenames were replaced by equivalent assertions in existing test files during implementation, then later补齐为独立契约测试文件
- Not completed from plan-governance perspective:
  - Per-task commit steps were not executed
  - Original checklist boxes were not maintained in real time

## Final Closeout

Closeout date: 2026-05-30

Final outcome:

- Core payroll / performance boundary refactor completed
- Employee performance input model, API, UI, templates, and audit flow completed
- Shop performance official scope settled as `sales + profit + operation`
- `key_product` explicitly kept out of current formal scope
- My Income, payroll stale hints, monthly snapshots, and income audit flow completed

Remaining items are no longer blocking this plan and have been reclassified as follow-up governance work:

- historical `target_breakdown` data cleanup
- longer-term schema governance
- future `key_product` business design

---

### Task 1: Redesign Salary Structure Contract For Fixed Salary And Performance Package

**Files:**
- Modify: `modules/core/db/schema_parts/business.py`
- Modify: `backend/schemas/hr.py`
- Create: `backend/tests/test_salary_structure_performance_package_contract.py`
- Create: `migrations/versions/<timestamp>_salary_structure_performance_package.py`

- [ ] **Step 1: Write the failing contract test**

```python
def test_salary_structure_has_fixed_salary_and_performance_package_fields():
    from modules.core.db import SalaryStructure

    columns = SalaryStructure.__table__.c
    assert "base_salary" in columns
    assert "position_salary" in columns
    assert "performance_package_amount" in columns
    assert "performance_ratio" not in columns or columns["performance_ratio"].nullable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_salary_structure_performance_package_contract.py -q`
Expected: FAIL because `performance_package_amount` does not exist yet.

- [ ] **Step 3: Add minimal schema changes**

In `business.py` and `backend/schemas/hr.py`:
- add `performance_package_amount`
- keep `base_salary`, `position_salary`, allowances
- mark `performance_ratio` as legacy or remove it if the migration strategy is clean

- [ ] **Step 4: Write Alembic migration**

Add the new column and migrate current values conservatively. Do not drop legacy fields until all readers are migrated.

- [ ] **Step 5: Re-run contract test**

Run: `pytest backend/tests/test_salary_structure_performance_package_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/core/db/schema_parts/business.py backend/schemas/hr.py backend/tests/test_salary_structure_performance_package_contract.py migrations/versions
git commit -m "feat: add performance package to salary structure"
```

### Task 2: Add Dedicated Employee Performance Domain Model Inputs

**Files:**
- Modify: `modules/core/db/schema_parts/business.py`
- Modify: `backend/schemas/hr.py`
- Create: `backend/tests/test_employee_performance_domain_contract.py`
- Create: `migrations/versions/<timestamp>_employee_performance_domain.py`

- [ ] **Step 1: Write the failing domain contract test**

Cover these required concepts:
- employee score components are explicit
- employee performance can exist independently from store performance
- employee operation inputs are no longer piggybacked on generic `SalesTarget target_type=operation`

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_employee_performance_domain_contract.py -q`
Expected: FAIL because the dedicated employee-performance input model does not exist.

- [ ] **Step 3: Add new persistence model(s)**

Introduce explicit employee-side inputs, for example:
- `employee_performance_inputs`
- or a similarly named table that stores employee/month/metric/value/source

At minimum it must support:
- employee identifier
- year_month
- metric_code
- target_value
- achieved_value
- max_score
- direction
- optional manual score

- [ ] **Step 4: Add migration**

Create finance-safe / a_class-safe Alembic migration without deleting old target records yet.

- [ ] **Step 5: Re-run test**

Run: `pytest backend/tests/test_employee_performance_domain_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/core/db/schema_parts/business.py backend/schemas/hr.py backend/tests/test_employee_performance_domain_contract.py migrations/versions
git commit -m "feat: add dedicated employee performance input model"
```

### Task 3: Split Operation Targets Into Shop And Person Contracts

**Files:**
- Modify: `backend/schemas/target.py`
- Modify: `modules/core/db/schema_parts/business.py`
- Create: `backend/tests/test_operation_target_boundary_contract.py`
- Create: `migrations/versions/<timestamp>_split_operation_target_scope.py`

- [ ] **Step 1: Write the failing boundary contract test**

The test should assert:
- shop operation targets have an explicit shop scope
- employee operation targets have an explicit employee scope
- generic `target_type=operation` is no longer the long-term semantic boundary

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_operation_target_boundary_contract.py -q`
Expected: FAIL because operation target scope is still ambiguous.

- [ ] **Step 3: Implement explicit scope fields / models**

Choose one clean approach:
- add `scope_type = shop|employee`
- or split into separate tables / contracts

Document one source of truth and avoid dual meaning in one row.

- [ ] **Step 4: Add migration**

Backfill current shop operation targets into the new explicit scope.

- [ ] **Step 5: Re-run test**

Run: `pytest backend/tests/test_operation_target_boundary_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/target.py modules/core/db/schema_parts/business.py backend/tests/test_operation_target_boundary_contract.py migrations/versions
git commit -m "feat: make operation target scope explicit"
```

### Task 4: Rewrite Employee Performance Calculation To Stop Inheriting Store Totals As The Main Source

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: Write the failing calculation tests**

Add cases that prove:
- employee performance score can be computed with no store score present
- store score is not the primary employee score source
- attendance/manual adjustments still apply
- employee operation inputs contribute directly

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_hr_income_calculation_service.py -k "employee performance domain" -q`
Expected: FAIL because current logic still aggregates `PerformanceScore.total_score`.

- [ ] **Step 3: Implement minimal calculation rewrite**

Refactor `HRIncomeCalculationService.calculate_month()` so:
- employee performance reads dedicated employee inputs
- attendance/manual adjustments remain
- store score may remain as an optional responsibility weight, not the main score source

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_hr_income_calculation_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py
git commit -m "feat: decouple employee performance from store totals"
```

### Task 5: Rebuild Payroll Formula Around Performance Package

**Files:**
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/tests/test_payroll_generation_service.py`

- [ ] **Step 1: Write the failing payroll formula tests**

Cover:
- base salary stays fixed
- position salary stays fixed
- performance salary uses `performance_package_amount * employee_performance_coefficient`
- commission remains independent

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_payroll_generation_service.py -k "performance package" -q`
Expected: FAIL because payroll still uses `(base_salary + position_salary) * performance_ratio * performance_score / 100`.

- [ ] **Step 3: Implement minimal payroll formula change**

Replace the current performance salary formula with:

```python
performance_salary = performance_package_amount * employee_performance_coefficient
```

If coefficient is stored as a score, normalize explicitly.

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_payroll_generation_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/payroll_generation_service.py backend/tests/test_payroll_generation_service.py
git commit -m "feat: calculate payroll performance salary from performance package"
```

### Task 6: Adapt My Income And Monthly Settlement Readers To The New Payroll Semantics

**Files:**
- Modify: `backend/domains/business/routers/hr_employee.py`
- Modify: `backend/services/monthly_profit_settlement_service.py`
- Modify: `backend/tests/test_add_performance_income_acceptance.py`
- Modify: `backend/tests/test_monthly_profit_settlement_service.py`

- [ ] **Step 1: Write failing integration assertions if missing**

Ensure:
- My Income still reads payroll/snapshot only
- monthly settlement personnel cost still reads payroll total cost only
- no direct read from employee intermediate tables leaks into result layers

- [ ] **Step 2: Run tests to verify current gaps**

Run:
```bash
pytest backend/tests/test_add_performance_income_acceptance.py -k "my_income" backend/tests/test_monthly_profit_settlement_service.py -q
```
Expected: FAIL only if payroll semantics drift during formula rewrite.

- [ ] **Step 3: Update readers**

Keep them payroll-first while updating any labels or summary fields needed for the new fixed/performance split.

- [ ] **Step 4: Re-run tests**

Run the same command again.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/business/routers/hr_employee.py backend/services/monthly_profit_settlement_service.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_monthly_profit_settlement_service.py
git commit -m "feat: align readers with new payroll semantics"
```

### Task 7: Add Backend API Surface For Employee Performance Inputs

**Files:**
- Modify: `backend/domains/business/routers/hr_salary.py`
- Create or modify: `backend/domains/business/routers/hr_employee_performance.py` if cleaner
- Create: `backend/tests/test_employee_performance_input_routes.py`

- [ ] **Step 1: Write failing route tests**

Need routes for:
- list employee performance inputs
- create employee performance input
- update employee performance input
- delete / deactivate employee performance input

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_employee_performance_input_routes.py -q`
Expected: FAIL because routes do not exist yet.

- [ ] **Step 3: Implement minimal routes**

Keep the API scoped to employee performance inputs, not generic targets.

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_employee_performance_input_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/business/routers backend/tests/test_employee_performance_input_routes.py
git commit -m "feat: add employee performance input routes"
```

### Task 8: Update Frontend Pages To Use The New Contracts

**Files:**
- Modify: `frontend/src/domains/business/views/target/TargetPersonManagement.vue`
- Modify: `frontend/src/domains/business/views/target/TargetOperationManagement.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagement.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceDisplay.vue`
- Modify: `frontend/src/domains/business/views/hr/MyIncome.vue`
- Create tests under `frontend/scripts/`

- [ ] **Step 1: Write failing frontend script tests**

Cover:
- person target page uses dedicated employee performance input API, not generic employee targets forever
- operation page distinguishes shop/person scope clearly
- My Income explanation mentions performance package, not performance ratio on fixed salary

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd frontend && npm run test:target-route-split && npm run test:operation-target-formula && npm run test:my-income-view-model
```
Expected: FAIL where pages still mention old semantics.

- [ ] **Step 3: Implement frontend contract updates**

Update pages to reflect:
- dedicated employee target/performance input flow
- operation scope clarity
- payroll explanation clarity

- [ ] **Step 4: Re-run tests**

Run the same command again.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src frontend/scripts frontend/package.json
git commit -m "feat: align frontend pages with performance boundary redesign"
```

### Task 9: Documentation And Final Verification

**Files:**
- Modify: `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
- Modify: `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`
- Modify: `docs/系统使用说明书.md`
- Modify: `docs/系统使用说明书_一页速查.md`

- [ ] **Step 1: Update docs**

Document:
- final payroll formula
- employee performance no longer equals inherited store score
- operation target split
- shop/person frontend entrypoints

- [ ] **Step 2: Run final backend verification**

Run:
```bash
pytest backend/tests/test_salary_structure_performance_package_contract.py backend/tests/test_employee_performance_domain_contract.py backend/tests/test_operation_target_boundary_contract.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_payroll_generation_service.py backend/tests/test_add_performance_income_acceptance.py -q
```
Expected: PASS

- [ ] **Step 3: Run final frontend verification**

Run:
```bash
cd frontend && npm run test:target-route-split && npm run test:operation-target-formula && npm run test:performance-route-split && npm run test:my-income-view-model
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs: update payroll and performance boundary runbooks"
```
