# Operating Costs Marketing Fee Physical Column Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Physically migrate the legacy `a_class.operating_costs` salary column naming to `marketing_fee` / `"营销费用"` across schema, SQL assets, backend runtime, and active docs without breaking the payroll domain.

**Architecture:** Treat this as a storage-layer rename limited to the `operating_costs` chain. Update the repository first so all active code and SQL point to the new physical name, add reversible migration scripts, then verify that expense management and dashboard cost aggregation still work. Do not touch payroll salary semantics outside this chain.

**Tech Stack:** PostgreSQL, SQLAlchemy ORM, FastAPI, Vue 3, Element Plus, repository SQL modules, pytest, Node test runner

---

## File Structure

- Modify: `modules/core/db/schema.py`
  Responsibility: rename the ORM mapping for `OperatingCost` from the legacy physical column to the new physical column while keeping the Python-side business meaning aligned with marketing spend.

- Modify: `backend/routers/expense_management.py`
  Responsibility: update active expense-management SQL to use the new physical column name and keep the public contract limited to `marketing_fee`.

- Modify: `backend/services/postgresql_dashboard_service.py`
  Responsibility: update fallback SQL that aggregates A-class operating costs.

- Modify: `sql/api_modules/business_overview_operational_metrics_module.sql`
  Responsibility: update API-module SQL to use the renamed column.

- Modify: `sql/mart/annual_summary_shop_month.sql`
  Responsibility: update mart aggregation SQL to use the renamed column.

- Modify: `sql/metabase_questions/business_overview_operational_metrics.sql`
  Responsibility: update active query SQL to use the renamed column.

- Modify: `sql/metabase_questions/annual_summary_trend.sql`
  Responsibility: update active query SQL to use the renamed column.

- Modify: `sql/metabase_questions/annual_summary_by_shop.sql`
  Responsibility: update active query SQL to use the renamed column.

- Create: `sql/migrations/2026-04-14_rename_operating_costs_salary_to_marketing_fee.sql`
  Responsibility: forward physical-column migration for the target environments.

- Create: `sql/migrations/2026-04-14_rollback_operating_costs_marketing_fee_to_salary.sql`
  Responsibility: rollback physical-column migration.

- Modify: `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`
  Responsibility: document the final post-migration physical naming.

- Modify: `docs/DEPLOYMENT_GUIDE.md`
  Responsibility: update deployment/bootstrap SQL examples and operational notes.

- Modify: `docs/PHASE3_COMPLETION_SUMMARY.md`
  Responsibility: align the active table summary with the post-migration column name.

- Modify: `docs/superpowers/specs/2026-04-03-postgresql-dashboard-calculation-audit-design.md`
  Responsibility: align active design references with the post-migration physical name.

- Test: `backend/tests/test_expense_management_compatibility.py`
  Responsibility: verify the public expense-management chain no longer exposes legacy field names.

- Test: `backend/tests/test_expense_management_terminology.py`
  Responsibility: verify active terminology remains marketing-fee based.

- Test: `backend/tests/test_monthly_profit_settlement_service.py`
  Responsibility: protect the earlier monthly-settlement fix while touching nearby finance semantics.

- Test: `backend/tests/test_payroll_generation_service.py`
  Responsibility: confirm payroll salary semantics remain untouched.

- Test: `frontend/scripts/expenseManagementCompatibilityUi.test.mjs`
  Responsibility: verify the expense-management page only uses marketing-fee fields.

- Test: `frontend/scripts/expenseManagementTerminologyUi.test.mjs`
  Responsibility: verify marketing-fee terminology remains visible in the UI.

## Task 1: Lock Red Tests For Final Physical Naming

**Files:**
- Modify: `backend/tests/test_expense_management_compatibility.py`
- Modify: `frontend/scripts/expenseManagementCompatibilityUi.test.mjs`

- [ ] **Step 1: Tighten the failing tests**

Update the tests so they assert the active expense-management chain no longer contains:

