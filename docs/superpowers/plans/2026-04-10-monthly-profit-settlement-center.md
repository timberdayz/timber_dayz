# Monthly Profit Settlement Center Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a company-level monthly profit settlement center that summarizes monthly net profit, personnel cost, follow-investment income, and company retained income using a target-ratio plus actual-settlement workflow.

**Architecture:** Reuse existing shop-level `profit_basis_amount`, HR commission, payroll, and follow-investment modules as upstream sources. Add a dedicated monthly settlement aggregate model and service in the finance domain, then expose a single finance API and a single finance UI surface for rebuild, target-ratio editing, approval, and reopen. Keep performance coefficient governance out of this implementation wave and consume only finalized upstream payroll and settlement outputs.

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Pydantic, Vue 3, Element Plus, Pinia, pytest

---

### Task 1: Lock the monthly settlement contract with failing tests

**Files:**
- Create: `backend/tests/test_monthly_profit_settlement_service.py`
- Create: `backend/tests/test_monthly_profit_settlement_routes.py`
- Modify: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Write the failing service tests for monthly settlement aggregation**

Cover:
- monthly net profit comes from aggregated `profit_basis_amount`
- personnel actual amount includes shop commission plus payroll total cost
- follow actual amount comes from approved follow-investment settlements
- company actual amount is net profit minus personnel, follow, and adjustments
- target ratios derive target amounts

```python
async def test_build_monthly_settlement_aggregates_company_totals():
    payload = await service.rebuild_month("2026-04")
    assert payload["summary"]["net_profit_amount"] == 100000.0
    assert payload["summary"]["personnel_actual_amount"] == 32000.0
    assert payload["summary"]["follow_actual_amount"] == 18000.0
    assert payload["summary"]["company_actual_amount"] == 50000.0
```

- [ ] **Step 2: Run the targeted service tests to verify they fail**

Run: `python -m pytest backend/tests/test_monthly_profit_settlement_service.py -q`
Expected: FAIL because the settlement service and models do not exist yet.

- [ ] **Step 3: Write the failing route tests for get, rebuild, update-targets, approve, and reopen**

Cover:
- `GET /api/finance/monthly-profit-settlement`
- `POST /api/finance/monthly-profit-settlement/rebuild`
- `PUT /api/finance/monthly-profit-settlement/{id}/targets`
- `POST /api/finance/monthly-profit-settlement/{id}/approve`
- `POST /api/finance/monthly-profit-settlement/{id}/reopen`

- [ ] **Step 4: Run the targeted route tests to verify they fail**

Run: `python -m pytest backend/tests/test_monthly_profit_settlement_routes.py -q`
Expected: FAIL because the routes are not registered yet.

- [ ] **Step 5: Extend the finance schema contract tests with the new monthly settlement tables**

Add expected table names and foreign-key expectations for:
- `monthly_profit_settlements`
- `monthly_profit_personnel_details`
- `monthly_profit_follow_details`
- `monthly_profit_adjustments`

- [ ] **Step 6: Run the schema contract tests to verify they fail**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py -q`
Expected: FAIL because the ORM models are missing.

### Task 2: Add finance ORM models for company monthly settlement

**Files:**
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Add the `MonthlyProfitSettlement` ORM model**

Fields:
- `period_month`
- `net_profit_amount`
- `personnel_target_ratio`
- `follow_target_ratio`
- `company_target_ratio`
- `personnel_target_amount`
- `follow_target_amount`
- `company_target_amount`
- `personnel_actual_amount`
- `follow_actual_amount`
- `company_actual_amount`
- `adjustment_amount`
- `difference_amount`
- `difference_ratio`
- `status`
- `locked_at`
- `approved_by`
- `approved_at`
- `remark`

- [ ] **Step 2: Add the `MonthlyProfitPersonnelDetail` ORM model**

Fields:
- `settlement_id`
- `detail_type`
- `employee_code`
- `platform_code`
- `shop_id`
- `source_module`
- `source_record_id`
- `amount`
- `remark`

- [ ] **Step 3: Add the `MonthlyProfitFollowDetail` ORM model**

Fields:
- `settlement_id`
- `investor_user_id`
- `source_settlement_id`
- `amount`
- `status`
- `remark`

- [ ] **Step 4: Add the `MonthlyProfitAdjustment` ORM model**

Fields:
- `settlement_id`
- `adjustment_type`
- `amount`
- `reason`
- `created_by`

- [ ] **Step 5: Add uniqueness and indexes**

Required:
- unique key on `period_month` in `monthly_profit_settlements`
- index on `status`
- indexes on all detail-table foreign keys

- [ ] **Step 6: Run the schema contract tests until they pass**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add modules/core/db/schema.py backend/tests/test_finance_schema_contract.py
git commit -m "feat: add monthly profit settlement models"
```

