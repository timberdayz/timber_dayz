# Training Management Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-phase ERP training management loop that assigns training, creates collaboration tasks, reuses notifications, tracks results, and supports onboarding plus one role-certification pilot without building a custom LMS.

**Architecture:** Add a dedicated training business domain inside ERP and connect it to the existing employee collaboration task center and notification center. Keep learning and exam delivery in an external platform, while ERP remains the source of truth for assignment, deadlines, confirmation, retraining, dashboards, and business linkage.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, existing employee task center, existing notification center, Vue 3, Element Plus, Pinia, Vite, pytest

---

## File Structure

### Training backend domain

- Create: `backend/schemas/training.py`
  - Pydantic contracts for training program, package, assignment, result, and dashboard payloads
- Create: `backend/services/training_service.py`
  - Main training business service for CRUD, assignment, result updates, and dashboard summaries
- Create: `backend/routers/training.py`
  - FastAPI routes for training management and employee-facing training detail retrieval
- Create: `backend/tests/test_training_service.py`
  - Unit tests for training domain rules and assignment lifecycle
- Create: `backend/tests/test_training_router.py`
  - API tests for training routes and response models

### Database and schema alignment

- Modify: `modules/core/db/schema.py`
  - Add training ORM models and relationships
- Modify: migration location used by the repository for schema updates
  - Add migration for training tables only after ORM shape is finalized in tests

### Task and notification integration

- Modify: existing employee collaboration task service files used by the repository task center
  - Add training task types and training-source task creation helpers
- Modify: existing notification service / notification type definitions used by the repository
  - Add training notification types and delivery helpers
- Create: `backend/tests/test_training_task_integration.py`
  - Tests for training task generation, status mapping, and reminders

### Frontend training management

- Create: `frontend/src/api/training.js`
  - API wrapper for training program, assignment, result, and dashboard endpoints
- Create: `frontend/src/views/training/TrainingOverview.vue`
  - Admin overview and KPI summary
- Create: `frontend/src/views/training/TrainingPrograms.vue`
  - Program and package management page
- Create: `frontend/src/views/training/TrainingAssignments.vue`
  - Assignment management page
- Create: `frontend/src/views/training/TrainingResults.vue`
  - Result tracking and exception handling page
- Create: `frontend/src/views/training/TrainingTaskDetail.vue`
  - Employee/supervisor training detail page linked from tasks
- Modify: frontend router and navigation files used by the existing Vue app
  - Add training routes and menu entries
- Modify: `frontend/src/views/approval/MyTasks.vue`
  - Ensure training task rows deep-link cleanly into the training detail page
- Modify: `frontend/src/views/messages/SystemNotifications.vue`
  - Add labels and routes for training notification types

### Documentation

- Modify: runbook or guide location if the implementation introduces operator workflow docs
  - Add one concise operator guide for HR / training admins after UI and endpoints stabilize

## Task 1: Confirm Existing Task And Notification Integration Points

**Files:**
- Read: `docs/superpowers/specs/2026-04-11-employee-collaboration-task-center-design.md`
- Read: `frontend/src/views/approval/MyTasks.vue`
- Read: `frontend/src/views/messages/SystemNotifications.vue`
- Read: backend task and notification service/router files already powering these pages

- [ ] **Step 1: Locate the exact backend task and notification extension points**

Run: `rg -n "task_assigned|task_due_soon|task_overdue|employeeTasks|notifications|notification_type|pending_confirmation" backend frontend`
Expected: identify the backend service, schema, router, and notification-type definitions that training should extend

- [ ] **Step 2: Record the concrete files to modify before implementation starts**

Run: `rg -n "class .*Task|def .*task|notification_type|markAsRead|getNotifications" backend frontend`
Expected: produce a short implementation note listing exact files for task creation, task status updates, notification creation, and frontend route handling

- [ ] **Step 3: Commit the integration inventory if saved to a repo doc**

```bash
git add <only-if-a-doc-was-created>
git commit -m "docs: capture training integration points"
```

