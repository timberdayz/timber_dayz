# B类数据云端追平控制台 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `/cloud-sync` 页面从表级技术操作台重构为面向中文管理员的 B 类数据云端追平控制台，主打整体状态、自动同步控制、手动增量追平和异常恢复，同时把表级能力下沉到高级诊断。

**Architecture:** 后端先补齐“总览 / 运行时 / 历史 / 设置 / 异常重试 / 立即追平”控制面契约，前端再围绕这些契约重构首页，保留现有表级接口作为高级诊断层。实现以最小破坏替换现有 `/cloud-sync` 页面，不新增第二个入口，不让首页继续依赖单表选择。所有行为改动都用 TDD 驱动，先补测试，再写最小实现。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Pinia, Element Plus, Vite, pytest

---

## File Structure

### Backend
- Modify: `backend/routers/cloud_sync.py`
- Modify: `backend/schemas/cloud_sync_admin.py`
- Modify: `backend/services/cloud_sync_admin_query_service.py`
- Modify: `backend/services/cloud_sync_admin_command_service.py`
- Modify: `backend/services/cloud_b_class_auto_sync_factory.py`
- Modify: `backend/services/cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/services/cloud_b_class_auto_sync_worker.py`

### Frontend
- Modify: `frontend/src/api/cloudSync.js`
- Modify: `frontend/src/stores/cloudSync.js`
- Modify: `frontend/src/views/CloudSyncManagement.vue`

### Tests
- Modify: `backend/tests/test_cloud_b_class_auto_sync_router.py`
- Modify: `backend/tests/test_cloud_sync_admin_query_service.py`
- Modify: `backend/tests/test_cloud_sync_admin_command_service.py`

### Docs / Workflow
- Create: `docs/superpowers/specs/2026-04-06-b-class-cloud-catch-up-console-design.md`
- Create: `docs/superpowers/plans/2026-04-06-b-class-cloud-catch-up-console-implementation.md`

---

## Task 1: Add Overall Catch-Up Backend Contracts

**Files:**
- Modify: `backend/routers/cloud_sync.py`
- Modify: `backend/schemas/cloud_sync_admin.py`
- Modify: `backend/services/cloud_sync_admin_query_service.py`
- Modify: `backend/services/cloud_sync_admin_command_service.py`
- Test: `backend/tests/test_cloud_b_class_auto_sync_router.py`
- Test: `backend/tests/test_cloud_sync_admin_query_service.py`
- Test: `backend/tests/test_cloud_sync_admin_command_service.py`

- [ ] **Step 1: Write failing router tests for the new control-plane endpoints**

Add tests for:
- `GET /api/cloud-sync/overview`
- `GET /api/cloud-sync/runtime`
- `GET /api/cloud-sync/history`
- `GET /api/cloud-sync/settings`
- `PUT /api/cloud-sync/settings`
- `POST /api/cloud-sync/sync-now`
- `POST /api/cloud-sync/retry-failed`

Example:

```python
async def test_overview_endpoint_returns_catch_up_summary():
    response = await client.get("/api/cloud-sync/overview")
    assert response.status_code == 200
    assert "catch_up_status" in response.json()
```

- [ ] **Step 2: Run the router tests and verify they fail for the expected missing-contract reason**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_router.py -q
```

Expected:
- FAIL because the new endpoints do not exist yet

- [ ] **Step 3: Write failing query-service tests for overview/runtime/history serialization**

Cover:
- overall catch-up status
- failed / partial_success visibility
- recent run history shape
- settings payload shape

Example:

```python
async def test_overview_includes_failed_and_last_success():
    payload = await service.get_overview_summary(runtime_health={...})
    assert payload["exception_task_count"] == 1
    assert payload["last_success_at"] is not None