### Task 3: Add finance Pydantic schemas for the settlement center

**Files:**
- Create: `backend/schemas/monthly_profit_settlement.py`
- Modify: `backend/schemas/__init__.py` only if the package exports are maintained centrally

- [ ] **Step 1: Add summary and detail response schemas**

Need:
- settlement summary schema
- personnel detail schema
- follow detail schema
- adjustment schema

- [ ] **Step 2: Add rebuild and target-update request schemas**

Need:
- `MonthlyProfitSettlementRebuildRequest`
- `MonthlyProfitSettlementTargetsUpdateRequest`

- [ ] **Step 3: Add approve and reopen response schemas if route typing needs them**

- [ ] **Step 4: Run lightweight import validation**

Run: `python - <<'PY'\nfrom backend.schemas.monthly_profit_settlement import MonthlyProfitSettlementResponse\nprint(MonthlyProfitSettlementResponse.__name__)\nPY`
Expected: prints `MonthlyProfitSettlementResponse`

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/monthly_profit_settlement.py backend/schemas/__init__.py
git commit -m "feat: add monthly profit settlement schemas"
```

### Task 4: Implement the monthly settlement aggregation service

**Files:**
- Create: `backend/services/monthly_profit_settlement_service.py`
- Modify: `backend/services/__init__.py` only if local service exports are used
- Test: `backend/tests/test_monthly_profit_settlement_service.py`

- [ ] **Step 1: Implement company-level net profit aggregation from monthly `profit_basis_amount`**

Source:
- `ShopProfitBasis` rows for the requested `period_month`

Rule:

```python
net_profit_amount = sum(float(row.profit_basis_amount or 0) for row in profit_basis_rows)
```

- [ ] **Step 2: Implement personnel actual aggregation**

Sources:
- `GET`-equivalent internal logic behind HR shop commission totals
- `PayrollRecord.total_cost` for the requested month

First-wave rule:
- keep company-level payroll totals as company-level personnel cost
- do not back-allocate payroll totals to shops yet

- [ ] **Step 3: Implement follow actual aggregation**

Source:
- `FollowInvestmentSettlement`

First-wave rule:
- use `approved` settlements as the official monthly follow actual amount
- ignore `draft` and `calculated`

- [ ] **Step 4: Implement target ratio handling**

Rules:

```python
personnel_target_amount = net_profit_amount * personnel_target_ratio
follow_target_amount = net_profit_amount * follow_target_ratio
company_target_amount = net_profit_amount * company_target_ratio
```

Validate:
- target ratios sum to `1.0`

- [ ] **Step 5: Implement actual and difference calculations**

Rules:

```python
company_actual_amount = net_profit_amount - personnel_actual_amount - follow_actual_amount - adjustment_amount
difference_amount = company_target_amount - company_actual_amount
```

Also compute actual ratios and difference ratio with divide-by-zero guards.

- [ ] **Step 6: Implement rebuild persistence**

Behavior:
- create or update one settlement row per `period_month`
- refresh detail rows on rebuild
- preserve approved state only when explicitly reopened or rejected by policy

- [ ] **Step 7: Run the targeted service tests until they pass**

Run: `python -m pytest backend/tests/test_monthly_profit_settlement_service.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/monthly_profit_settlement_service.py backend/tests/test_monthly_profit_settlement_service.py
git commit -m "feat: add monthly profit settlement aggregation service"
```

### Task 5: Add finance routes for the monthly settlement center

**Files:**
- Create: `backend/domains/business/routers/monthly_profit_settlement.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_monthly_profit_settlement_routes.py`

- [ ] **Step 1: Add the settlement router with finance-role protection**

Prefix:
- `/api/finance/monthly-profit-settlement`

Reuse the same finance-role gate style used by:
- `backend/domains/business/routers/profit_basis.py`
- `backend/domains/business/routers/follow_investment.py`

- [ ] **Step 2: Add the GET route for month query**

Shape:
- `GET /api/finance/monthly-profit-settlement?period_month=YYYY-MM`

- [ ] **Step 3: Add the rebuild route**

Shape:
- `POST /api/finance/monthly-profit-settlement/rebuild`

- [ ] **Step 4: Add the targets update route**

Shape:
- `PUT /api/finance/monthly-profit-settlement/{settlement_id}/targets`

- [ ] **Step 5: Add approve and reopen routes**

Shapes:
- `POST /api/finance/monthly-profit-settlement/{settlement_id}/approve`
- `POST /api/finance/monthly-profit-settlement/{settlement_id}/reopen`

- [ ] **Step 6: Reuse `success_response` and keep typed `response_model` declarations**

- [ ] **Step 7: Run the targeted route tests until they pass**

Run: `python -m pytest backend/tests/test_monthly_profit_settlement_routes.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/domains/business/routers/monthly_profit_settlement.py backend/main.py backend/tests/test_monthly_profit_settlement_routes.py
git commit -m "feat: add monthly profit settlement routes"
```

### Task 6: Add frontend finance API and store support

**Files:**
- Modify: `frontend/src/api/finance.js`
- Modify: `frontend/src/stores/finance.js`

- [ ] **Step 1: Add finance API helpers for monthly settlement**

Need:
- `getMonthlyProfitSettlement`
- `rebuildMonthlyProfitSettlement`
- `updateMonthlyProfitSettlementTargets`
- `approveMonthlyProfitSettlement`
- `reopenMonthlyProfitSettlement`

- [ ] **Step 2: Add finance store state**

Need store branches for:
- `monthlyProfitSettlement`
- `monthlyProfitSettlementAction`

- [ ] **Step 3: Add finance store actions**

Implement:
- fetch
- rebuild
- update targets
- approve
- reopen

- [ ] **Step 4: Add store reset handling**

Ensure finance reset actions clear the new settlement state.

- [ ] **Step 5: Run a targeted frontend smoke check**

Check:
- imports resolve
- no obvious duplicate keys or syntax issues

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/finance.js frontend/src/stores/finance.js
git commit -m "feat: add finance client support for monthly settlement center"
```

