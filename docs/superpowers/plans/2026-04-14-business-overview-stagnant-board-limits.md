# Business Overview Stagnant Board Limits Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict the business overview stagnant board to dashboard-sized result sets by returning clearance ranking top 10 and inventory backlog risk top 20 from backend-backed limits.

**Architecture:** Keep the business overview page as a dashboard, not a full report. Push row limits into the PostgreSQL dashboard router/service contract so the frontend requests only the rows it needs, then verify both backend payload limits and frontend request parameters with targeted tests.

**Tech Stack:** FastAPI, async SQLAlchemy service layer, Vue 3, Element Plus, pytest, Node test runner

---

### Task 1: Record the dashboard contract in tests first

**Files:**
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

- [ ] **Step 1: Write the failing service test**

Add an assertion that `get_business_overview_inventory_backlog(..., limit=20)` returns at most 20 `top_products`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py -k inventory_backlog -q`
Expected: FAIL because the service method does not accept or enforce the new limit parameter yet.

- [ ] **Step 3: Write the failing router test**

Add a router test that verifies `get_business_overview_inventory_backlog_postgresql(..., limit=20)` forwards `limit` to the service.

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k inventory_backlog -q`
Expected: FAIL because the route currently only forwards `days`.

### Task 2: Update backend inventory backlog contract

**Files:**
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/domains/business/routers/dashboard_api_postgresql.py`

- [ ] **Step 1: Implement minimal service change**

Add a `limit` parameter to `get_business_overview_inventory_backlog(...)` and use it to bound `top_products`.

- [ ] **Step 2: Implement minimal router change**

Add `limit` query support to `/api/dashboard/business-overview/inventory-backlog` and pass it through to the service.

- [ ] **Step 3: Run targeted backend tests**

Run: `python -m pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k "inventory_backlog or clearance_ranking" -q`
Expected: PASS

### Task 3: Make the frontend request dashboard-sized result sets

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/BusinessOverview.vue`

- [ ] **Step 1: Write a lightweight frontend contract test**

Create a small Node-based regression test that checks:
- inventory backlog requests include `limit=20`
- clearance ranking requests include `limit=10`

- [ ] **Step 2: Run test to verify it fails**

Run the new frontend test directly with `node --test`.

- [ ] **Step 3: Implement the minimal frontend changes**

Update the API helper to serialize `limit` for business overview inventory backlog, then update `BusinessOverview.vue` loaders to pass `20` and `10`.

- [ ] **Step 4: Re-run the frontend test**

Run: `node --test <new frontend test file>`
Expected: PASS

### Task 4: Final verification

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] **Step 1: Run combined verification**

Run:
`python -m pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k "inventory_backlog or clearance_ranking" -q`

Run:
`node --test frontend/scripts/businessOverviewBoardLimits.test.mjs`

- [ ] **Step 2: Record results**

Update planning files with the final status, findings, and exact verification output.