```

- [ ] **Step 4: Run the service tests and verify they fail for the expected missing-method reason**

Run:

```bash
pytest backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py -q
```

Expected:
- FAIL because the new methods and schema fields do not exist yet

- [ ] **Step 5: Implement the minimal backend schema additions**

In `backend/schemas/cloud_sync_admin.py`, add response models for:
- overview summary
- runtime status
- history rows
- settings payload
- sync-now / retry-failed command responses

Keep status values business-oriented enough for frontend mapping, but still explicit:
- `up_to_date`
- `catching_up`
- `backlog`
- `degraded`

- [ ] **Step 6: Implement minimal query methods**

In `backend/services/cloud_sync_admin_query_service.py`, add:
- `get_overview_summary(runtime_health)`
- `get_runtime_summary(runtime_health)`
- `list_history(limit=20)`
- `get_settings()`

Rules:
- treat `failed + partial_success` as exception pressure
- calculate a top-level catch-up state from queue + worker + latest success
- do not expose secrets in any summary field

- [ ] **Step 7: Implement minimal command methods**

In `backend/services/cloud_sync_admin_command_service.py`, add:
- `sync_now()`
- `update_settings(enabled: bool)`
- `retry_failed()`

Rules:
- `sync_now()` enqueues or coalesces the required work to bring cloud state to latest, not a single user-selected table
- `update_settings()` reflects pause/resume semantics
- paused mode keeps backlog-producing behavior intact
- `retry_failed()` only affects `failed` and `partial_success`

- [ ] **Step 8: Wire the new endpoints in `backend/routers/cloud_sync.py`**

Add the new routes using `require_admin` and `get_async_db()`.

Keep existing table/task endpoints in place; do not delete them yet.

- [ ] **Step 9: Re-run the backend tests**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py -q
```

Expected:
- PASS for the new control-plane contract tests

- [ ] **Step 10: Commit**

```bash
git add backend/routers/cloud_sync.py backend/schemas/cloud_sync_admin.py backend/services/cloud_sync_admin_query_service.py backend/services/cloud_sync_admin_command_service.py backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py
git commit -m "feat: add b-class cloud catch-up control plane APIs"
```

---

## Task 2: Harden Runtime And Worker Semantics For Pause/Overall Catch-Up

**Files:**
- Modify: `backend/services/cloud_b_class_auto_sync_factory.py`
- Modify: `backend/services/cloud_b_class_auto_sync_runtime.py`
- Modify: `backend/services/cloud_b_class_auto_sync_worker.py`
- Test: extend existing cloud sync runtime/worker tests if needed

- [ ] **Step 1: Write a failing test for settings-driven pause semantics**

Add a test that proves:
- auto-sync can be paused without pretending the worker runtime vanished
- pause means backlog can exist while execution is suspended

- [ ] **Step 2: Run the relevant tests and verify the missing behavior**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py -q
```

Expected:
- FAIL or missing coverage for pause-aware semantics

- [ ] **Step 3: Implement the minimal runtime/worker changes**

Goals:
- distinguish “runtime healthy” from “auto-sync enabled”
- let settings drive whether runnable tasks are executed
- keep existing environment guardrails for collection/local ownership

Do not refactor the whole runtime shape unless the tests demand it.

- [ ] **Step 4: Re-run runtime/worker tests**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py -q
```

Expected:
- PASS with stable pause/resume semantics

- [ ] **Step 5: Commit**

```bash
git add backend/services/cloud_b_class_auto_sync_factory.py backend/services/cloud_b_class_auto_sync_runtime.py backend/services/cloud_b_class_auto_sync_worker.py backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py
git commit -m "feat: support pause-aware b-class cloud catch-up runtime"
```

---

## Task 3: Refactor Frontend Data Layer To Use The New Overall Contracts

**Files:**
- Modify: `frontend/src/api/cloudSync.js`
- Modify: `frontend/src/stores/cloudSync.js`

- [ ] **Step 1: Write the target store shape into the plan before editing**

The store should own:
- overview
- runtime
- history
- settings
- diagnostics (`tables`, `tasks`, `events`)
- action loading flags by area

- [ ] **Step 2: Add failing frontend-facing expectations via minimal smoke checks**

If frontend test infrastructure is absent, use type/build failure as the red phase.

Target contract:
- no primary store method should require `sourceTableName` for the main sync action
- diagnostics stay optional/lazy

- [ ] **Step 3: Update `frontend/src/api/cloudSync.js`**

Add:
- `getOverview()`
- `getRuntime()`
- `getHistory()`
- `getSettings()`
- `updateSettings(payload)`
- `syncNow()`
- `retryFailed()`

Keep existing table/task methods for diagnostics.

- [ ] **Step 4: Update `frontend/src/stores/cloudSync.js`**

Add state and actions for:
- `overview`
- `runtime`
- `history`
- `settings`
- `syncNow()`
- `toggleAutoSync()`
- `retryFailed()`

Keep diagnostics loading separate so the homepage can load without blocking on the heavy table/task surfaces.

- [ ] **Step 5: Run frontend type/build verification**

Run:

```bash
npm --prefix frontend run build
```