### Task 7: Add the monthly settlement center UI to finance management

**Files:**
- Modify: `frontend/src/domains/business/views/FinancialManagement.vue`
- Optionally create: `frontend/src/components/finance/MonthlyProfitSettlementSummary.vue`
- Optionally create: `frontend/src/components/finance/MonthlyProfitSettlementDetails.vue`

- [ ] **Step 1: Write a focused UI contract test if the repo already uses simple source-based UI assertions**

Possible contract:
- page contains a tab or section labeled `月度利润结算中心`
- page shows cards for `月度净利润`, `人员成本`, `跟投收益`, `公司留存`

- [ ] **Step 2: Run the UI contract test to verify it fails**

Run: `python -m pytest backend/tests/test_follow_investment_menu_contract.py -q`
Expected: extend or add an equivalent frontend contract test and observe failure.

- [ ] **Step 3: Add the month selector and settlement actions**

Need:
- month selector
- rebuild button
- approve button
- reopen button

- [ ] **Step 4: Add the four summary cards**

Show:
- net profit
- personnel actual
- follow actual
- company actual

- [ ] **Step 5: Add the target-ratio editor**

Fields:
- personnel target ratio
- follow target ratio
- company target ratio

Guardrail:
- show inline error when sum is not 100%

- [ ] **Step 6: Add the difference and adjustment section**