## Task 2: Write Failing Backend Tests For The Training Domain

**Files:**
- Create: `backend/tests/test_training_service.py`
- Create: `backend/tests/test_training_router.py`

- [ ] **Step 1: Write the failing service test for assignment lifecycle**

```python
async def test_create_training_assignment_defaults_to_pending_study(async_session):
    service = TrainingService(async_session)
    assignment = await service.create_assignment(
        program_name="New Hire Basics",
        category="onboarding",
        employee_id=1,
        due_days=7,
    )

    assert assignment.business_status == "pending_study"
    assert assignment.linked_task_id is None
```

- [ ] **Step 2: Write the failing service test for status mapping**

```python
async def test_training_passed_maps_to_completed_task(async_session):
    service = TrainingService(async_session)
    assignment = await service.create_assignment(
        program_name="Operations Certification",
        category="role_certification",
        employee_id=1,
        due_days=14,
    )

    mapped_status = service.map_business_status_to_task_status("passed")

    assert mapped_status == "completed"
```

- [ ] **Step 3: Write the failing router test for overview payload**

```python
def test_training_overview_returns_summary_fields(client):
    response = client.get("/api/training/overview")

    assert response.status_code == 200
    payload = response.json()
    assert "completion_rate" in payload
    assert "overdue_count" in payload
    assert "retraining_required_count" in payload
```

- [ ] **Step 4: Run backend training tests to verify they fail**

Run: `pytest backend/tests/test_training_service.py backend/tests/test_training_router.py -v`
Expected: FAIL because the training schema, service, and router do not exist yet

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_training_service.py backend/tests/test_training_router.py
git commit -m "test: add failing training domain tests"
```

## Task 3: Implement Training ORM Models And Pydantic Schemas

**Files:**
- Modify: `modules/core/db/schema.py`
- Create: `backend/schemas/training.py`
- Test: `backend/tests/test_training_service.py`

- [ ] **Step 1: Add the failing ORM-facing assertions if needed**

```python
assert hasattr(schema, "TrainingProgram")
assert hasattr(schema, "TrainingAssignment")
```

- [ ] **Step 2: Add minimal ORM models in the repository SSOT**

```python
class TrainingProgram(Base):
    __tablename__ = "training_programs"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)
    is_required = Column(Boolean, default=True, nullable=False)
    pass_score = Column(Integer, nullable=True)
    due_days = Column(Integer, nullable=True)
    retrain_cycle_days = Column(Integer, nullable=True)
    requires_confirmation = Column(Boolean, default=False, nullable=False)
    confirmation_role_type = Column(String(64), nullable=True)
    version = Column(String(32), nullable=False, default="v1")
```

- [ ] **Step 3: Add minimal assignment and result models**

```python
class TrainingAssignment(Base):
    __tablename__ = "training_assignments"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("training_programs.id"), nullable=False)
    employee_id = Column(Integer, nullable=False, index=True)
    business_status = Column(String(64), nullable=False, default="pending_study")
    linked_task_id = Column(String(64), nullable=True)
```

- [ ] **Step 4: Add matching Pydantic response models**

```python
class TrainingOverviewResponse(BaseModel):
    completion_rate: float
    overdue_count: int
    failed_count: int
    retraining_required_count: int
```

- [ ] **Step 5: Run training service tests**

Run: `pytest backend/tests/test_training_service.py -v`
Expected: still FAIL in service-layer logic, but ORM imports and schema objects now exist

- [ ] **Step 6: Commit**

```bash
git add modules/core/db/schema.py backend/schemas/training.py
git commit -m "feat: add training domain schema models"
```

## Task 4: Implement Training Service With Minimal Business Rules

**Files:**
- Create: `backend/services/training_service.py`
- Test: `backend/tests/test_training_service.py`

- [ ] **Step 1: Implement status mapping in the service**

```python
TASK_STATUS_MAP = {
    "pending_study": "pending",
    "studying": "in_progress",
    "pending_exam": "in_progress",
    "pending_confirmation": "pending_confirmation",
    "passed": "completed",
    "failed": "rejected",
    "closed": "closed",
}
```

- [ ] **Step 2: Implement minimal assignment creation**

```python
async def create_assignment(self, *, program_name: str, category: str, employee_id: int, due_days: int):
    assignment = TrainingAssignment(
        employee_id=employee_id,
        business_status="pending_study",
    )
    self.session.add(assignment)
    await self.session.flush()
    return assignment
