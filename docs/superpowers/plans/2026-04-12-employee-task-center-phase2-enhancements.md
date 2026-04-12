# Employee Task Center Phase 2 Enhancements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add phase-2 operational controls to the employee task center, including collaborator supplement actions, initiator cancellation rules, admin reassignment controls, task-type permission mapping, and task-type action strategies.

**Architecture:** Extend the existing employee-task domain rather than redesigning it. Add explicit action APIs and service-level policy checks first, then layer task-type strategy and permission mapping on top so the current inbox, notifications, and business-page links continue to work without breaking phase-1 behavior.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, existing RBAC config, pytest, node --test, vue-tsc

---

## File Structure

### New backend files

- Create: `backend/services/employee_task_policy.py`
  - Central policy engine for task-type actions, visibility, and permission compatibility.
- Create: `backend/tests/test_employee_task_policy.py`
  - Unit tests for action matrix and permission mapping.
- Create: `backend/tests/test_employee_task_admin_actions.py`
  - Backend tests for reassign/takeover/force-close.
- Create: `backend/tests/test_employee_task_collaboration_actions.py`
  - Backend tests for collaborator supplement behavior.

### Modified backend files

- Modify: `backend/schemas/employee_task.py`
  - Add request/response contracts for collaborator supplement, initiator cancel, admin reassign, takeover, and force-close.
- Modify: `backend/services/employee_task_service.py`
  - Add new actions and policy checks.
- Modify: `backend/services/employee_task_repository.py`
  - Support participant updates and task reassignment writes.
- Modify: `backend/routers/employee_tasks.py`
  - Add endpoints for phase-2 actions.
- Modify: `backend/services/employee_task_sources.py`
  - Validate assignee permission compatibility during task creation.
- Modify: `backend/services/employee_task_notifications.py`
  - Add helper support for cancellation / reassignment / return-style reminders as needed.

### Modified frontend files

- Modify: `frontend/src/api/employeeTasks.js`
  - Add API helpers for phase-2 actions.
- Modify: `frontend/src/views/approval/TaskDetail.vue`
  - Add collaborator supplement UI, initiator close/cancel actions, and admin control panel.
- Modify: `frontend/src/config/rolePermissions.js`
  - Ensure task-related role permissions remain aligned.
- Modify: `frontend/src/router/index.js`
  - Keep route metadata aligned if additional task action pages or dialogs are needed.
- Modify: `frontend/scripts/employeeTaskUi.test.mjs`
  - Extend deterministic checks for new action regions.

### Documentation updates

- Modify: `docs/superpowers/specs/2026-04-12-employee-task-center-phase2-enhancements-design.md`
  - Reflect any implementation-driven scope adjustments.
- Modify: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`
  - Document new action permissions and operator guidance.

## Task 1: Add Task-Type Policy Engine

**Files:**
- Create: `backend/services/employee_task_policy.py`
- Create: `backend/tests/test_employee_task_policy.py`

- [ ] **Step 1: Write failing policy tests**

Cover:
- allowed actions for `execution`, `confirmation`, `approval`, and `reminder`
- collaborator cannot submit final result
- initiator may close only unstarted tasks
- admin may reassign / take over / force close
- task-type to route/permission mapping for:
  - `monthly_cost_entry`
  - `performance_confirmation`

- [ ] **Step 2: Run policy tests to verify failure**

Run: `python -m pytest backend/tests/test_employee_task_policy.py -q`
Expected: FAIL because policy engine does not exist.

- [ ] **Step 3: Implement task policy engine**

Add:
- action matrix by task category / task type
- helper such as `get_task_type_policy(task_type)`
- helper such as `can_user_perform_task_action(...)`
- helper such as `validate_task_target_permission(...)`

- [ ] **Step 4: Re-run policy tests**

Run: `python -m pytest backend/tests/test_employee_task_policy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit policy engine**

```bash
git add backend/services/employee_task_policy.py backend/tests/test_employee_task_policy.py
git commit -m "feat: add employee task policy engine"
```

## Task 2: Add Collaborator Supplement Actions

**Files:**
- Modify: `backend/schemas/employee_task.py`
- Modify: `backend/services/employee_task_service.py`
- Modify: `backend/routers/employee_tasks.py`
- Create: `backend/tests/test_employee_task_collaboration_actions.py`

- [ ] **Step 1: Write failing collaborator action tests**

Cover:
- collaborator may append comment
- collaborator may append evidence / structured supplement
- collaborator may not submit final result
- supplement actions create timeline entries