Show:
- target amount
- actual amount
- difference amount
- difference ratio
- adjustment amount

- [ ] **Step 7: Add the personnel and follow detail tables**

Need:
- personnel detail grouped by `detail_type`
- follow detail grouped by investor or source settlement

- [ ] **Step 8: Keep the existing profit-basis and follow-investment tabs intact**

Do not fold existing shop-level tools into the new monthly settlement center in this wave.

- [ ] **Step 9: Run the frontend verification available in the repo**

If no build or test target is available, at minimum verify imports and template syntax manually.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/domains/business/views/FinancialManagement.vue frontend/src/components/finance
git commit -m "feat: add monthly profit settlement center UI"
```

### Task 8: Add approval, reopen, and status guardrails

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py`
- Modify: `backend/domains/business/routers/monthly_profit_settlement.py`
- Test: `backend/tests/test_monthly_profit_settlement_service.py`
- Test: `backend/tests/test_monthly_profit_settlement_routes.py`

- [ ] **Step 1: Implement settlement statuses**

Use:
- `draft`
- `approved`
- `locked`

First-wave simplification:
- `approve` transitions `draft -> approved`
- `reopen` transitions `approved -> draft`
- `locked` can be reserved for later if finance wants an explicit final close state

- [ ] **Step 2: Prevent target updates on approved rows**

- [ ] **Step 3: Prevent rebuild from silently overwriting approved rows**

Policy:
- require explicit reopen first

- [ ] **Step 4: Record approver and approval time**

- [ ] **Step 5: Run the targeted backend tests until they pass**

Run: `python -m pytest backend/tests/test_monthly_profit_settlement_service.py backend/tests/test_monthly_profit_settlement_routes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/monthly_profit_settlement_service.py backend/domains/business/routers/monthly_profit_settlement.py backend/tests/test_monthly_profit_settlement_service.py backend/tests/test_monthly_profit_settlement_routes.py
git commit -m "feat: add monthly settlement status guardrails"
```

### Task 9: Document the operational flow and residual governance boundaries

**Files:**
- Modify: `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
- Create: `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`
- Modify: `docs/系统使用说明书.md`
- Modify: `docs/系统使用说明书_一页速查.md`

- [ ] **Step 1: Add the new monthly settlement flow to the finance and HR runbooks**

Document:
- recommended monthly order of operations
- what each upstream module must be checked for
- when finance should reopen versus adjust

- [ ] **Step 2: Document that performance coefficient governance is out of scope for this wave**

- [ ] **Step 3: Document the first-wave business rule for follow actual amount**

Rule:
- approved follow-investment settlements count
- draft settlements do not

- [ ] **Step 4: Review docs for consistency with the design spec**

- [ ] **Step 5: Commit**

```bash
git add docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md docs/系统使用说明书.md docs/系统使用说明书_一页速查.md
git commit -m "docs: add monthly profit settlement operations guidance"
```

### Task 10: Run focused verification and capture rollout risks

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run focused backend verification**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py backend/tests/test_monthly_profit_settlement_service.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py backend/tests/test_hr_payroll_routes.py backend/tests/test_payroll_generation_service.py -q`
Expected: PASS

- [ ] **Step 2: Run any available frontend verification for modified finance files**

Run the repo-standard frontend verification command if available. If unavailable, record that limitation explicitly.

- [ ] **Step 3: Manually verify the end-to-end monthly sequence**

Check:
- rebuild month
- update target ratios
- approve
- reopen
- approved rows resist rebuild and update

- [ ] **Step 4: Record residual risks**

At minimum capture:
- payroll totals are company-level only in wave 1
- performance coefficient remains governed by existing inconsistent logic
- no shop back-allocation for payroll totals in wave 1

- [ ] **Step 5: Commit**

```bash
git add progress.md findings.md task_plan.md
git commit -m "chore: record monthly settlement verification evidence"
```

