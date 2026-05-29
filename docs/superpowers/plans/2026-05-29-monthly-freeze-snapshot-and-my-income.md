# Monthly Freeze Snapshot And My Income Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add monthly settlement freeze snapshots for approved months and align “我的收入” to use clear payroll-first result display with explainable source layers.

**Architecture:** Keep runtime calculation tables (`shop_profit_basis`, `employee_commissions`, `employee_performance`, `payroll_records`) mutable for draft/recalculation flows. On monthly settlement approval, persist versioned snapshot rows for the approved month and make approved settlement reads prefer snapshots. Then refine “我的收入” to expose payroll result cards plus source explanations without reassembling income from intermediate tables.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, PostgreSQL/Alembic, Vue 3, Element Plus, Node built-in test runner, pytest

---

### Task 1: Add Failing Backend Schema Contract Tests For Snapshot Tables

**Files:**
- Create: `backend/tests/test_monthly_profit_snapshot_schema_contract.py`
- Modify: `modules/core/db/schema_parts/business.py`
- Modify: `backend/schemas/monthly_profit_settlement.py`

- [ ] **Step 1: Write the failing schema contract tests**

```python
def test_monthly_profit_snapshot_tables_exist():
    from modules.core.db import (
        MonthlyProfitShopBasisSnapshot,
        MonthlyProfitEmployeeCommissionSnapshot,
        MonthlyProfitEmployeePerformanceSnapshot,
        MonthlyProfitPayrollSnapshot,
    )

    assert MonthlyProfitShopBasisSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeeCommissionSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeePerformanceSnapshot.__table__.schema == "finance"
    assert MonthlyProfitPayrollSnapshot.__table__.schema == "finance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_monthly_profit_snapshot_schema_contract.py -q`
Expected: FAIL because snapshot ORM models do not exist yet.

- [ ] **Step 3: Add the minimal ORM models**

Add four finance-schema ORM tables in `modules/core/db/schema_parts/business.py`:
- `monthly_profit_shop_basis_snapshots`
- `monthly_profit_employee_commission_snapshots`
- `monthly_profit_employee_performance_snapshots`
- `monthly_profit_payroll_snapshots`

Each table must include:
- `settlement_id`
- `period_month`
- `snapshot_version`
- `snapshot_status`
- audit fields

Also add narrow unique indexes described in the approved spec.

- [ ] **Step 4: Expose any response schema additions**

Add snapshot-oriented response models only if route/service typing needs them. Do not over-model unused payloads.

- [ ] **Step 5: Re-run tests**

Run: `pytest backend/tests/test_monthly_profit_snapshot_schema_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_monthly_profit_snapshot_schema_contract.py modules/core/db/schema_parts/business.py backend/schemas/monthly_profit_settlement.py
git commit -m "feat: add monthly profit snapshot schema models"
```

### Task 2: Add Failing Service Tests For Approve/Reopen Snapshot Versioning

**Files:**
- Create: `backend/tests/test_monthly_profit_settlement_snapshot_service.py`
- Modify: `backend/services/monthly_profit_settlement_service.py`
- Modify: `modules/core/db/schema_parts/business.py`

- [ ] **Step 1: Write failing snapshot service tests**

Cover these behaviors:
- approve on `draft` creates snapshot rows with `snapshot_version=1` and marks settlement approved
- approve fails if snapshot persistence fails
- reopen on `approved` marks current snapshot rows `superseded` and reverts settlement to `draft`
- re-approve after reopen creates `snapshot_version=2`
- rebuild on approved settlement is rejected until reopen

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_monthly_profit_settlement_snapshot_service.py -q`
Expected: FAIL because snapshot lifecycle methods do not exist yet.

- [ ] **Step 3: Implement snapshot lifecycle methods**

In `backend/services/monthly_profit_settlement_service.py`, add focused methods:
- `build_settlement_snapshots(...)`
- `mark_active_snapshots_superseded(...)`
- `get_next_snapshot_version(...)`
- `load_settlement_detail(...)` snapshot-aware read helper

Rules:
- approval writes snapshots and settlement status in one transaction
- reopen never deletes history; it supersedes current active snapshot rows
- approved settlements reject rebuild and target mutation until reopened

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_monthly_profit_settlement_snapshot_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_monthly_profit_settlement_snapshot_service.py backend/services/monthly_profit_settlement_service.py
git commit -m "feat: add monthly settlement snapshot lifecycle"
```

### Task 3: Add Failing Route Tests For Snapshot-Aware Monthly Settlement Reads

**Files:**
- Modify: `backend/tests/test_monthly_profit_settlement_routes.py`
- Modify: `backend/domains/business/routers/monthly_profit_settlement.py`
- Modify: `backend/services/monthly_profit_settlement_service.py`

- [ ] **Step 1: Write failing route tests**

Add route tests for:
- approved settlement detail reads snapshot-backed response
- draft settlement detail reads runtime aggregation
- approve route creates snapshots
- reopen route supersedes active snapshots

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_monthly_profit_settlement_routes.py -q`
Expected: FAIL because routes still use non-snapshot behavior.

- [ ] **Step 3: Implement minimal router changes**

Update monthly settlement router to:
- delegate approve/reopen/read behavior to snapshot-aware service methods
- preserve existing permission and approval-center hooks
- avoid duplicating snapshot logic in the router

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_monthly_profit_settlement_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_monthly_profit_settlement_routes.py backend/domains/business/routers/monthly_profit_settlement.py backend/services/monthly_profit_settlement_service.py
git commit -m "feat: make monthly settlement routes snapshot-aware"
```

### Task 4: Add Migration And Database Verification For Snapshot Tables

