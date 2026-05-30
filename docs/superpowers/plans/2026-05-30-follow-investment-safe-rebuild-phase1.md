# Follow Investment Safe Rebuild Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the follow investment backend contract and the personal follow investment income page so they become pure downstream consumers and stop mutating upstream profit-basis or payroll/cost chains.

**Architecture:** Keep the existing finance tables and route URLs, but replace the follow-investment contract with explicit schemas, a tighter state machine, and a read-only personal income view. Frontend work is limited to the personal page in phase 1; the larger financial settlement center shell stays for phase 2.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Pinia, Vite, pytest

---

## File Structure

- Modify: `backend/schemas/follow_investment.py`
  Add complete request and response schemas for settlement list, detail, my-income, and status responses.
- Modify: `backend/domains/business/routers/follow_investment.py`
  Add explicit `response_model` declarations and normalize error/status behavior.
- Modify: `backend/services/follow_investment_service.py`
  Remove profit-basis writeback from settlement calculation path and formalize settlement state transitions.
- Modify: `frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue`
  Rebuild the page as a clean, read-only personal settlement view.
- Modify: `backend/tests/test_follow_investment_routes.py`
  Rebind tests to the real domain router/module contract and cover response models.
- Create or modify: `backend/tests/test_follow_investment_service.py`
  Add focused service tests for state machine and no-writeback guarantees.
- Create or modify: `backend/tests/test_follow_investment_personal_income_contract.py`
  Add focused contract tests for the personal view payload if no equivalent exists.
- Create or modify: `frontend/scripts/myFollowInvestmentIncomeView.test.mjs`
  Add page-level view-model or content-contract coverage if needed.

### Task 1: Lock the backend contract surface

**Files:**
- Modify: `backend/schemas/follow_investment.py`
- Modify: `backend/tests/test_follow_investment_routes.py`

- [ ] **Step 1: Write failing schema/route contract tests**

Add tests that assert the router returns typed envelopes for:
- settlement calculation
- settlement list
- settlement detail
- my-income
- approve / reopen status

- [ ] **Step 2: Run the targeted contract tests to verify failure**

Run: `pytest backend/tests/test_follow_investment_routes.py -q`
Expected: FAIL due to current drift and incomplete contract behavior.

- [ ] **Step 3: Expand `backend/schemas/follow_investment.py` with full response models**

Add explicit models for:
- settlement summary row
- settlement detail row
- settlement calculate payload
- my-income summary
- my-income item
- status payload
- envelope responses

- [ ] **Step 4: Run the targeted tests again**

Run: `pytest backend/tests/test_follow_investment_routes.py -q`
Expected: still FAIL, but now only on router/service behavior, not missing schema coverage.

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/follow_investment.py backend/tests/test_follow_investment_routes.py
git commit -m "feat: define follow investment response contracts"
```

### Task 2: Make the follow-investment router explicit and testable

**Files:**
- Modify: `backend/domains/business/routers/follow_investment.py`
- Modify: `backend/tests/test_follow_investment_routes.py`

- [ ] **Step 1: Write or update failing router tests for the real domain module**

Make the tests monkeypatch the domain router module path directly, not the legacy compatibility wrapper.

- [ ] **Step 2: Run the router tests to verify failure**

Run: `pytest backend/tests/test_follow_investment_routes.py -q`
Expected: FAIL because current test seam is still wrong.

- [ ] **Step 3: Add `response_model` and normalize route error mapping**

Update the domain router so each typed endpoint declares the corresponding response model and status mapping is consistent.

- [ ] **Step 4: Re-run the router tests**

Run: `pytest backend/tests/test_follow_investment_routes.py -q`
Expected: PASS or narrow remaining failures to service behavior only.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/business/routers/follow_investment.py backend/tests/test_follow_investment_routes.py
git commit -m "feat: formalize follow investment router responses"
```

### Task 3: Remove upstream mutation from settlement calculation

**Files:**
- Modify: `backend/services/follow_investment_service.py`
- Modify: `backend/tests/test_follow_investment_service.py`

- [ ] **Step 1: Write failing service tests for no-writeback behavior**

Add tests that prove:
- settlement calculation reads an existing basis instead of creating/updating `ShopProfitBasis`
- settlement calculation does not mutate payroll/cost-related upstream tables

- [ ] **Step 2: Run the focused service tests to verify failure**

Run: `pytest backend/tests/test_follow_investment_service.py -q`
Expected: FAIL because the current implementation writes back profit-basis data.