- [ ] **Step 2: Run collaborator tests to verify failure**

Run: `python -m pytest backend/tests/test_employee_task_collaboration_actions.py -q`
Expected: FAIL because collaborator supplement actions do not exist.

- [ ] **Step 3: Add collaborator supplement contracts**

Add request models for:
- append comment
- append evidence metadata
- append structured supplement

- [ ] **Step 4: Implement collaborator supplement service methods**

Add service methods such as:
- `append_task_comment`
- `append_task_evidence`
- `append_task_structured_data`

Enforce:
- only collaborator / owner / admin can supplement
- supplement does not move task to completed

- [ ] **Step 5: Add API endpoints**

Add endpoints such as:
- `POST /api/employee-tasks/{task_id}/comment`
- `POST /api/employee-tasks/{task_id}/evidence`
- `POST /api/employee-tasks/{task_id}/supplement`

- [ ] **Step 6: Re-run collaborator tests**

Run: `python -m pytest backend/tests/test_employee_task_collaboration_actions.py -q`
Expected: PASS.

- [ ] **Step 7: Commit collaborator actions**

```bash
git add backend/schemas/employee_task.py backend/services/employee_task_service.py backend/routers/employee_tasks.py backend/tests/test_employee_task_collaboration_actions.py
git commit -m "feat: add collaborator task supplement actions"
```

## Task 3: Add Initiator Close And Cancellation Rules

**Files:**
- Modify: `backend/schemas/employee_task.py`
- Modify: `backend/services/employee_task_service.py`
- Modify: `backend/routers/employee_tasks.py`
- Modify: `backend/tests/test_employee_task_service.py`

- [ ] **Step 1: Write failing initiator-action tests**

Cover:
- initiator may directly close `pending` tasks
- initiator may not directly close `in_progress` or `pending_confirmation` tasks
- initiator may request cancellation after task has started

- [ ] **Step 2: Run service tests to verify failure**

Run: `python -m pytest backend/tests/test_employee_task_service.py -q`
Expected: FAIL for the new initiator action cases.

- [ ] **Step 3: Add initiator action contracts**

Add request models for:
- `close_unstarted_task`
- `request_cancel`

- [ ] **Step 4: Implement service logic**

Add:
- `close_task_as_initiator`
- `request_task_cancellation`

Write timeline entries:
- `close_unstarted_task`
- `request_cancel`

- [ ] **Step 5: Add or update API endpoints**

Add endpoints such as:
- `POST /api/employee-tasks/{task_id}/close-by-initiator`
- `POST /api/employee-tasks/{task_id}/request-cancel`

- [ ] **Step 6: Re-run service tests**

Run: `python -m pytest backend/tests/test_employee_task_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit initiator rules**

```bash
git add backend/schemas/employee_task.py backend/services/employee_task_service.py backend/routers/employee_tasks.py backend/tests/test_employee_task_service.py
git commit -m "feat: add initiator task cancellation rules"
```

## Task 4: Add Admin Reassign, Takeover, And Force Close

**Files:**
- Modify: `backend/schemas/employee_task.py`
- Modify: `backend/services/employee_task_repository.py`
- Modify: `backend/services/employee_task_service.py`
- Modify: `backend/routers/employee_tasks.py`
- Create: `backend/tests/test_employee_task_admin_actions.py`

- [ ] **Step 1: Write failing admin-action tests**

Cover:
- admin may reassign task owner
- admin may take over a task
- admin may force close with reason
- all admin actions write timeline records

- [ ] **Step 2: Run admin-action tests to verify failure**

Run: `python -m pytest backend/tests/test_employee_task_admin_actions.py -q`
Expected: FAIL because these actions do not exist.

- [ ] **Step 3: Add admin-action request contracts**

Add:
- reassignment request
- takeover request
- force-close request

- [ ] **Step 4: Implement repository and service support**

Add:
- owner reassignment write support
- participant maintenance if needed
- audit/timeline entries with reasons

- [ ] **Step 5: Add API endpoints**

Add endpoints such as:
- `POST /api/employee-tasks/{task_id}/reassign`
- `POST /api/employee-tasks/{task_id}/takeover`
- `POST /api/employee-tasks/{task_id}/force-close`

- [ ] **Step 6: Re-run admin-action tests**

Run: `python -m pytest backend/tests/test_employee_task_admin_actions.py -q`
Expected: PASS.

- [ ] **Step 7: Commit admin controls**

```bash
git add backend/schemas/employee_task.py backend/services/employee_task_repository.py backend/services/employee_task_service.py backend/routers/employee_tasks.py backend/tests/test_employee_task_admin_actions.py
git commit -m "feat: add admin task control actions"
```

## Task 5: Enforce Task-Type To Permission Mapping At Assignment Time

**Files:**
- Modify: `backend/services/employee_task_policy.py`
- Modify: `backend/services/employee_task_service.py`
- Modify: `backend/services/employee_task_sources.py`
- Modify: `backend/tests/test_employee_task_policy.py`
- Modify: `backend/tests/test_employee_task_sources.py`

- [ ] **Step 1: Add failing assignment-validation tests**

Cover:
- assignee lacking required permission is rejected
- `monthly_cost_entry` validates `expense-management`
- `performance_confirmation` validates `performance:read`

- [ ] **Step 2: Run policy/source tests to verify failure**

Run:
```bash
python -m pytest backend/tests/test_employee_task_policy.py backend/tests/test_employee_task_sources.py -q
```
Expected: FAIL for new permission-compatibility cases.

- [ ] **Step 3: Implement assignment-time validation**

Use policy mapping to ensure:
- task detail route and business route are known
- required permission exists
- assignee has compatible role / permission

- [ ] **Step 4: Re-run policy/source tests**

Run:
```bash
python -m pytest backend/tests/test_employee_task_policy.py backend/tests/test_employee_task_sources.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit permission mapping**

