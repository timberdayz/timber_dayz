# Unified Profit Basis And Follow Investment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a single formal settlement profit basis (`profit_basis_amount`) and use it to support follow-investment profit sharing while preparing the system to converge other profit-distribution logic onto the same basis.

**Architecture:** Keep the current profit and cost pipeline as the single source of truth, add a monthly shop settlement-basis object that materializes `profit_basis_amount`, then build follow-investment settlement on top of it. Treat existing display-only profit fields as analysis references, not settlement truth. Route the new UX through the existing finance management screen and keep the resulting data auditable and month-locked.

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Pydantic, Vue 3, Element Plus, pytest

---

### Task 1: Lock the unified settlement profit contract

**Files:**
- Modify: `docs/superpowers/specs/2026-04-06-follow-investment-profit-sharing-design.md`
- Create: `backend/tests/test_profit_basis_service.py`

- [ ] **Step 1: Inspect the existing profit fields and define `profit_basis_amount` source rules**

Check:
- `backend/services/postgresql_dashboard_service.py`
- SQL modules behind shop-level finance outputs
- HR profit-distribution logic inputs

- [ ] **Step 2: Write the failing tests for unified profit-basis selection**

Cover:
- A-only basis calculation
- optional B-cost inclusion toggle
- negative profit clamps distributable amount to zero

- [ ] **Step 3: Run the targeted tests to verify they fail**

Run: `python -m pytest backend/tests/test_profit_basis_service.py -q`

### Task 2: Add the monthly shop settlement-basis persistence model

**Files:**
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Add a finance-side monthly `profit_basis` table/model**

- [ ] **Step 2: Add fields for `orders_profit_amount`, `a_class_cost_amount`, `b_class_cost_amount`, `profit_basis_amount`, `basis_version`, and lock status**

- [ ] **Step 3: Add unique key on the chosen monthly shop basis identity**

- [ ] **Step 4: Run the finance schema contract tests**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py -q`

### Task 3: Add finance follow-investment persistence models

**Files:**
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_finance_schema_contract.py`

- [ ] **Step 1: Add `finance_follow_investments` ORM model**

- [ ] **Step 2: Add `finance_follow_investment_settlements` ORM model**

- [ ] **Step 3: Add `finance_follow_investment_details` ORM model**

- [ ] **Step 4: Add indexes and foreign keys aligned with existing finance tables**

- [ ] **Step 5: Run the finance schema contract tests**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py -q`

### Task 4: Define unified profit-basis and follow-investment schemas

**Files:**
- Create: `backend/schemas/profit_basis.py`
- Create: `backend/schemas/follow_investment.py`

- [ ] **Step 1: Add monthly profit-basis response and rebuild request schemas**

- [ ] **Step 2: Add follow-investment principal create/update/list schemas**

- [ ] **Step 3: Add settlement calculate/list/detail schemas**

- [ ] **Step 4: Add personal income response schemas**

### Task 5: Implement the profit-basis service

**Files:**
- Create: `backend/services/profit_basis_service.py`
- Modify: `backend/services/postgresql_dashboard_service.py` only if thin reusable source queries are needed
- Test: `backend/tests/test_profit_basis_service.py`

- [ ] **Step 1: Implement source loading for orders profit, A-class cost, and optional B-cost**

- [ ] **Step 2: Implement `profit_basis_amount` calculation with explicit rule versioning**

- [ ] **Step 3: Persist or refresh monthly shop profit-basis snapshots**

- [ ] **Step 4: Run the profit-basis tests until they pass**

Run: `python -m pytest backend/tests/test_profit_basis_service.py -q`

### Task 6: Implement the follow-investment settlement service

**Files:**
- Create: `backend/services/follow_investment_service.py`
- Test: `backend/tests/test_follow_investment_service.py`

- [ ] **Step 1: Implement principal lookup for a shop and month**

- [ ] **Step 2: Implement occupied-days and weighted-capital calculation**

- [ ] **Step 3: Implement settlement calculation from the persisted `profit_basis_amount`**

- [ ] **Step 4: Persist settlement header and detail rows**

- [ ] **Step 5: Run the service tests until they pass**

Run: `python -m pytest backend/tests/test_follow_investment_service.py -q`

### Task 7: Add profit-basis routes and finance follow-investment routes

**Files:**
- Create: `backend/routers/profit_basis.py`
- Create: `backend/routers/follow_investment.py`
- Modify: `backend/routers/__init__.py` or the main router registration site
- Test: `backend/tests/test_profit_basis_routes.py`
- Test: `backend/tests/test_follow_investment_routes.py`

- [ ] **Step 1: Add routes for viewing and rebuilding monthly profit-basis snapshots**

- [ ] **Step 2: Add CRUD routes for follow-investment principal records**

- [ ] **Step 3: Add settlement calculate route**

- [ ] **Step 4: Add settlement list/detail/approve/mark-paid routes**

- [ ] **Step 5: Add current-user income route**

- [ ] **Step 6: Reuse `approval_logs` when approving settlements**

- [ ] **Step 7: Run route tests**

Run: `python -m pytest backend/tests/test_profit_basis_routes.py backend/tests/test_follow_investment_routes.py -q`

### Task 8: Add frontend finance API bindings

**Files:**
- Modify: `frontend/src/api/finance.js`

- [ ] **Step 1: Add monthly profit-basis query/rebuild helpers**

- [ ] **Step 2: Add principal list/create/update helpers**

- [ ] **Step 3: Add settlement calculate/list/approve/pay helpers**

- [ ] **Step 4: Add current-user income helper**

### Task 9: Extend the finance management screen

**Files:**
- Modify: `frontend/src/views/FinanceManagement.vue`
- Optionally create: `frontend/src/components/finance/FollowInvestment*.vue` if the view becomes too large

- [ ] **Step 1: Add a visible `profit_basis_amount` section with source breakdown**

- [ ] **Step 2: Add the `跟投收益` tab**

- [ ] **Step 3: Add the `跟投记录` section**

- [ ] **Step 4: Add the `月度试算` section**

- [ ] **Step 5: Add the `结算台账` section**

- [ ] **Step 6: Keep existing finance tabs unchanged**

### Task 10: Add a personal my follow-investment income surface

**Files:**
- Modify: `frontend/src/router/index.js`
- Create or modify: `frontend/src/views/hr/MyFollowInvestmentIncome.vue`

- [ ] **Step 1: Add a route for current-user follow-investment income**

- [ ] **Step 2: Implement a read-only page for current-user settlement history**

- [ ] **Step 3: Ensure the page only shows the logged-in user’s own data**

### Task 11: Prepare HR profit-sharing convergence

**Files:**
- Modify: `backend/routers/hr_commission.py`
- Modify: HR commission calculation services
- Test: relevant HR commission tests

- [ ] **Step 1: Identify the current HR dependency on `api.business_overview_shop_racing_module.profit`**

- [ ] **Step 2: Add an internal adapter layer so HR can switch to `profit_basis_amount` without breaking current APIs**

- [ ] **Step 3: Decide whether the first implementation wave flips HR immediately or leaves a feature-flagged path**

### Task 12: Verification and documentation

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run focused backend verification**

Run: `python -m pytest backend/tests/test_finance_schema_contract.py backend/tests/test_postgresql_dashboard_b_cost_routes.py backend/tests/test_profit_basis_service.py backend/tests/test_profit_basis_routes.py backend/tests/test_follow_investment_service.py backend/tests/test_follow_investment_routes.py -q`

- [ ] **Step 2: Run any available frontend verification for modified finance files**

- [ ] **Step 3: Record the final evidence and residual risks in the planning files**
