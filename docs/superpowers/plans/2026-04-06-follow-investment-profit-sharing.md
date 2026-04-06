# Follow Investment Profit Sharing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a follow-investment profit sharing workflow that reuses the existing monthly finance stack, shop-level profit basis, A-class cost allocation, and finance management entrypoints.

**Architecture:** Keep the current profit and cost pipeline as the single source of truth, add three finance-side tables for follow-investment principal and monthly settlement data, and hang the new UX off the existing finance management screen. The settlement engine must read the current `period_month + platform_code + shop_id` finance basis, calculate weighted-capital ratios, and write auditable settlement records without redefining P&L.

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Pydantic, Vue 3, Element Plus, pytest

---

### Task 1: Confirm the profit basis source and lock the calculation contract

**Files:**
- Modify: `docs/superpowers/specs/2026-04-06-follow-investment-profit-sharing-design.md`
- Test: `backend/tests/test_follow_investment_service.py`

- [ ] **Step 1: Inspect the existing profit basis fields and confirm whether `contribution_profit` already includes A-class costs**

Check:
- `backend/services/postgresql_dashboard_service.py`
- SQL modules behind shop-level finance outputs

- [ ] **Step 2: Write the failing backend tests for profit-basis selection**

Cover:
- direct reuse of `contribution_profit`
- fallback to `orders_profit - a_class_cost_total`
- negative profit clamps distributable amount to zero

- [ ] **Step 3: Run the targeted tests to verify they fail**

Run: `python -m pytest backend/tests/test_follow_investment_service.py -q`

### Task 2: Add finance follow-investment persistence models

**Files:**
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Add `finance_follow_investments` ORM model**

- [ ] **Step 2: Add `finance_follow_investment_settlements` ORM model**

- [ ] **Step 3: Add `finance_follow_investment_details` ORM model**

- [ ] **Step 4: Add indexes and foreign keys aligned with existing finance tables**

- [ ] **Step 5: Run the finance schema contract tests**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py -q`

### Task 3: Define follow-investment request and response schemas

**Files:**
- Create: `backend/schemas/follow_investment.py`

- [ ] **Step 1: Add follow-investment principal create/update/list schemas**

- [ ] **Step 2: Add settlement calculate/list/detail schemas**

- [ ] **Step 3: Add personal income response schemas**

### Task 4: Implement the settlement service

**Files:**
- Create: `backend/services/follow_investment_service.py`
- Modify: `backend/services/postgresql_dashboard_service.py` only if a thin reusable profit-basis query helper is needed
- Test: `backend/tests/test_follow_investment_service.py`

- [ ] **Step 1: Implement principal lookup for a shop and month**

- [ ] **Step 2: Implement occupied-days and weighted-capital calculation**

- [ ] **Step 3: Implement settlement calculation from the existing finance basis**

- [ ] **Step 4: Persist settlement header and detail rows**

- [ ] **Step 5: Run the service tests until they pass**

Run: `python -m pytest backend/tests/test_follow_investment_service.py -q`

### Task 5: Add finance follow-investment routes

**Files:**
- Create: `backend/routers/follow_investment.py`
- Modify: `backend/routers/__init__.py` or the main router registration site
- Test: `backend/tests/test_follow_investment_routes.py`

- [ ] **Step 1: Add CRUD routes for follow-investment principal records**

- [ ] **Step 2: Add settlement calculate route**

- [ ] **Step 3: Add settlement list/detail/approve/mark-paid routes**

- [ ] **Step 4: Add current-user income route**

- [ ] **Step 5: Reuse `approval_logs` when approving settlements**

- [ ] **Step 6: Run route tests**

Run: `python -m pytest backend/tests/test_follow_investment_routes.py -q`

### Task 6: Add frontend finance API bindings

**Files:**
- Modify: `frontend/src/api/finance.js`

- [ ] **Step 1: Add principal list/create/update helpers**

- [ ] **Step 2: Add settlement calculate/list/approve/pay helpers**

- [ ] **Step 3: Add current-user income helper**

### Task 7: Extend the finance management screen

**Files:**
- Modify: `frontend/src/views/FinanceManagement.vue`
- Optionally create: `frontend/src/components/finance/FollowInvestment*.vue` if the view becomes too large

- [ ] **Step 1: Add the `跟投收益` tab**

- [ ] **Step 2: Add the `跟投记录` section**

- [ ] **Step 3: Add the `月度试算` section**

- [ ] **Step 4: Add the `结算台账` section**

- [ ] **Step 5: Keep existing finance tabs unchanged**

### Task 8: Add a personal “my follow-investment income” surface

**Files:**
- Modify: `frontend/src/router/index.js`
- Create or modify: `frontend/src/views/hr/MyFollowInvestmentIncome.vue`

- [ ] **Step 1: Add a route for current-user follow-investment income**

- [ ] **Step 2: Implement a read-only page for current-user settlement history**

- [ ] **Step 3: Ensure the page only shows the logged-in user’s own data**

### Task 9: Verification and documentation

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run focused backend verification**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py backend/tests/test_postgresql_dashboard_b_cost_routes.py backend/tests/test_follow_investment_service.py backend/tests/test_follow_investment_routes.py -q`

- [ ] **Step 2: Run any available frontend verification for modified finance files**

- [ ] **Step 3: Record the final evidence and residual risks in the planning files**