Expected:
- FAIL first if the page still references the old API/store shape

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/cloudSync.js frontend/src/stores/cloudSync.js
git commit -m "feat: add cloud catch-up frontend data contracts"
```

---

## Task 4: Rebuild `/cloud-sync` As A Chinese-First Catch-Up Console

**Files:**
- Modify: `frontend/src/views/CloudSyncManagement.vue`

- [ ] **Step 1: Write a failing page-level acceptance checklist**

Use the design spec as the checklist:
- no English operational labels in the primary interface
- homepage no longer centers table selection
- primary actions are `立即同步到最新`, `开启/暂停自动同步`, `重试异常任务`
- diagnostics are visually secondary

- [ ] **Step 2: Run a build to lock in the current failure surface**

Run:

```bash
npm --prefix frontend run build
```

Expected:
- PASS or FAIL, but record baseline before editing

- [ ] **Step 3: Rebuild the page shell**

Replace the current top layout with:
- 标题区
- 总览状态卡
- 主操作区
- 最近同步状态
- 最近同步记录
- 高级诊断折叠区

Use full Chinese copy for all primary labels.

- [ ] **Step 4: Remove single-table selection from the primary action path**

Delete from the main action area:
- source table select
- batch size input
- single-table action buttons

Keep single-table capabilities only inside diagnostics.

- [ ] **Step 5: Promote exception visibility**

The homepage must visibly surface:
- exception task count
- degraded catch-up state
- recent error summary

Do not bury failure pressure below the fold.

- [ ] **Step 6: Add a diagnostics section**

Diagnostics can include:
- table state table
- task queue
- event list
- per-task drawer

But they must be visually secondary:
- collapse by default or place after the core console sections

- [ ] **Step 7: Re-run frontend build verification**

Run:

```bash
npm --prefix frontend run build
```

Expected:
- PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/CloudSyncManagement.vue
git commit -m "feat: redesign cloud sync page as b-class catch-up console"
```

---

## Task 5: Align Diagnostics With Recovery Needs

**Files:**
- Modify: `backend/schemas/cloud_sync_admin.py`
- Modify: `backend/services/cloud_sync_admin_query_service.py`
- Modify: `frontend/src/views/CloudSyncManagement.vue`

- [ ] **Step 1: Write a failing test or acceptance expectation for recovery fields**

Need visibility for:
- `lease_expires_at`
- `next_retry_at`
- richer failure/partial-success context

- [ ] **Step 2: Implement missing recovery fields in backend serialization**

Expose the required fields in diagnostic responses without leaking secrets.

- [ ] **Step 3: Render those fields in the diagnostic drawer/panels**

The admin should be able to understand:
- whether a running task is stale
- when a retry will happen
- whether partial success is projection-related

- [ ] **Step 4: Re-run backend and frontend verification**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py -q
npm --prefix frontend run build
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/cloud_sync_admin.py backend/services/cloud_sync_admin_query_service.py frontend/src/views/CloudSyncManagement.vue backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py
git commit -m "feat: enrich cloud catch-up diagnostics"
```

---

## Task 6: Final Verification And Handoff

**Files:**
- Review only unless fixes are required in files above

- [ ] **Step 1: Run focused backend verification**

Run:

```bash
pytest backend/tests/test_cloud_b_class_auto_sync_router.py backend/tests/test_cloud_sync_admin_query_service.py backend/tests/test_cloud_sync_admin_command_service.py backend/tests/test_cloud_b_class_auto_sync_runtime.py backend/tests/test_cloud_b_class_auto_sync_worker.py -q
```

Expected:
- PASS

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm --prefix frontend run build
```

Expected:
- PASS

- [ ] **Step 3: Run a short manual smoke checklist**

Verify:
- admin opens `/cloud-sync` and sees Chinese-first catch-up console
- homepage shows overall status, not table-first operations
- `立即同步到最新` no longer asks for a single table
- automatic sync toggle reflects pause/resume semantics
- diagnostics still allow table/task inspection

- [ ] **Step 4: Review diff and prepare handoff**

Run:

```bash
git status --short
git diff --stat
```

- [ ] **Step 5: Use verification-before-completion before claiming success**

Do not claim completion until the verification commands above have run and passed in this worktree.

---

## Notes For Execution

- Implement Task 1 before any frontend page changes.
- Keep the old diagnostic APIs available during the transition; do not break operator recovery tools while rebuilding the homepage.
- Avoid expanding scope into new permissions, new menus, or cross-page refactors unless directly required by the catch-up console.
- Prefer minimal backend additions over large service rewrites.

Plan complete and saved to `docs/superpowers/plans/2026-04-06-b-class-cloud-catch-up-console-implementation.md`. Execution will continue in this worktree using TDD.

