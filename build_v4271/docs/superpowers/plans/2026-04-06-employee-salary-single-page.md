# Employee Salary Single-Page Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated HR-facing `员工薪资` page that unifies fixed salary maintenance, monthly manual payroll inputs, and payroll result/state handling without changing the employee-facing `我的收入` page.

**Architecture:** Reuse the existing HR payroll chain and add a new frontend page plus missing HR salary APIs. Keep `salary_structures` as the fixed-salary source of truth, keep `payroll_records` as the monthly manual-input and final payroll source of truth, and avoid introducing new salary-specific pages or new payroll states. Support salary-structure version history in application logic using existing `effective_date` and `status` fields instead of redesigning the table first.

**Tech Stack:** Vue 3 + Element Plus + Pinia + Vite, FastAPI, SQLAlchemy async, Pydantic, pytest, Node `node:test` UI source checks

---

## File Structure

### Backend

- Modify: `backend/schemas/hr.py`
  - Add request/response contracts for salary structure update/history and optional employee-salary aggregate responses.
- Modify: `backend/routers/hr_salary.py`
  - Expand salary structure APIs to support current config retrieval, version history retrieval, and versioned create/update behavior.
  - Add an employee-centric payroll refresh/read path if needed by the page.
- Modify: `backend/services/payroll_generation_service.py`
  - Add a focused method for single-employee, single-month payroll refresh or extraction if the page needs on-demand result refresh.
- Test: `backend/tests/test_hr_payroll_routes.py`
  - Extend for new route behavior and salary-structure version rules.
- Test: `backend/tests/test_payroll_generation_service.py`
  - Extend for employee/month refresh behavior and manual-field preservation rules.

### Frontend

- Create: `frontend/src/views/hr/EmployeeSalary.vue`
  - Main HR salary page.
- Modify: `frontend/src/router/index.js`
  - Add new route entry.
- Modify: `frontend/src/config/menuGroups.js`
  - Add menu item under human resources.
- Modify: `frontend/src/api/index.js`
  - Add frontend API helpers for new salary-structure and employee-salary flows.
- Optionally modify: `frontend/src/views/HumanResources.vue`
  - Reduce or reword the old payroll tab so it stops acting like the primary salary business entry.
- Test: `frontend/scripts/employeeSalaryUi.test.mjs`
  - Source-level assertions for the new page structure and labels.
- Test: `frontend/scripts/employeeSalaryRouteUi.test.mjs`
  - Source-level assertions for route/menu integration.

### Docs

- Modify: `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
  - Update HR operating entry point from mixed `HumanResources` payroll tab to dedicated `员工薪资` page.

---

### Task 1: Lock API Behavior For Salary Structures

**Files:**
- Modify: `backend/schemas/hr.py`
- Modify: `backend/routers/hr_salary.py`
- Test: `backend/tests/test_hr_payroll_routes.py`

- [ ] **Step 1: Write failing tests for salary structure current-record and history behavior**

Add tests covering:
- `GET /api/hr/salary-structures/{employee_code}` returns the currently effective structure, not an arbitrary row.
- New history endpoint returns multiple versions ordered newest-first.
- Creating a new salary structure version for an employee with existing records succeeds when the new version has a new `effective_date`.
- Updating the current salary structure in place remains allowed only when explicitly using the update route.

Suggested test names:
```python
def test_get_salary_structure_returns_current_effective_version():
    ...

def test_list_salary_structure_history_returns_versions_desc():
    ...