```

- [ ] **Step 3: Implement minimal overview summary method**

```python
async def get_overview(self) -> dict:
    return {
        "completion_rate": 0.0,
        "overdue_count": 0,
        "failed_count": 0,
        "retraining_required_count": 0,
    }
```

- [ ] **Step 4: Run service tests**

Run: `pytest backend/tests/test_training_service.py -v`
Expected: PASS for current service tests

- [ ] **Step 5: Commit**

```bash
git add backend/services/training_service.py backend/tests/test_training_service.py
git commit -m "feat: add minimal training service"
```

## Task 5: Implement Training API Routes

**Files:**
- Create: `backend/routers/training.py`
- Modify: backend router registration file used by the application
- Test: `backend/tests/test_training_router.py`

- [ ] **Step 1: Add the failing route registration check if needed**

```python
def test_training_router_is_registered(client):
    response = client.get("/api/training/overview")
    assert response.status_code != 404
```

- [ ] **Step 2: Add the minimal overview route with `response_model`**

```python
router = APIRouter(prefix="/api/training", tags=["training"])

@router.get("/overview", response_model=TrainingOverviewResponse)
async def get_training_overview(db: AsyncSession = Depends(get_async_db)):
    service = TrainingService(db)
    return await service.get_overview()
```

- [ ] **Step 3: Add minimal routes for programs, assignments, and task detail lookup**

```python
@router.get("/assignments/{assignment_id}", response_model=TrainingAssignmentResponse)
async def get_training_assignment_detail(...):
    ...
```

- [ ] **Step 4: Run router tests**

Run: `pytest backend/tests/test_training_router.py -v`
Expected: PASS for overview and initial route registration tests

- [ ] **Step 5: Commit**

```bash
git add backend/routers/training.py <router-registration-file> backend/tests/test_training_router.py
git commit -m "feat: add training api routes"
```

## Task 6: Add Task-Center Integration For Training Assignments

**Files:**
- Modify: existing backend employee task service files identified in Task 1
- Create: `backend/tests/test_training_task_integration.py`
- Test: existing employee task API tests if present

- [ ] **Step 1: Write the failing integration test for task creation**

```python
async def test_training_assignment_creates_collaboration_task(async_session):
    service = TrainingService(async_session)
    assignment = await service.create_assignment(
        program_name="New Hire Basics",
        category="onboarding",
        employee_id=1,
        due_days=7,
    )

    await service.ensure_collaboration_task(assignment.id)

    refreshed = await service.get_assignment(assignment.id)
    assert refreshed.linked_task_id is not None
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `pytest backend/tests/test_training_task_integration.py -v`
Expected: FAIL because training task creation is not wired into the task domain yet

- [ ] **Step 3: Implement the minimal task creation adapter**

```python
async def ensure_collaboration_task(self, assignment_id: int) -> str:
    task_id = await self.task_service.create_task(
        task_type="training_onboarding",
        source_module="training",
        source_record_id=str(assignment_id),
        owner_user_id=<resolved owner>,
        status="pending",
    )
    assignment.linked_task_id = task_id
    await self.session.flush()
    return task_id
```

- [ ] **Step 4: Run the training task integration test**

Run: `pytest backend/tests/test_training_task_integration.py -v`
Expected: PASS

- [ ] **Step 5: Run focused existing employee-task tests if present**

Run: `pytest backend/tests -k "employee task or collaboration task" -v`
Expected: PASS without regressions in existing task-center behavior

- [ ] **Step 6: Commit**