- [ ] **Step 3: Refactor `calculate_settlement()` to pure-consumer mode**

Use the already-confirmed profit basis as input. If the basis is missing, fail clearly rather than regenerate it inside follow-investment flow.

- [ ] **Step 4: Re-run the focused service tests**

Run: `pytest backend/tests/test_follow_investment_service.py -q`
Expected: PASS for no-writeback guarantees.

- [ ] **Step 5: Commit**

```bash
git add backend/services/follow_investment_service.py backend/tests/test_follow_investment_service.py
git commit -m "refactor: stop follow investment from mutating profit basis"
```

### Task 4: Formalize the settlement state machine

**Files:**
- Modify: `backend/services/follow_investment_service.py`
- Modify: `backend/tests/test_follow_investment_service.py`

- [ ] **Step 1: Write failing tests for legal and illegal state transitions**

Cover:
- `draft -> calculated`
- `calculated -> approved`
- `approved -> reopened`
- illegal duplicate approve
- illegal reopen from draft/calculated

- [ ] **Step 2: Run the focused state-machine tests**

Run: `pytest backend/tests/test_follow_investment_service.py -q`
Expected: FAIL because current transition handling is too permissive.

- [ ] **Step 3: Implement minimal transition guards**

Update service methods so invalid transitions return explicit errors and valid transitions preserve details consistently.

- [ ] **Step 4: Re-run the state-machine tests**

Run: `pytest backend/tests/test_follow_investment_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/follow_investment_service.py backend/tests/test_follow_investment_service.py
git commit -m "feat: add follow investment settlement state guards"
```

### Task 5: Rebuild the personal follow-investment income page

**Files:**
- Modify: `frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue`
- Create or modify: `frontend/scripts/myFollowInvestmentIncomeView.test.mjs`

- [ ] **Step 1: Write a failing UI contract or view-model test**

Assert that the page:
- uses readable Chinese copy
- renders estimated / approved / paid summaries
- stays read-only
- does not expose trial/approval actions

- [ ] **Step 2: Run the targeted frontend test**

Run: `node --test frontend/scripts/myFollowInvestmentIncomeView.test.mjs`
Expected: FAIL because the current page is corrupted and under-specified.

- [ ] **Step 3: Rewrite the Vue page with a focused read-only layout**

Implement:
- clean header and month filter
- summary cards
- settlement item table
- explicit empty/loading states
- corrected monetary formatting and field labels

- [ ] **Step 4: Re-run the targeted frontend test**

Run: `node --test frontend/scripts/myFollowInvestmentIncomeView.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue frontend/scripts/myFollowInvestmentIncomeView.test.mjs
git commit -m "feat: rebuild personal follow investment income page"
```

### Task 6: Prove phase-1 safety against upstream chains

**Files:**
- Modify: `backend/tests/test_follow_investment_service.py`
- Modify: `backend/tests/test_follow_investment_routes.py`

- [ ] **Step 1: Add focused regression tests for protected boundaries**

Add assertions that phase 1 does not:
- write `ShopProfitBasis`
- write payroll-related tables
- expose personal-page mutation actions

- [ ] **Step 2: Run the narrow backend verification suite**

Run: `pytest backend/tests/test_follow_investment_routes.py backend/tests/test_follow_investment_service.py -q`
Expected: PASS.

- [ ] **Step 3: Run the page verification**

Run: `node --test frontend/scripts/myFollowInvestmentIncomeView.test.mjs`
Expected: PASS.

- [ ] **Step 4: Record any remaining drift for phase 2**

Document remaining work around:
- `FinancialManagement.vue`
- `frontend/src/stores/finance.js`
- stale frontend settlement-center contract tests

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_follow_investment_routes.py backend/tests/test_follow_investment_service.py frontend/scripts/myFollowInvestmentIncomeView.test.mjs
git commit -m "test: lock safe rebuild boundaries for follow investment phase 1"
```

## Verification Notes

- Prefer narrow pytest targets over broad suites while phase 1 is in flight.
- Do not claim success unless route tests, service tests, and the targeted frontend test have fresh passing output.
- Do not change `PayrollRecord`, `EmployeeCommission`, `EmployeePerformance`, or `ShopProfitBasis` write behavior outside the explicit no-writeback constraint above.

## Handoff

Phase 1 ends when:

- follow-investment backend is a pure downstream consumer
- personal follow-investment page is rebuilt and readable
- tests protect the new boundary

Phase 2 can then focus on splitting `FinancialManagement.vue` and decomposing the oversized finance store without reopening the follow-investment contract.