def test_create_salary_structure_allows_new_version_for_same_employee():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
pytest -q backend/tests/test_hr_payroll_routes.py
```

Expected:
- New tests fail because route behavior does not yet support current-version selection/history/versioned create.

- [ ] **Step 3: Add Pydantic contracts for salary structure version flows**

Implement in `backend/schemas/hr.py`:
- `SalaryStructureUpdate`
- `SalaryStructureHistoryResponse` or reuse `SalaryStructureResponse` as a list if no extra metadata is needed
- Any employee-salary aggregate contract only if required by the page

Keep fields aligned with existing `SalaryStructureCreate`.

- [ ] **Step 4: Implement salary structure route changes**

Implement in `backend/routers/hr_salary.py`:
- Keep `GET /api/hr/salary-structures`
- Change `GET /api/hr/salary-structures/{employee_code}` to select the current record using:
  - `status == "active"`
  - latest `effective_date` not in the future when multiple active rows exist
  - fallback to latest row if no active row matches
- Add `GET /api/hr/salary-structures/{employee_code}/history`
- Add `PUT /api/hr/salary-structures/{employee_code}` for in-place edit of the selected version
- Relax the current app-level duplicate rejection in `POST /api/hr/salary-structures` so multiple versions for one employee are allowed when they differ by `effective_date`

- [ ] **Step 5: Re-run backend route tests**

Run:
```powershell
pytest -q backend/tests/test_hr_payroll_routes.py
```

Expected:
- All route tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/hr.py backend/routers/hr_salary.py backend/tests/test_hr_payroll_routes.py
git commit -m "feat: support versioned hr salary structures"
```

---

### Task 2: Add Employee-Month Payroll Refresh API

**Files:**
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/routers/hr_salary.py`
- Test: `backend/tests/test_payroll_generation_service.py`
- Test: `backend/tests/test_hr_payroll_routes.py`

- [ ] **Step 1: Write failing tests for employee/month refresh**

Add tests covering:
- A single employee/month refresh recalculates automatic payroll fields from fixed salary + commission + performance.
- Existing draft manual fields (`bonus`, `overtime_pay`, deductions, remark) are preserved.
- `confirmed` and `paid` records are not overwritten.

Suggested test names:
```python
def test_refresh_employee_month_payroll_updates_auto_fields_only():
    ...

def test_refresh_employee_month_payroll_reports_locked_record():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
pytest -q backend/tests/test_payroll_generation_service.py backend/tests/test_hr_payroll_routes.py
```

Expected:
- New tests fail because no single-employee refresh path exists.

- [ ] **Step 3: Implement minimal service support**

In `backend/services/payroll_generation_service.py`:
- Extract or add a focused method such as `generate_employee_month(employee_code, year_month)`
- Reuse existing payload-building and lock-conflict logic
- Preserve manual fields on `draft`
- Return enough result data for the frontend to reload the employee/month payroll section

- [ ] **Step 4: Expose route for the page**

In `backend/routers/hr_salary.py` add a route like:
```python
@router.post("/payroll-records/{employee_code}/{year_month}/refresh")
```

Behavior:
- refresh a single employee/month payroll row
- return the latest payroll row payload
- surface lock-conflict details if the row is `confirmed` or `paid`

- [ ] **Step 5: Re-run targeted backend tests**

Run:
```powershell
pytest -q backend/tests/test_payroll_generation_service.py backend/tests/test_hr_payroll_routes.py
```

Expected:
- All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/payroll_generation_service.py backend/routers/hr_salary.py backend/tests/test_payroll_generation_service.py backend/tests/test_hr_payroll_routes.py
git commit -m "feat: add employee payroll refresh flow"
```

---

### Task 3: Add Frontend API Layer For Employee Salary Page

**Files:**
- Modify: `frontend/src/api/index.js`
- Test: `frontend/scripts/employeeSalaryRouteUi.test.mjs`

- [ ] **Step 1: Write failing frontend API assertions**

Create a new source-check script asserting that `frontend/src/api/index.js` exposes helpers for:
- salary structure history
- salary structure update
- employee/month payroll refresh

Suggested checks:
```js
assert.equal(apiSource.includes('async updateHrSalaryStructure('), true)
assert.equal(apiSource.includes('async getHrSalaryStructureHistory('), true)
assert.equal(apiSource.includes('async refreshHrPayrollRecord('), true)
```

- [ ] **Step 2: Run the script to verify failure**