- `salary: float` in the expense contract
- `total_salary` in the expense contract
- `"工资" as salary` style router aliases for public output
- front-end references to `row.salary` / `total_salary`

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest backend\tests\test_expense_management_compatibility.py -q
node --test frontend\scripts\expenseManagementCompatibilityUi.test.mjs
```

Expected: FAIL because the repository still contains legacy physical/public naming in active code.

- [ ] **Step 3: Commit the test-only red state**

```powershell
git add backend/tests/test_expense_management_compatibility.py frontend/scripts/expenseManagementCompatibilityUi.test.mjs
git commit -m "test: lock marketing fee physical rename expectations"
```

## Task 2: Rename The ORM Mapping

**Files:**
- Modify: `modules/core/db/schema.py`

- [ ] **Step 1: Write/extend a failing schema contract assertion if needed**

If no focused test exists for the `OperatingCost` mapping, add or extend one so the mapping expectation is explicit.

- [ ] **Step 2: Run the focused test to verify it fails**

Run the smallest relevant schema contract or grep-based test.

- [ ] **Step 3: Change the ORM mapping to the new physical column**

Update `OperatingCost` so the physical mapped column becomes `"营销费用"` (or `marketing_fee` in the English-column path if present) while preserving the Python-facing responsibility within the operating-cost chain.

- [ ] **Step 4: Run the focused schema test again**

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add modules/core/db/schema.py
git commit -m "refactor: rename operating cost salary mapping to marketing fee"
```

## Task 3: Update Expense Management Backend SQL

**Files:**
- Modify: `backend/routers/expense_management.py`
- Modify: `backend/schemas/expense.py`
- Test: `backend/tests/test_expense_management_compatibility.py`
- Test: `backend/tests/test_expense_management_terminology.py`

- [ ] **Step 1: Write or refine failing backend tests**

Make the compatibility test assert that:

- expense contract exposes only `marketing_fee` / `total_marketing_fee`
- router public payloads do not expose legacy `salary` / `total_salary`

- [ ] **Step 2: Run backend tests to verify they fail**

Run:

```powershell
python -m pytest backend\tests\test_expense_management_compatibility.py backend\tests\test_expense_management_terminology.py -q
```

Expected: FAIL because router SQL and contract still reference legacy naming.

- [ ] **Step 3: Update the backend implementation**

Change:

- request handling to use `marketing_fee`
- SQL aliases from legacy public output to `marketing_fee`
- summaries to emit `total_marketing_fee`
- insert/update parameter names to match the new physical column

Do not reintroduce `salary` into the public contract.

- [ ] **Step 4: Re-run backend tests**

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/expense_management.py backend/schemas/expense.py backend/tests/test_expense_management_compatibility.py backend/tests/test_expense_management_terminology.py
git commit -m "refactor: use marketing fee fields in expense management backend"
```

## Task 4: Update Expense Management Frontend

**Files:**
- Modify: `frontend/src/views/finance/ExpenseManagement.vue`
- Test: `frontend/scripts/expenseManagementCompatibilityUi.test.mjs`
- Test: `frontend/scripts/expenseManagementTerminologyUi.test.mjs`

- [ ] **Step 1: Tighten the UI test if needed**

Assert the page:

- binds table/edit state to `marketing_fee`
- uses `total_marketing_fee` in summaries
- contains no `row.salary` or `total_salary` references

- [ ] **Step 2: Run the UI tests to verify they fail**

Run:

```powershell
node --test frontend\scripts\expenseManagementCompatibilityUi.test.mjs frontend\scripts\expenseManagementTerminologyUi.test.mjs
```

Expected: FAIL because the page still has legacy field references.

- [ ] **Step 3: Update the page implementation**

Remove legacy fallback behavior in the expense-management chain and make the page use only:

- `marketing_fee`
- `total_marketing_fee`

- [ ] **Step 4: Re-run the UI tests**

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/finance/ExpenseManagement.vue frontend/scripts/expenseManagementCompatibilityUi.test.mjs frontend/scripts/expenseManagementTerminologyUi.test.mjs
git commit -m "refactor: remove legacy salary fields from expense management ui"
```

## Task 5: Update Dashboard Fallback And SQL Assets

**Files:**
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `sql/api_modules/business_overview_operational_metrics_module.sql`
- Modify: `sql/mart/annual_summary_shop_month.sql`
- Modify: `sql/metabase_questions/business_overview_operational_metrics.sql`
- Modify: `sql/metabase_questions/annual_summary_trend.sql`
- Modify: `sql/metabase_questions/annual_summary_by_shop.sql`

- [ ] **Step 1: Write a focused failing check**

Use grep or an existing SQL-focused test to assert these active files no longer reference the old physical operating-cost column.

- [ ] **Step 2: Run the focused check and verify it fails**

