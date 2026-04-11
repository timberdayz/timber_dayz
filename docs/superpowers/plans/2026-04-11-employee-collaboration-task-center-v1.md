# Employee Collaboration Task Center V1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-ready employee collaboration task center with a real `我的任务` inbox, task detail flow, task-based notifications, and initial automatic task generation for monthly cost entry and performance confirmation.

**Architecture:** Add a dedicated employee-facing collaboration task domain instead of overloading the existing system long-task center. Reuse the current notification infrastructure for reminders, keep business modules as execution surfaces, and wire two mature automatic sources plus one replenishment-template bridge into a unified employee task workflow. The frontend should expose one primary task inbox with tabs rather than spawning multiple disconnected pages.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, Vue 3, Element Plus, Pinia-compatible frontend patterns, existing notification WebSocket stack, pytest, node --test

---

## File Structure

### New backend files

- Create: `backend/schemas/employee_task.py`
  - Employee task request/response contracts, timeline contracts, participant contracts, and source-creation payloads.
- Create: `backend/services/employee_task_repository.py`
  - Focused persistence operations for employee task tables.
- Create: `backend/services/employee_task_service.py`
  - Task lifecycle, participant handling, reminder orchestration entrypoints, and source adapter entrypoints.
- Create: `backend/services/employee_task_notifications.py`
  - Shared helper for creating task-related notifications using the existing notification system.
- Create: `backend/tests/test_employee_task_schema.py`
  - Contract tests for new Pydantic models.
- Create: `backend/tests/test_employee_task_service.py`
  - Core lifecycle and participant tests.
- Create: `backend/tests/test_employee_task_routes.py`
  - API tests for list/detail/state actions.
- Create: `backend/tests/test_employee_task_notifications.py`
  - Notification payload and recipient tests.
- Create: `backend/tests/test_employee_task_sources.py`
  - Automatic source-generation tests for expense and performance flows.
- Create: `frontend/src/api/employeeTasks.js`
  - Frontend API wrapper for employee task endpoints.
- Create: `frontend/src/views/approval/TaskDetail.vue`
  - Dedicated task detail and action surface.
- Create: `frontend/scripts/employeeTaskRoutes.test.mjs`
  - Deterministic route/menu assertions.
- Create: `frontend/scripts/employeeTaskUi.test.mjs`
  - Source-level UI assertions for inbox/detail rendering.
- Create: `migrations/versions/20260411_add_employee_collaboration_task_tables.py`
  - New collaboration task tables in the canonical ORM chain.

### Modified backend files

- Modify: `modules/core/db/schema.py`
  - Add collaboration task ORM models to the SSOT.
- Modify: `backend/main.py`
  - Register the new router.
- Modify: `backend/routers/notifications.py`
  - Add task notification type handling and helper entrypoints.
- Modify: `backend/schemas/notification.py`
  - Add task-related notification enums and payload support.
- Modify: `backend/routers/users_me.py`
  - Ensure notification preferences can serve newly added task notification types.
- Modify: `backend/routers/expense_management.py`
  - Create or refresh employee tasks when monthly cost actions require owner follow-up.
- Modify: `backend/routers/performance_management.py`
  - Create or refresh employee tasks for performance confirmation actions.
- Modify: `backend/services/permission_service.py`
  - Add employee task center permissions if the repository still requires explicit registration.

### Modified frontend files

- Modify: `frontend/src/views/approval/MyTasks.vue`
  - Replace placeholder page with the real inbox.
- Modify: `frontend/src/router/index.js`
  - Add task detail route and broaden task access beyond admin-only.
- Modify: `frontend/src/config/menuGroups.js`
  - Keep approval menu entry but align title/placement with the new collaboration task center.
- Modify: `frontend/src/config/rolePermissions.js`
  - Ensure employee-facing roles can access the task inbox and detail page.
- Modify: `frontend/src/components/common/NotificationBell.vue`
  - Route task notifications into task detail or task-linked business pages.
