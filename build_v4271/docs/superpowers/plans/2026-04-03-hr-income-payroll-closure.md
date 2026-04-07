# HR Income Payroll Closure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the payroll loop so performance and commission recalculation produces authoritative payroll records, and the my-income view reads only payroll.

**Architecture:** Keep `employee_commissions` and `employee_performance` as intermediate calculation tables, add a dedicated `PayrollGenerationService` to materialize authoritative `payroll_records`, and route all user-facing income reads through payroll. Reuse the existing HR payroll tab for draft editing and status transitions rather than introducing a new page.

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Pydantic, Vue 3, Element Plus, pytest

---

### Task 1: Lock the backend payroll behavior with failing tests

**Files:**
- Create: `backend/tests/test_payroll_generation_service.py`
- Modify: `backend/tests/test_add_performance_income_acceptance.py`

- [ ] **Step 1: Write failing tests for payroll generation**

Cover:
- recalculation writes payroll drafts
- draft preserves manual fields
- confirmed/paid payroll is not overwritten

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `pytest backend/tests/test_payroll_generation_service.py -v`

- [ ] **Step 3: Extend acceptance tests for `/performance/scores/calculate` and `/hr/me/income`**

Cover:
- response includes payroll counts
- my-income returns payroll-only result

- [ ] **Step 4: Run targeted tests to verify the new assertions fail**

Run: `pytest backend/tests/test_add_performance_income_acceptance.py -k "payroll or income" -v`

### Task 2: Implement backend payroll generation service

**Files:**
- Create: `backend/services/payroll_generation_service.py`
- Modify: `backend/services/__init__.py` if needed

- [ ] **Step 1: Implement payroll draft upsert logic**

Responsibilities:
- load salary structure, employee commission, employee performance
- calculate payroll fields
- preserve manual fields on existing draft rows
- detect locked rows for confirmed/paid

- [ ] **Step 2: Run payroll service tests**

Run: `pytest backend/tests/test_payroll_generation_service.py -v`

- [ ] **Step 3: Refine implementation until tests pass**

### Task 3: Wire payroll generation into performance recalculation

**Files:**
- Modify: `backend/routers/performance_management.py`

- [ ] **Step 1: Integrate `PayrollGenerationService` after income recalculation**

- [ ] **Step 2: Return `payroll_upserts` and `payroll_locked_conflicts`**

- [ ] **Step 3: Run targeted performance acceptance tests**

Run: `pytest backend/tests/test_add_performance_income_acceptance.py -k "calculate or payroll" -v`

### Task 4: Close backend payroll APIs

**Files:**
- Modify: `backend/routers/hr_salary.py`
- Modify: `backend/schemas/hr.py`

- [ ] **Step 1: Add payroll detail/update/confirm/reopen schemas if needed**

- [ ] **Step 2: Add payroll detail route**

- [ ] **Step 3: Add draft-only update route for manual fields**

- [ ] **Step 4: Add confirm and reopen routes**

- [ ] **Step 5: Write or extend route tests for status guardrails**

- [ ] **Step 6: Run targeted backend tests**

Run: `pytest backend/tests/test_payroll_generation_service.py backend/tests/test_add_performance_income_acceptance.py -v`

### Task 5: Make my-income payroll-only

**Files:**
- Modify: `backend/routers/hr_employee.py`
- Modify: `backend/schemas/hr.py`
- Modify: `backend/tests/test_add_performance_income_acceptance.py`

- [ ] **Step 1: Change `/api/hr/me/income` to read only payroll**

- [ ] **Step 2: Return empty-state payload when linked employee has no payroll**

- [ ] **Step 3: Set top-level income from `net_salary`**

- [ ] **Step 4: Run targeted tests**

Run: `pytest backend/tests/test_add_performance_income_acceptance.py -k "my_income" -v`

### Task 6: Update frontend API and screens

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/hr/MyIncome.vue`
- Modify: `frontend/src/views/HumanResources.vue`

- [ ] **Step 1: Add payroll detail/update/confirm/reopen API wrappers**

- [ ] **Step 2: Refactor `MyIncome.vue` to payroll-only presentation**

- [ ] **Step 3: Add draft editing and status actions in `HumanResources.vue` payroll tab**

- [ ] **Step 4: Validate build or lint target if available**

### Task 7: Verification and wrap-up

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run focused backend tests**

Run: `pytest backend/tests/test_payroll_generation_service.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_hr_income_calculation_service.py -v`

- [ ] **Step 2: Run any available frontend verification for modified files**

- [ ] **Step 3: Record results and residual risks in planning files**