Run:
```powershell
node --test frontend/scripts/employeeSalaryRouteUi.test.mjs
```

Expected:
- FAIL because the new helpers are not yet present.

- [ ] **Step 3: Implement frontend API helpers**

Add helpers in `frontend/src/api/index.js`:
- `getHrSalaryStructureHistory(employeeCode)`
- `updateHrSalaryStructure(employeeCode, data)`
- `refreshHrPayrollRecord(employeeCode, yearMonth)`

Keep naming aligned with existing `getHrSalaryStructure`, `createHrSalaryStructure`, `getHrPayrollRecord`, `updateHrPayrollRecord`.

- [ ] **Step 4: Re-run the frontend API assertions**

Run:
```powershell
node --test frontend/scripts/employeeSalaryRouteUi.test.mjs
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/index.js frontend/scripts/employeeSalaryRouteUi.test.mjs
git commit -m "feat: add frontend employee salary api helpers"
```

---

### Task 4: Add Dedicated Employee Salary Route And Menu Entry

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Test: `frontend/scripts/employeeSalaryRouteUi.test.mjs`

- [ ] **Step 1: Extend route/menu assertions with new expectations**

Add checks for:
- route path exists for the new page
- route component points to `../views/hr/EmployeeSalary.vue`
- route is listed under human resources menu group

Suggested assertions:
```js
assert.equal(routerSource.includes("path: '/employee-salary'"), true)
assert.equal(routerSource.includes("views/hr/EmployeeSalary.vue"), true)
assert.equal(menuSource.includes('/employee-salary'), true)
```

- [ ] **Step 2: Run the script to verify failure**

Run:
```powershell
node --test frontend/scripts/employeeSalaryRouteUi.test.mjs
```

Expected:
- FAIL because route/menu are missing.

- [ ] **Step 3: Add route and menu entry**

Modify:
- `frontend/src/router/index.js`
- `frontend/src/config/menuGroups.js`

Requirements:
- place under HR menu group
- keep `MyIncome` unchanged
- keep `HumanResources` route intact
- title should clearly distinguish HR business page from employee self-service page

- [ ] **Step 4: Re-run the route/menu script**

Run:
```powershell
node --test frontend/scripts/employeeSalaryRouteUi.test.mjs
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/index.js frontend/src/config/menuGroups.js frontend/scripts/employeeSalaryRouteUi.test.mjs
git commit -m "feat: add employee salary route"
```

---

### Task 5: Build Employee Salary Page

**Files:**
- Create: `frontend/src/views/hr/EmployeeSalary.vue`
- Modify: `frontend/src/api/index.js`
- Optionally modify: `frontend/src/views/HumanResources.vue`
- Test: `frontend/scripts/employeeSalaryUi.test.mjs`

- [ ] **Step 1: Write failing source-level UI tests**

Create `frontend/scripts/employeeSalaryUi.test.mjs` with assertions that the new page contains:
- employee list area
- fixed salary section
- monthly input section
- payroll result section
- labels for bottom-line fields like `底薪`, `岗位工资`, `月度奖金`, `实发工资`, `确认工资单`, `标记已发放`

Suggested assertions:
```js
assert.equal(source.includes('固定薪资'), true)
assert.equal(source.includes('月度录入'), true)
assert.equal(source.includes('工资单结果'), true)
assert.equal(source.includes('底薪'), true)
assert.equal(source.includes('月度奖金'), true)
```

- [ ] **Step 2: Run the script to verify failure**

Run:
```powershell
node --test frontend/scripts/employeeSalaryUi.test.mjs
```

Expected:
- FAIL because the page does not yet exist.

- [ ] **Step 3: Implement the page skeleton first**

Create `frontend/src/views/hr/EmployeeSalary.vue` with:
- left employee list
- right fixed salary card
- right monthly input card
- right payroll result card
- local state for selected employee and selected month
- page-level loading and empty states

Do not start with visual polish. Start with correct structure and data flow.

- [ ] **Step 4: Wire fixed salary APIs**

