# Approval Center Unified Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified approval center with `我的申请`, `审批历史`, and `流程配置`, while projecting pending approval steps into the existing employee task center so the product keeps a single pending-work inbox.

**Architecture:** Add a lightweight approval domain beside the existing employee-task domain. Approval center owns approval templates, approval instances, approval steps, and approval action logs. The employee task center remains the single actionable inbox by projecting the currently pending approval step into a standard employee task row instead of creating a second "我的待办" surface.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, Vue 3, Element Plus, existing employee task center services, pytest, node --test, vue-tsc

---

## File Structure

### New backend files

- Create: `backend/schemas/approval_center.py`
  - Approval template, instance, step, action-log, request, and projection response contracts.
- Create: `backend/services/approval_center_repository.py`
  - Repository methods for templates, instances, steps, and action logs.
- Create: `backend/services/approval_center_service.py`
  - Approval lifecycle orchestration and task-projection support.
- Create: `backend/tests/test_approval_center_schema.py`
  - Schema contract tests for approval-center ORM and migration.
- Create: `backend/tests/test_approval_center_service.py`
  - Lifecycle tests for submit / approve / reject / withdraw.
- Create: `backend/tests/test_approval_center_routes.py`
  - Route tests for approval-center API.
- Create: `migrations/versions/20260413_add_approval_center_tables.py`
  - Approval center domain tables migration.

### Modified backend files

- Modify: `modules/core/db/schema.py`
  - Add approval templates, instances, steps, and action logs.
- Modify: `backend/main.py`
  - Register approval-center router.
- Modify: `backend/services/employee_task_service.py`
  - Add approval-task projection creation / closure helpers if needed.
- Modify: `backend/routers/users_admin.py`
  - Route user registration approval through approval-center lifecycle.
- Modify: `backend/routers/hr_attendance.py`
  - Align leave and overtime approval flows with approval-center lifecycle.
- Modify: `backend/routers/monthly_profit_settlement.py`
  - Align settlement approval state with approval-center instance state.
- Modify: `backend/routers/follow_investment.py`
  - Align follow-investment approval state with approval-center instance state.

### New frontend files

- Create: `frontend/src/api/approvalCenter.js`
  - Frontend approval-center API wrapper.
- Create: `frontend/scripts/approvalCenterUi.test.mjs`
  - UI assertions for `我的申请`, `审批历史`, `流程配置`.

### Modified frontend files

- Modify: `frontend/src/views/approval/MyRequests.vue`
  - Replace placeholder with real request list / detail launcher.
- Modify: `frontend/src/views/approval/ApprovalHistory.vue`
  - Replace placeholder with real acted-history page.
- Modify: `frontend/src/views/approval/WorkflowConfig.vue`
  - Replace placeholder with admin template-config page.
- Modify: `frontend/src/views/approval/MyTasks.vue`
  - Add approval-task tagging or grouping where useful.
- Modify: `frontend/src/views/approval/TaskDetail.vue`
  - Render approval-specific task details and actions when task source is approval center.
- Modify: `frontend/src/router/index.js`
  - Keep approval routes and permissions aligned.
- Modify: `frontend/src/config/menuGroups.js`
  - Keep one pending queue; expose approval-center pages cleanly.
- Modify: `frontend/src/config/rolePermissions.js`
  - Align approval-center permissions with role access.

### Documentation updates

- Modify: `docs/superpowers/specs/2026-04-13-approval-center-unified-design.md`
  - Update with implementation notes if needed.