```bash
git add backend/services/employee_task_policy.py backend/services/employee_task_service.py backend/services/employee_task_sources.py backend/tests/test_employee_task_policy.py backend/tests/test_employee_task_sources.py
git commit -m "feat: validate employee task permission mapping"
```

## Task 6: Align Frontend Task UI With Phase 2 Actions

**Files:**
- Modify: `frontend/src/api/employeeTasks.js`
- Modify: `frontend/src/views/approval/TaskDetail.vue`
- Modify: `frontend/scripts/employeeTaskUi.test.mjs`
- Modify: `frontend/src/config/rolePermissions.js` only if new task action access requires alignment

- [ ] **Step 1: Write failing UI assertions**

Cover:
- task detail shows collaborator supplement actions
- task detail shows initiator close/cancel options when appropriate
- task detail shows admin reassignment / force-close options when appropriate

- [ ] **Step 2: Run frontend task UI tests to verify failure**

Run: `node --test frontend/scripts/employeeTaskUi.test.mjs`
Expected: FAIL because those UI regions do not exist yet.

- [ ] **Step 3: Extend frontend API wrapper**

Add helpers for:
- comment / evidence / supplement
- initiator close / cancel request
- admin reassign / takeover / force-close

- [ ] **Step 4: Extend `TaskDetail.vue`**

Add:
- collaborator supplement section
- initiator task control section
- admin control section

Use backend task detail payload to decide visibility.

- [ ] **Step 5: Re-run frontend tests**

Run:
```bash
node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```
Expected: PASS.

- [ ] **Step 6: Commit phase-2 frontend**

```bash
git add frontend/src/api/employeeTasks.js frontend/src/views/approval/TaskDetail.vue frontend/scripts/employeeTaskUi.test.mjs frontend/src/config/rolePermissions.js
git commit -m "feat: add employee task phase2 frontend actions"
```

## Task 7: Documentation And Final Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-12-employee-task-center-phase2-enhancements-design.md`
- Modify: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`

- [ ] **Step 1: Update docs with final behavior**

Document:
- collaborator supplement actions
- initiator close/cancel rules
- admin override actions
- permission mapping behavior

- [ ] **Step 2: Run final backend verification**

Run:
```bash
python -m pytest backend/tests/test_employee_task_schema.py backend/tests/test_employee_task_service.py backend/tests/test_employee_task_routes.py backend/tests/test_employee_task_notifications.py backend/tests/test_employee_task_sources.py backend/tests/test_employee_task_policy.py backend/tests/test_employee_task_collaboration_actions.py backend/tests/test_employee_task_admin_actions.py -q
```

- [ ] **Step 3: Run final frontend verification**

Run:
```bash
node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```

- [ ] **Step 4: Commit documentation updates**

```bash
git add docs/superpowers/specs/2026-04-12-employee-task-center-phase2-enhancements-design.md docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md
git commit -m "docs: update employee task center phase2 guidance"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-12-employee-task-center-phase2-enhancements.md`. Ready to execute?