Implement page behavior:
- load current salary structure when selecting employee
- load salary history
- allow save current salary structure
- allow create new version with `effective_date`

- [ ] **Step 5: Wire monthly payroll APIs**

Implement page behavior:
- load payroll row for selected employee/month
- edit only manual fields
- refresh selected employee/month payroll
- confirm / reopen / pay using existing endpoints

- [ ] **Step 6: Re-run source-level UI tests**

Run:
```powershell
node --test frontend/scripts/employeeSalaryUi.test.mjs frontend/scripts/employeeSalaryRouteUi.test.mjs
```

Expected:
- PASS

- [ ] **Step 7: Optionally simplify old HumanResources payroll messaging**

If needed, update `frontend/src/views/HumanResources.vue` so:
- it no longer reads like the primary salary business page
- it can link or direct users to `员工薪资`

Only do this if it reduces ambiguity without destabilizing unrelated HR tabs.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/hr/EmployeeSalary.vue frontend/src/api/index.js frontend/src/views/HumanResources.vue frontend/scripts/employeeSalaryUi.test.mjs frontend/scripts/employeeSalaryRouteUi.test.mjs
git commit -m "feat: add employee salary management page"
```

---

### Task 6: Update HR Payroll Documentation

**Files:**
- Modify: `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`

- [ ] **Step 1: Update the runbook entry points**

Document:
- `员工薪资` is now the HR salary operations page
- `我的收入` remains employee self-service only
- `HumanResources` remains base HR management

- [ ] **Step 2: Update monthly operation instructions**

Clarify:
- fixed salary setup happens in `员工薪资`
- monthly bonus and deduction input happens in `员工薪资`
- payroll status actions happen in `员工薪资`

- [ ] **Step 3: Sanity-check docs**

Run:
```powershell
Select-String -Path docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md -Pattern '员工薪资|我的收入|HumanResources'
```

Expected:
- Updated terminology appears in the runbook.

- [ ] **Step 4: Commit**

```bash
git add docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md
git commit -m "docs: update hr payroll runbook for employee salary page"
```

---

### Task 7: Final Verification

**Files:**
- Verify all files changed above

- [ ] **Step 1: Run backend regression checks**

Run:
```powershell
pytest -q backend/tests/test_hr_payroll_routes.py backend/tests/test_payroll_generation_service.py
```

Expected:
- PASS

- [ ] **Step 2: Run frontend source-level checks**

Run:
```powershell
node --test frontend/scripts/employeeSalaryUi.test.mjs frontend/scripts/employeeSalaryRouteUi.test.mjs frontend/scripts/myIncomePayrollUi.test.mjs frontend/scripts/humanResourcesPayrollPaidUi.test.mjs
```

Expected:
- PASS

- [ ] **Step 3: Run lint-style verification for touched backend files**

Run:
```powershell
python -m ruff check backend/schemas/hr.py backend/routers/hr_salary.py backend/services/payroll_generation_service.py backend/tests/test_hr_payroll_routes.py backend/tests/test_payroll_generation_service.py
```

Expected:
- PASS

- [ ] **Step 4: Review the diff for scope control**

Run:
```powershell
git diff --stat HEAD~7..HEAD
git status --short
```

Expected:
- Only employee-salary page, HR salary API, tests, and runbook updates are in scope.

- [ ] **Step 5: Final commit if verification changes were needed**

```bash
git add -A
git commit -m "chore: finalize employee salary single-page rollout"
```

---

## Notes For Execution

- Prefer reusing existing `Employee`, `SalaryStructure`, and `PayrollRecord` data paths over inventing a new aggregate backend object unless the page truly needs one.
- Keep frontend implementation in Vue 3 + Element Plus patterns already used in the repo.
- Do not convert `MyIncome` into an editable page.
- Do not create separate `奖金管理`, `底薪管理`, or `工资条管理` pages.
- If the current backend route naming becomes ambiguous, improve names only where doing so does not create broad API churn.