- Modify: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`
  - Document approval-task projection and approval-center navigation.

## Task 1: Add Approval-Center ORM Models And Migration

**Files:**
- Modify: `modules/core/db/schema.py`
- Create: `migrations/versions/20260413_add_approval_center_tables.py`
- Create: `backend/tests/test_approval_center_schema.py`

- [ ] **Step 1: Write failing schema tests**

Cover:
- `approval_templates` table exists
- `approval_instances` table exists
- `approval_steps` table exists
- `approval_action_logs` table exists
- approval instance has applicant/status/current step fields
- approval step has approver/status/order fields

- [ ] **Step 2: Run schema tests to verify failure**

Run: `python -m pytest backend/tests/test_approval_center_schema.py -q`
Expected: FAIL because approval-center tables do not exist yet.

- [ ] **Step 3: Add approval-center ORM models**

Add to `modules/core/db/schema.py`:
- `ApprovalTemplate`
- `ApprovalInstance`
- `ApprovalStep`
- `ApprovalActionLog`

- [ ] **Step 4: Add approval-center migration**

Create migration for the four tables with indexes for:
- template enablement
- applicant lookup
- status lookup
- current approver lookup
- action timeline ordering

- [ ] **Step 5: Re-run schema tests**

Run: `python -m pytest backend/tests/test_approval_center_schema.py -q`
Expected: PASS.

- [ ] **Step 6: Commit ORM and migration**

```bash
git add modules/core/db/schema.py migrations/versions/20260413_add_approval_center_tables.py backend/tests/test_approval_center_schema.py
git commit -m "feat: add approval center domain tables"
```

## Task 2: Build Approval Lifecycle Contracts, Repository, And Service

**Files:**
- Create: `backend/schemas/approval_center.py`
- Create: `backend/services/approval_center_repository.py`
- Create: `backend/services/approval_center_service.py`
- Create: `backend/tests/test_approval_center_service.py`

- [ ] **Step 1: Write failing service tests**

Cover:
- create approval instance from template
- create first pending step
- project current step into employee task center
- approve current step and open next step
- reject current step and end workflow
- withdraw approval before review completes

- [ ] **Step 2: Run service tests to verify failure**

Run: `python -m pytest backend/tests/test_approval_center_service.py -q`
Expected: FAIL because approval-center service does not exist.

- [ ] **Step 3: Add approval-center contracts**

Include request/response models for:
- submit approval
- approve / reject / withdraw
- list requests
- list approval history
- template summary
- approval detail

- [ ] **Step 4: Implement repository layer**

Repository should support:
- create template / instance / step / action log
- get current step
- list instances by applicant
- list acted history by approver
- list / update templates

- [ ] **Step 5: Implement service layer**

Service should support:
- `submit_approval`
- `approve_step`
- `reject_step`
- `withdraw_approval`
- `list_my_requests`
- `list_my_history`
- `get_approval_detail`

Also:
- create employee-task projection for the current pending approval step
- close previous projection when step advances or workflow ends

- [ ] **Step 6: Re-run service tests**

Run: `python -m pytest backend/tests/test_approval_center_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit approval service layer**

```bash
git add backend/schemas/approval_center.py backend/services/approval_center_repository.py backend/services/approval_center_service.py backend/tests/test_approval_center_service.py
git commit -m "feat: add approval center lifecycle service"
```

## Task 3: Add Approval-Center API

**Files:**
- Create: `backend/routers/approval_center.py`
- Create: `backend/tests/test_approval_center_routes.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing route tests**

Cover:
- `GET /api/approval-center/requests`
- `GET /api/approval-center/history`
- `GET /api/approval-center/templates`
- `GET /api/approval-center/{approval_id}`
- `POST /api/approval-center/{approval_id}/approve`
- `POST /api/approval-center/{approval_id}/reject`
- `POST /api/approval-center/{approval_id}/withdraw`

- [ ] **Step 2: Run route tests to verify failure**

Run: `python -m pytest backend/tests/test_approval_center_routes.py -q`
Expected: FAIL because approval-center router does not exist.

- [ ] **Step 3: Implement router**

Add routes for:
- my requests
- approval history
- template list
- approval detail
- approval actions

- [ ] **Step 4: Register router**

Mount under `/api/approval-center`.

- [ ] **Step 5: Re-run route tests**

Run: `python -m pytest backend/tests/test_approval_center_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit API**

```bash
git add backend/routers/approval_center.py backend/main.py backend/tests/test_approval_center_routes.py
git commit -m "feat: add approval center api"
```

## Task 4: Integrate Existing Approval-Capable Flows

**Files:**
- Modify: `backend/routers/users_admin.py`
- Modify: `backend/routers/hr_attendance.py`
- Modify: `backend/routers/monthly_profit_settlement.py`
- Modify: `backend/routers/follow_investment.py`
- Modify: `backend/tests/test_users_admin_routes.py`
- Modify: `backend/tests/test_monthly_profit_settlement_routes.py`
- Modify: `backend/tests/test_follow_investment_routes.py`

## Current Delivery Snapshot

As of 2026-04-13, the following items are complete on `main`:

- approval-center ORM models and migration
- approval-center lifecycle service
- approval-center API
- frontend pages for:
  - `我的申请`
  - `审批历史`
  - `流程配置` (read-only template view)
- approval-center permission hardening for:
  - detail visibility
  - approve / reject actions
  - template-list admin-only access
- existing approval-flow integrations:
  - user registration approval
  - monthly profit settlement approval
  - follow-investment settlement approval

## Deferred Optimization Backlog

The following items are intentionally deferred to later optimization rounds:

1. HR leave approval integration
   - blocked on current `hr_attendance.py` permission / approver model cleanup
2. HR overtime approval integration
   - same prerequisite as leave approval
3. workflow-config editing
   - current page is read-only template visibility, not a full editor
4. explicit template-configured approver rules
   - current registration / settlement approvals still use lightweight admin fallback
5. dedicated approval detail route
   - current frontend uses list + drawer detail pattern
6. richer pending-queue projection UX
   - approval tasks already project into the unified inbox, but frontend grouping and jump flow can be improved

- [ ] **Step 1: Write failing integration assertions**

Cover:
- user registration approval creates/updates approval instance
- leave/overtime approval aligns with approval-center state
- settlement approvals align with approval-center state