Expected: FAIL or grep hits on `salary` / `"工资"` in the operating-cost context.

- [ ] **Step 3: Update all active SQL**

Replace old physical-column references with the new physical name, preserving the same formulas:

```text
rent + marketing_fee + utilities + other_costs
```

and Chinese-column equivalents using `"营销费用"`.

- [ ] **Step 4: Re-run the focused check**

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add backend/services/postgresql_dashboard_service.py sql/api_modules/business_overview_operational_metrics_module.sql sql/mart/annual_summary_shop_month.sql sql/metabase_questions/business_overview_operational_metrics.sql sql/metabase_questions/annual_summary_trend.sql sql/metabase_questions/annual_summary_by_shop.sql
git commit -m "refactor: rename operating cost marketing fee references in sql assets"
```

## Task 6: Add Forward And Rollback Migration SQL

**Files:**
- Create: `sql/migrations/2026-04-14_rename_operating_costs_salary_to_marketing_fee.sql`
- Create: `sql/migrations/2026-04-14_rollback_operating_costs_marketing_fee_to_salary.sql`

- [ ] **Step 1: Write the forward migration**

The forward migration must defensively:

- detect whether the environment uses English or Chinese physical columns
- rename `salary` -> `marketing_fee` where present
- rename `"工资"` -> `"营销费用"` where present
- update comments if present

- [ ] **Step 2: Write the rollback migration**

Reverse the forward migration exactly.

- [ ] **Step 3: Review both scripts manually**

Check for:

- idempotency assumptions
- quoting correctness
- schema qualification
- rollback symmetry

- [ ] **Step 4: Commit**

```powershell
git add sql/migrations/2026-04-14_rename_operating_costs_salary_to_marketing_fee.sql sql/migrations/2026-04-14_rollback_operating_costs_marketing_fee_to_salary.sql
git commit -m "feat: add operating costs marketing fee rename migrations"
```

## Task 7: Update Active Documentation

**Files:**
- Modify: `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`
- Modify: `docs/DEPLOYMENT_GUIDE.md`
- Modify: `docs/PHASE3_COMPLETION_SUMMARY.md`
- Modify: `docs/superpowers/specs/2026-04-03-postgresql-dashboard-calculation-audit-design.md`

- [ ] **Step 1: Update docs to the final post-migration name**

Remove language that treats `salary` / `"工资"` as the active physical name. Make it explicit that the storage column is now `marketing_fee` / `"营销费用"` after migration.

- [ ] **Step 2: Review for contradictions**

Search the edited docs for stale expense-management salary wording.

- [ ] **Step 3: Commit**

```powershell
git add docs/COST_DATA_SOURCES_AND_DEFINITIONS.md docs/DEPLOYMENT_GUIDE.md docs/PHASE3_COMPLETION_SUMMARY.md docs/superpowers/specs/2026-04-03-postgresql-dashboard-calculation-audit-design.md
git commit -m "docs: align operating costs docs with marketing fee column rename"
```

## Task 8: Final Verification

**Files:**
- Modify if needed: any file above

- [ ] **Step 1: Run targeted backend tests**

```powershell
python -m pytest backend\tests\test_expense_management_compatibility.py backend\tests\test_expense_management_terminology.py backend\tests\test_monthly_profit_settlement_service.py backend\tests\test_payroll_generation_service.py -q
```

Expected: PASS

- [ ] **Step 2: Run targeted frontend tests**

```powershell
node --test frontend\scripts\expenseManagementCompatibilityUi.test.mjs frontend\scripts\expenseManagementTerminologyUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Run grep verification**

Run repository grep to confirm no active `operating_costs` chain still uses legacy public or physical naming, excluding archives if necessary.

- [ ] **Step 4: Inspect migration scripts and changed SQL**

Verify the final branch is ready for a maintenance-window execution.

- [ ] **Step 5: Commit any last fixes**

```powershell
git add -A
git commit -m "chore: finalize operating costs marketing fee physical rename prep"
```

## Task 9: Execution Handoff Notes

**Operational database step after merge:**

- Back up the target database
- Run the forward migration in a controlled maintenance window
- Re-run the validation checklist
- Keep the rollback migration available until verification completes

**Do not skip this sequence:**

1. merge repository changes
2. deploy code that expects the new physical name
3. execute DB migration in the intended environment
4. verify runtime behavior
5. only then consider the migration complete