- Modify: `frontend/src/views/settings/NotificationPreferences.vue`
  - Show new task notification types.
- Modify: `frontend/src/views/finance/ExpenseManagement.vue`
  - Accept task context and complete or refresh linked cost-entry tasks.
- Modify: `frontend/src/views/hr/PerformanceManagement.vue`
  - Accept task context and complete or refresh linked performance-confirmation tasks.
- Modify: `frontend/src/views/procurement/PurchaseOrders.vue`
  - Add a bridge placeholder for replenishment task templates until procurement runtime exists.

### Documentation updates

- Modify: `docs/superpowers/specs/2026-04-11-employee-collaboration-task-center-design.md`
  - Note any implementation-driven scope refinement if required.
- Create: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`
  - Explain task center operations, source adapters, and reminder behavior.

## Task 1: Add Collaboration Task ORM And Migration

**Files:**
- Modify: `modules/core/db/schema.py`
- Create: `migrations/versions/20260411_add_employee_collaboration_task_tables.py`
- Create: `backend/tests/test_employee_task_schema.py`

- [ ] **Step 1: Write failing ORM/schema contract tests**

Add tests covering:
- new `EmployeeTask` ORM model fields
- task log / timeline model fields
- task participant model fields
- expected default statuses and timestamps

- [ ] **Step 2: Run targeted backend schema tests to verify failure**

Run: `pytest backend/tests/test_employee_task_schema.py -v`
Expected: FAIL because collaboration task ORM models do not exist yet.

- [ ] **Step 3: Add SSOT ORM models to `modules/core/db/schema.py`**

Add:
- `EmployeeTask`
- `EmployeeTaskLog`
- `EmployeeTaskParticipant`

Include:
- one primary owner field on task row
- task category, type, status, priority
- business linkage fields
- completion schema / payload JSON
- review outcome fields
- timestamps and soft-close fields

- [ ] **Step 4: Add Alembic migration for collaboration task tables**

Create migration that:
- creates the three tables
- adds indexes for owner, status, due time, source object, and created time
- keeps names distinct from the existing `task_center_*` tables

- [ ] **Step 5: Re-run schema tests**

Run: `pytest backend/tests/test_employee_task_schema.py -v`
Expected: PASS.

- [ ] **Step 6: Commit ORM and migration work**

```bash
git add modules/core/db/schema.py migrations/versions/20260411_add_employee_collaboration_task_tables.py backend/tests/test_employee_task_schema.py
git commit -m "feat: add employee collaboration task tables"
```

## Task 2: Build Backend Contracts, Repository, And Service Layer

**Files:**
- Create: `backend/schemas/employee_task.py`
- Create: `backend/services/employee_task_repository.py`
- Create: `backend/services/employee_task_service.py`
- Create: `backend/tests/test_employee_task_service.py`

- [ ] **Step 1: Write failing service tests**

Cover:
- create task with exactly one owner
- list tasks by owner / initiated-by / cc
- state transitions
- participant restrictions
- timeline append on state change
- completion payload persistence

- [ ] **Step 2: Run targeted service tests to verify failure**

Run: `pytest backend/tests/test_employee_task_service.py -v`
Expected: FAIL because service and schema files do not exist.

- [ ] **Step 3: Add Pydantic contracts in `backend/schemas/employee_task.py`**

Include:
- task list item
- task detail
- participant payloads
- action request payloads for start / submit / confirm / reject / close / nudge
- timeline payloads

- [ ] **Step 4: Implement repository layer**

Repository should provide:
- create task
- fetch by task ID
- list with filters and pagination
- add / replace participants
- append timeline event
- update state safely

- [ ] **Step 5: Implement service layer**

Service should provide:
- `create_task`
- `list_tasks`
- `get_task_detail`
- `start_task`
- `submit_task_result`
- `confirm_task_result`
- `reject_task_result`
- `close_task`
- `nudge_task`

Service should enforce:
- exactly one owner
- owner-only result submission
- CC read-only default behavior
- state transition guards

- [ ] **Step 6: Re-run service tests**

Run: `pytest backend/tests/test_employee_task_service.py -v`
Expected: PASS.

- [ ] **Step 7: Commit backend service layer**

```bash
git add backend/schemas/employee_task.py backend/services/employee_task_repository.py backend/services/employee_task_service.py backend/tests/test_employee_task_service.py
git commit -m "feat: add employee task service layer"
```

## Task 3: Add Employee Task API Surface

**Files:**
- Create: `backend/tests/test_employee_task_routes.py`
- Modify: `backend/main.py`
- Create: `backend/routers/employee_tasks.py`

- [ ] **Step 1: Write failing API contract tests**

Cover:
- inbox list endpoint
- initiated-by-me list endpoint
- cc-to-me list endpoint
- task detail endpoint
- start task action
- submit result action
- confirm / reject / close actions

- [ ] **Step 2: Run targeted route tests to verify failure**

Run: `pytest backend/tests/test_employee_task_routes.py -v`
Expected: FAIL because endpoints are missing.

- [ ] **Step 3: Implement router with async DB patterns**

Add endpoints such as:
- `GET /api/employee-tasks`
- `GET /api/employee-tasks/{task_id}`
- `POST /api/employee-tasks/{task_id}/start`
- `POST /api/employee-tasks/{task_id}/submit`
- `POST /api/employee-tasks/{task_id}/confirm`
- `POST /api/employee-tasks/{task_id}/reject`
- `POST /api/employee-tasks/{task_id}/close`
- `POST /api/employee-tasks/{task_id}/nudge`

Use:
- `AsyncSession`
- `get_async_db()`
- typed response models from `backend/schemas/employee_task.py`

- [ ] **Step 4: Register router in `backend/main.py`**

Ensure the new API mounts under `/api`.

- [ ] **Step 5: Re-run route tests**

Run: `pytest backend/tests/test_employee_task_routes.py -v`
Expected: PASS.

- [ ] **Step 6: Commit API surface**

```bash
git add backend/routers/employee_tasks.py backend/main.py backend/tests/test_employee_task_routes.py
git commit -m "feat: add employee task api"
```

## Task 4: Integrate Task Notifications And Preferences

**Files:**
- Modify: `backend/schemas/notification.py`
- Modify: `backend/routers/notifications.py`
- Modify: `backend/routers/users_me.py`
- Create: `backend/services/employee_task_notifications.py`
- Create: `backend/tests/test_employee_task_notifications.py`
- Modify: `frontend/src/components/common/NotificationBell.vue`
- Modify: `frontend/src/views/settings/NotificationPreferences.vue`

- [ ] **Step 1: Write failing notification contract tests**

Cover:
- new task notification types
- task assignment recipient behavior
- due-soon / overdue / returned / nudged payload shape
- notification preference round-trip for task types

- [ ] **Step 2: Run targeted notification tests to verify failure**

Run: `pytest backend/tests/test_employee_task_notifications.py -v`
Expected: FAIL because task notification types do not exist.

- [ ] **Step 3: Add task notification enum values**

Extend `backend/schemas/notification.py` with:
- `task_assigned`
- `task_due_soon`
- `task_overdue`
- `task_returned`
- `task_nudged`

- [ ] **Step 4: Implement task notification helper service**

Create helper methods for:
- create assignment notification
- create due-soon notification
- create overdue notification
- create returned notification
- create nudge notification

Each payload should include:
- `task_id`
- `task_type`
- `source_module`
- `source_record_type`
- `source_record_id`
- `target_route`

- [ ] **Step 5: Update notification routing and preferences**

Backend:
- allow these types through preference APIs

Frontend:
- show task labels in notification preferences
- route task notifications from `NotificationBell.vue` to task detail or linked business page

- [ ] **Step 6: Re-run targeted notification tests**

Run: `pytest backend/tests/test_employee_task_notifications.py -v`
Expected: PASS.

- [ ] **Step 7: Add frontend deterministic checks**

Run: `node --test frontend/scripts/employeeTaskRoutes.test.mjs`
Expected: PASS after the route and notification updates in later tasks.

- [ ] **Step 8: Commit notification integration**

```bash
git add backend/schemas/notification.py backend/routers/notifications.py backend/routers/users_me.py backend/services/employee_task_notifications.py backend/tests/test_employee_task_notifications.py frontend/src/components/common/NotificationBell.vue frontend/src/views/settings/NotificationPreferences.vue
git commit -m "feat: add employee task notifications"
```

## Task 5: Build Real My Tasks Inbox And Task Detail Frontend

**Files:**
- Create: `frontend/src/api/employeeTasks.js`
- Modify: `frontend/src/views/approval/MyTasks.vue`
- Create: `frontend/src/views/approval/TaskDetail.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/config/rolePermissions.js`
- Create: `frontend/scripts/employeeTaskRoutes.test.mjs`
- Create: `frontend/scripts/employeeTaskUi.test.mjs`

- [ ] **Step 1: Write failing frontend route and UI tests**

Cover:
- `我的任务` route is no longer admin-only
- task detail route exists
- inbox page contains tabs for owner / initiated / cc
- inbox page contains filters and status summary
- detail page contains timeline and action region

- [ ] **Step 2: Run targeted frontend tests to verify failure**

Run: `node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs`
Expected: FAIL because routes and real UI are missing.

- [ ] **Step 3: Add frontend API wrapper**

Implement `frontend/src/api/employeeTasks.js` with helpers for:
- list tasks
- get task detail
- start task
- submit result
- confirm / reject / close
- nudge

- [ ] **Step 4: Replace placeholder `MyTasks.vue`**

Build:
- status summary cards
- tabs for `我的任务`, `我发起的`, `抄送我的`
- filters by status, priority, source module
- task table / list rows with deep links

- [ ] **Step 5: Build `TaskDetail.vue`**

Include:
- task header
- linked business object card
- participant display
- due time / priority
- completion proof form driven by task schema
- action buttons by role and state
- timeline section

- [ ] **Step 6: Update routes, menu, and role access**

Change:
- `/my-tasks` to allow all employee-facing roles instead of admin-only
- add `/my-tasks/:taskId`
- keep approval center entry but align it to the collaboration model

- [ ] **Step 7: Re-run frontend tests**

Run: `node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs`
Expected: PASS.

- [ ] **Step 8: Run type-check**

Run: `npm -C frontend run type-check`
Expected: PASS.

- [ ] **Step 9: Commit frontend task center**

```bash
git add frontend/src/api/employeeTasks.js frontend/src/views/approval/MyTasks.vue frontend/src/views/approval/TaskDetail.vue frontend/src/router/index.js frontend/src/config/menuGroups.js frontend/src/config/rolePermissions.js frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
git commit -m "feat: build employee task center frontend"
```

## Task 6: Add Automatic Source Adapters For Cost Entry And Performance Confirmation

**Files:**
- Modify: `backend/routers/expense_management.py`
- Modify: `backend/routers/performance_management.py`
- Create: `backend/tests/test_employee_task_sources.py`
- Modify: `frontend/src/views/finance/ExpenseManagement.vue`
- Modify: `frontend/src/views/hr/PerformanceManagement.vue`

- [ ] **Step 1: Write failing source-adapter tests**

Cover:
- creating or refreshing a cost-entry task when monthly cost action needs employee follow-up
- creating or refreshing a performance-confirmation task
- task points back to the correct module and record
- repeated source runs update existing open task instead of creating duplicates

- [ ] **Step 2: Run targeted source tests to verify failure**

Run: `pytest backend/tests/test_employee_task_sources.py -v`
Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Implement cost-entry adapter**

Hook the expense flow so a task is created or refreshed when:
- monthly cost data is missing
- cost confirmation / entry action is required

Persist:
- `source_module = expense-management`
- source record identifiers
- owner derived from the chosen business rule

- [ ] **Step 4: Implement performance-confirmation adapter**

Hook performance management so a task is created or refreshed when:
- a score requires employee confirmation
- a manager review requires employee follow-up

- [ ] **Step 5: Add task-context handling to business pages**

Expense and performance pages should:
- accept task query params or route params
- show a lightweight “from task” banner
- call task completion API after successful business action

- [ ] **Step 6: Re-run source tests**

Run: `pytest backend/tests/test_employee_task_sources.py -v`
Expected: PASS.

- [ ] **Step 7: Add focused frontend smoke where needed**

Run:
- `node --test frontend/scripts/employeeTaskUi.test.mjs`
- any existing finance / performance UI tests impacted by route context

- [ ] **Step 8: Commit automatic source adapters**

```bash
git add backend/routers/expense_management.py backend/routers/performance_management.py backend/tests/test_employee_task_sources.py frontend/src/views/finance/ExpenseManagement.vue frontend/src/views/hr/PerformanceManagement.vue
git commit -m "feat: add employee task source adapters"
```

## Task 7: Add Replenishment Bridge Task Template Instead Of Premature Automation

**Files:**
- Modify: `frontend/src/views/procurement/PurchaseOrders.vue`
- Create: `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md`
- Modify: `docs/superpowers/specs/2026-04-11-employee-collaboration-task-center-design.md`

- [ ] **Step 1: Document the current procurement maturity constraint**

Capture that:
- replenishment / purchase order runtime is still placeholder-only
- true automatic replenishment task generation is deferred

- [ ] **Step 2: Add a bridge placeholder in `PurchaseOrders.vue`**

Show:
- that replenishment confirmation will join the task center
- current v1 path uses task templates or manual task creation until procurement runtime matures

- [ ] **Step 3: Update runbook and spec notes**

Clarify:
- v1 automatic sources are cost entry and performance confirmation
- replenishment is represented as a bridge source, not a false-complete automation

- [ ] **Step 4: Commit the replenishment bridge note**

```bash
git add frontend/src/views/procurement/PurchaseOrders.vue docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md docs/superpowers/specs/2026-04-11-employee-collaboration-task-center-design.md
git commit -m "docs: document replenishment task bridge"
```

## Task 8: Verification And Handoff

**Files:**
- Verify only

- [ ] **Step 1: Run targeted backend task-center test suite**

Run:
```bash
pytest backend/tests/test_employee_task_schema.py backend/tests/test_employee_task_service.py backend/tests/test_employee_task_routes.py backend/tests/test_employee_task_notifications.py backend/tests/test_employee_task_sources.py -v
```
Expected: PASS.

- [ ] **Step 2: Run impacted notification and task-center regression tests**

Run:
```bash
pytest backend/tests/test_notification_config_routes.py backend/tests/test_task_center_api.py -v
```
Expected: PASS or unchanged compatibility behavior.

- [ ] **Step 3: Run focused frontend checks**

Run:
```bash
node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```
Expected: PASS.

- [ ] **Step 4: Sanity-check the worktree diff**

Run:
```bash
git status --short
git log --oneline --decorate -n 8
```
Expected: Only task-center-related changes are present.

- [ ] **Step 5: Finalize runbook**

Ensure `docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md` explains:
- task categories
- state semantics
- notifications
- source adapters
- replenishment bridge limitation

- [ ] **Step 6: Commit verification and docs**

```bash
git add docs/guides/EMPLOYEE_TASK_CENTER_RUNBOOK.md
git commit -m "docs: add employee task center runbook"
```

## Notes For Execution

- Use TDD for each task block before implementation.
- Keep the collaboration task domain separate from the existing `task_center_*` system-job tables.
- Do not claim replenishment automation exists in v1; implement the bridge honestly.
- Prefer route-level task context and business-page callbacks over embedding every domain form inside the task inbox.
- Keep reminder delivery inside the existing notification infrastructure.

Plan complete and saved to `docs/superpowers/plans/2026-04-11-employee-collaboration-task-center-v1.md`. Ready to execute?