- [ ] **Step 2: Run targeted tests to verify failure**

Run:
```bash
python -m pytest backend/tests/test_users_admin_routes.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py -q
```
Expected: FAIL for the new approval-center expectations.

- [ ] **Step 3: Integrate user registration approval**

Use approval-center lifecycle for:
- creating approval instance when user registration enters pending state
- closing it on approve/reject

- [ ] **Step 4: Integrate attendance approvals**

Align leave/overtime approve operations with approval-center instance lifecycle and task projection.

- [ ] **Step 5: Integrate settlement approvals**

Align monthly-profit and follow-investment approvals with approval-center instance state transitions.

- [ ] **Step 6: Re-run targeted tests**

Run:
```bash
python -m pytest backend/tests/test_users_admin_routes.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py -q
```
Expected: PASS.

- [ ] **Step 7: Commit flow integrations**

```bash
git add backend/routers/users_admin.py backend/routers/hr_attendance.py backend/routers/monthly_profit_settlement.py backend/routers/follow_investment.py backend/tests/test_users_admin_routes.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py
git commit -m "feat: route existing approvals through approval center"
```

## Task 5: Build Approval-Center Frontend

**Files:**
- Create: `frontend/src/api/approvalCenter.js`
- Modify: `frontend/src/views/approval/MyRequests.vue`
- Modify: `frontend/src/views/approval/ApprovalHistory.vue`
- Modify: `frontend/src/views/approval/WorkflowConfig.vue`
- Modify: `frontend/src/views/approval/MyTasks.vue`
- Modify: `frontend/src/views/approval/TaskDetail.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/config/rolePermissions.js`
- Create: `frontend/scripts/approvalCenterUi.test.mjs`

- [ ] **Step 1: Write failing frontend UI tests**

Cover:
- `我的申请` is no longer placeholder-only
- `审批历史` is no longer placeholder-only
- `流程配置` is no longer placeholder-only
- approval-task detail renders approval-center-specific sections

- [ ] **Step 2: Run UI tests to verify failure**

Run: `node --test frontend/scripts/approvalCenterUi.test.mjs`
Expected: FAIL because approval-center pages are still placeholders.

- [ ] **Step 3: Add frontend API wrapper**

Add methods for:
- list my requests
- list approval history
- list templates
- get approval detail
- approve / reject / withdraw

- [ ] **Step 4: Replace placeholder pages**

Build:
- `我的申请`
- `审批历史`
- `流程配置`

Keep v1 simple:
- list pages
- detail links
- no graphical flow editor

- [ ] **Step 5: Extend task detail for approval projections**

If task source is `approval-center`, show:
- approval instance basics
- current step
- approval actions
- withdraw where allowed

- [ ] **Step 6: Align routes/menu/roles**

Ensure:
- only one pending-work inbox remains (`我的待办`)
- approval center contains:
  - `我的申请`
  - `审批历史`
  - `流程配置`

- [ ] **Step 7: Re-run frontend checks**

Run:
```bash
node --test frontend/scripts/approvalCenterUi.test.mjs frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```
Expected: PASS.

- [ ] **Step 8: Commit frontend approval center**

```bash
git add frontend/src/api/approvalCenter.js frontend/src/views/approval/MyRequests.vue frontend/src/views/approval/ApprovalHistory.vue frontend/src/views/approval/WorkflowConfig.vue frontend/src/views/approval/MyTasks.vue frontend/src/views/approval/TaskDetail.vue frontend/src/router/index.js frontend/src/config/menuGroups.js frontend/src/config/rolePermissions.js frontend/scripts/approvalCenterUi.test.mjs
git commit -m "feat: build approval center frontend"
```

## Task 6: Documentation And Final Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-13-approval-center-unified-design.md`
- Modify: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`

- [ ] **Step 1: Update docs with implemented approval-center behavior**

Document:
- unified pending queue vs approval center split
- first-wave approval types
- applicant / approver journey
- approval-task projection behavior

- [ ] **Step 2: Run final backend verification**

Run:
```bash
python -m pytest backend/tests/test_approval_center_schema.py backend/tests/test_approval_center_service.py backend/tests/test_approval_center_routes.py backend/tests/test_users_admin_routes.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py backend/tests/test_employee_task_policy.py backend/tests/test_employee_task_collaboration_actions.py backend/tests/test_employee_task_service.py backend/tests/test_employee_task_admin_actions.py backend/tests/test_employee_task_routes.py backend/tests/test_employee_task_sources.py -q
```

- [ ] **Step 3: Run final frontend verification**

Run:
```bash
node --test frontend/scripts/approvalCenterUi.test.mjs frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```

- [ ] **Step 4: Commit docs**

```bash
git add docs/superpowers/specs/2026-04-13-approval-center-unified-design.md docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md
git commit -m "docs: update approval center guidance"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-13-approval-center-unified-implementation.md`. Ready to execute?