**Files:**
- Create: `migrations/versions/<timestamp>_add_monthly_profit_snapshot_tables.py`
- Modify: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Write failing migration/schema verification tests**

Add contract checks that:
- new snapshot tables exist in `finance`
- foreign keys point to `finance.monthly_profit_settlements`
- unique constraints cover settlement/version/business keys

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_finance_schema_contract.py -q`
Expected: FAIL because migration not written yet.

- [ ] **Step 3: Write the Alembic migration**

Create the new snapshot tables with:
- proper schema
- indexes
- unique constraints
- `snapshot_status` defaults

Do not add unrelated refactors or data backfills in this migration.

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_finance_schema_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions backend/tests/test_finance_schema_contract.py
git commit -m "feat: add monthly profit snapshot migration"
```

### Task 5: Add Failing Backend Tests For My Income Snapshot-Aware Read Rules

**Files:**
- Modify: `backend/tests/test_hr_employee_my_income.py` or create if absent
- Modify: `backend/domains/business/routers/hr_employee.py`
- Modify: `backend/schemas/hr.py`

- [ ] **Step 1: Write failing My Income backend tests**

Cover:
- linked false behavior remains unchanged
- missing payroll returns empty state unchanged
- approved historical month prefers payroll snapshot when available
- current draft month still reads live `payroll_records`
- response omits stale top-level explanation fields or clearly deprecates them

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_hr_employee_my_income.py -q`
Expected: FAIL because `/me/income` is not snapshot-aware yet.

- [ ] **Step 3: Implement minimal backend changes**

In `hr_employee.py`:
- route approved historical months through payroll snapshot lookup
- preserve live payroll read for draft/current runtime paths
- keep response payroll-first

In `backend/schemas/hr.py`:
- either remove unused top-level explanation fields or document them as nullable/legacy only
- keep `breakdown.payroll` authoritative

- [ ] **Step 4: Re-run tests**

Run: `pytest backend/tests/test_hr_employee_my_income.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_hr_employee_my_income.py backend/domains/business/routers/hr_employee.py backend/schemas/hr.py
git commit -m "feat: make my income snapshot-aware"
```

### Task 6: Add Frontend Rule Tests And UI Enhancements For My Income Summary/Explanation

**Files:**
- Modify: `frontend/src/domains/business/views/hr/MyIncome.vue`
- Create: `frontend/src/domains/business/views/hr/myIncomeViewModel.js`
- Create: `frontend/scripts/myIncomeViewModel.test.mjs`

- [ ] **Step 1: Write the failing frontend view-model tests**

Cover:
- summary cards expose `net_salary`, fixed salary base, performance salary, and commission
- explanation blocks describe:
  - commission source
  - performance salary source
  - performance score source
- empty and linked-false states remain intact

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:my-income-view-model`
Expected: FAIL because helper module/script does not exist yet.

- [ ] **Step 3: Implement the helper and minimal UI changes**

Extract formatting/section-building logic into `myIncomeViewModel.js` and update `MyIncome.vue` to:
- show four summary cards:
  - 当月实发
  - 固定薪资
  - 绩效工资
  - 提成
- render a lightweight read-only explanation section
- keep payroll detail card as the authoritative breakdown

- [ ] **Step 4: Re-run tests**

Run: `cd frontend && npm run test:my-income-view-model`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/domains/business/views/hr/MyIncome.vue frontend/src/domains/business/views/hr/myIncomeViewModel.js frontend/scripts/myIncomeViewModel.test.mjs frontend/package.json
git commit -m "feat: clarify my income summary and explanation"
```

### Task 7: Update Runbooks And User-Facing Documentation

**Files:**
- Modify: `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`
- Modify: `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
- Modify: `docs/系统使用说明书.md`
- Modify: `docs/系统使用说明书_一页速查.md`

- [ ] **Step 1: Write failing doc contract checks if any exist**

If there are documentation contract tests, extend them first. Otherwise skip directly to doc updates.

- [ ] **Step 2: Update docs**

Document:
- approved month reads snapshot, draft reads runtime
- reopen semantics and version superseding
- “我的收入” now shows payroll-first result + explanation layer

- [ ] **Step 3: Run targeted verification**

Run:
```bash
pytest backend/tests/test_finance_schema_contract.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_hr_employee_my_income.py -q
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md docs/系统使用说明书.md docs/系统使用说明书_一页速查.md
git commit -m "docs: describe snapshot-based settlement and my income behavior"
```

### Task 8: Final Integration Verification

**Files:**
- Verify only

- [ ] **Step 1: Run backend integration checks**

Run:
```bash
pytest backend/tests/test_monthly_profit_snapshot_schema_contract.py backend/tests/test_monthly_profit_settlement_snapshot_service.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_hr_employee_my_income.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_hr_shop_assignment_rules.py backend/tests/test_hr_shop_assignment_dim_shop_autosync.py -q
```
Expected: all PASS

- [ ] **Step 2: Run frontend checks**

Run:
```bash
cd frontend && npm run test:shop-assignment-rules && npm run test:my-income-view-model
```
Expected: all PASS

- [ ] **Step 3: Run compile checks**

Run:
```bash
python -m py_compile backend/services/hr_income_calculation_service.py backend/domains/business/routers/hr_commission.py backend/domains/business/routers/hr_employee.py backend/services/monthly_profit_settlement_service.py backend/domains/business/routers/monthly_profit_settlement.py
```
Expected: no output, exit 0

- [ ] **Step 4: Commit final integration pass**

```bash
git add -A
git commit -m "chore: verify monthly snapshot and my income integration"
```