```bash
git add backend/services/training_service.py <task-service-files> backend/tests/test_training_task_integration.py
git commit -m "feat: connect training assignments to task center"
```

## Task 7: Add Notification-Center Integration For Training Events

**Files:**
- Modify: backend notification service files identified in Task 1
- Modify: notification type constants or mappings used by the repository
- Test: `backend/tests/test_training_task_integration.py`

- [ ] **Step 1: Add the failing test for training notification creation**

```python
async def test_training_assignment_emits_assignment_notification(async_session):
    service = TrainingService(async_session)
    assignment = await service.create_assignment(
        program_name="New Hire Basics",
        category="onboarding",
        employee_id=1,
        due_days=7,
    )

    await service.emit_assignment_notification(assignment.id)

    notifications = await list_training_notifications(async_session, employee_id=1)
    assert notifications[0].notification_type == "training_assigned"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest backend/tests/test_training_task_integration.py -k notification -v`
Expected: FAIL because training notification types are not defined yet

- [ ] **Step 3: Add new training notification types and minimal emit helper**

```python
TRAINING_NOTIFICATION_TYPES = {
    "training_assigned",
    "training_due_soon",
    "training_overdue",
    "training_failed",
    "training_retraining_required",
    "training_confirmation_pending",
}
```

- [ ] **Step 4: Run the focused notification integration test**

Run: `pytest backend/tests/test_training_task_integration.py -k notification -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add <notification-service-files> backend/services/training_service.py backend/tests/test_training_task_integration.py
git commit -m "feat: add training notifications"
```

## Task 8: Add Frontend API Layer And Training Overview Page

**Files:**
- Create: `frontend/src/api/training.js`
- Create: `frontend/src/views/training/TrainingOverview.vue`

- [ ] **Step 1: Add the API wrapper**

```javascript
export default {
  getOverview() {
    return request.get('/api/training/overview')
  },
}
```

- [ ] **Step 2: Add the minimal overview page**

```vue
<template>
  <PageHeader title="培训总览" subtitle="查看培训完成率、逾期、未通过与待复训情况" />
</template>
```

- [ ] **Step 3: Run the frontend build or targeted lint command**

Run: `<frontend build or lint command used by the repo>`
Expected: PASS with the new API import and view component

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/training.js frontend/src/views/training/TrainingOverview.vue
git commit -m "feat: add training overview page"
```

## Task 9: Add Training Management Pages And Routes

**Files:**
- Create: `frontend/src/views/training/TrainingPrograms.vue`
- Create: `frontend/src/views/training/TrainingAssignments.vue`
- Create: `frontend/src/views/training/TrainingResults.vue`
- Create: `frontend/src/views/training/TrainingTaskDetail.vue`
- Modify: frontend router and menu configuration files

- [ ] **Step 1: Add failing frontend smoke assertions if the repository has route tests**

```javascript
expect(routes.some((route) => route.path === '/training/overview')).toBe(true)
```

- [ ] **Step 2: Add routes and menu entries**

```javascript
{
  path: '/training/overview',
  component: () => import('@/views/training/TrainingOverview.vue'),
}
```

- [ ] **Step 3: Add the minimal management pages**

```vue
<template>
  <PageHeader title="培训项目" subtitle="管理培训项目和培训包" />
</template>
```

- [ ] **Step 4: Add the training task detail page with external-link section**

```vue
<template>
  <PageHeader title="培训任务详情" subtitle="查看要求、结果、确认与外部学习入口" />
</template>
```

- [ ] **Step 5: Run the frontend build or route-related tests**

Run: `<frontend build or route test command used by the repo>`
Expected: PASS with all new pages and routes registered

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/training frontend/src/router <menu-config-files>
git commit -m "feat: add training management pages"
```

## Task 10: Connect Existing Task And Notification Pages To Training Routes

**Files:**
- Modify: `frontend/src/views/approval/MyTasks.vue`
- Modify: `frontend/src/views/messages/SystemNotifications.vue`

- [ ] **Step 1: Add a failing assertion or manual checklist for training route resolution**

```javascript
expect(getNotificationRoute('training_assigned')).toBe('/training/tasks/123')
```

- [ ] **Step 2: Update task page deep-link logic for training task types**

```javascript
const openTask = (taskId, row) => {
  if (row.source_module === 'training') {
    router.push(`/training/tasks/${row.source_record_id}`)
    return
  }
  router.push(`/my-tasks/${taskId}`)
}
```

- [ ] **Step 3: Update notification labels and route helpers**

```javascript
case 'training_assigned':
  return '培训任务'
```

- [ ] **Step 4: Run the frontend build or smoke test**

Run: `<frontend build or smoke command used by the repo>`
Expected: PASS and no regression to existing task or notification pages

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/approval/MyTasks.vue frontend/src/views/messages/SystemNotifications.vue
git commit -m "feat: connect training with task and notification pages"
```

## Task 11: Add Dashboard, Pilot Defaults, And Operator Documentation

**Files:**
- Modify: `backend/services/training_service.py`
- Modify: `frontend/src/views/training/TrainingOverview.vue`
- Create or Modify: operator guide doc path chosen for training admins

- [ ] **Step 1: Add pilot-oriented overview summaries**

```python
return {
    "completion_rate": completion_rate,
    "overdue_count": overdue_count,
    "failed_count": failed_count,
    "retraining_required_count": retraining_required_count,
    "onboarding_assignments": onboarding_assignments,
    "role_certification_assignments": role_certification_assignments,
}
```

- [ ] **Step 2: Surface pilot metrics on the overview page**

```vue
<el-card>
  <div>入职培训中</div>
  <div>{{ summary.onboarding_assignments }}</div>
</el-card>
```

- [ ] **Step 3: Write a concise operator guide**

Content should cover:
- how HR creates an onboarding program
- how HR assigns the pilot role-certification package
- how results are imported or updated
- how supervisors confirm completion where required

- [ ] **Step 4: Run targeted backend and frontend verification**

Run: `pytest backend/tests/test_training_service.py backend/tests/test_training_router.py backend/tests/test_training_task_integration.py -v`
Expected: PASS

Run: `<frontend build or smoke command used by the repo>`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/training_service.py frontend/src/views/training/TrainingOverview.vue <operator-guide-doc>
git commit -m "docs: add training pilot operations guide"
```

## Task 12: Add Migration, Final Verification, And Handoff

**Files:**
- Modify: migration files for the repository
- Review: all changed training backend/frontend files

- [ ] **Step 1: Add the training schema migration**

The migration should create only the training tables required by phase 1:
- training programs
- training packages
- training assignments
- training results
- optional training confirmations

- [ ] **Step 2: Run migration and backend verification**

Run: `<repo migration command>`
Expected: training tables created successfully

Run: `pytest backend/tests/test_training_service.py backend/tests/test_training_router.py backend/tests/test_training_task_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run frontend verification**

Run: `<frontend build or smoke command used by the repo>`
Expected: PASS

- [ ] **Step 4: Run targeted manual verification checklist**

Verify:
- create one onboarding program
- assign it to one employee
- confirm a training task appears in `我的任务`
- confirm a `training_assigned` notification appears
- open training task detail page
- update result to passed
- verify task status becomes completed

- [ ] **Step 5: Commit**

```bash
git add <migration-files> backend frontend
git commit -m "feat: deliver training management phase 1"
```

## Notes For Execution

- Keep phase 1 limited to onboarding plus one role-certification pilot.
- Do not build a custom LMS, custom video player, or custom exam engine in this plan.
- Reuse the existing task center and notification center instead of creating a second reminder workflow.
- Use `AsyncSession`, `get_async_db()`, and `response_model` on typed routes.
- Keep ORM models in `modules/core/db/schema.py`.
- Keep frontend work inside the existing Vue 3 + Element Plus + Pinia + Vite stack.

Plan complete and saved to `docs/superpowers/plans/2026-04-12-training-management-phase1.md`. Ready to execute?
