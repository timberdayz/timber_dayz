# Collection Config Queue Runner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将采集配置执行改造成“配置运行实例入队 + 单 worker 串行消费”的模型，让定时配置和手动运行配置都按全局单队列顺序执行，并在前一个主账号配置完成后立即续跑下一个。

**Architecture:** 新增 `CollectionConfigRun` 作为配置级执行实例，APScheduler 与手动运行配置入口只负责创建 queued run，不再直接后台起采集。新增 `CollectionQueueRunner` 常驻消费 queued run，顺序展开并执行其下的 `CollectionTask`，同时给快速采集增加运行中配置闸门。

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, APScheduler, Playwright async, pytest

---

## File Map

### New Files

- `backend/services/collection_config_run_service.py`
  - 配置运行实例的创建、去重、领取、状态流转、结果汇总
- `backend/services/collection_queue_runner.py`
  - 单 worker 配置队列消费器
- `backend/tests/test_collection_config_run_service.py`
  - 配置运行实例服务的单元测试
- `backend/tests/test_collection_queue_runner.py`
  - 队列 runner 的单元测试
- `alembic/versions/<timestamp>_collection_config_runs.py`
  - 新表与任务关联字段迁移

### Modified Files

- `modules/core/db/schema.py`
  - 新增 `CollectionConfigRun`
  - `CollectionTask` 增加 `config_run_id`
- `backend/services/collection_scheduler.py`
  - 定时触发改为“入队 run”
- `backend/services/collection_config_execution.py`
  - 从“展开任务并直接后台启动”改为“只展开任务记录”
- `backend/domains/collection/routers/collection_tasks.py`
  - 手动运行配置改为创建 queued run
  - 快速采集增加闸门
- `backend/main.py`
  - 应用启动时初始化 queue runner
  - 应用退出时关闭 queue runner
- `backend/routers/collection_schedule.py`
  - 健康检查增加配置 run 维度状态
- `backend/schemas/collection.py`
  - 增加配置 run 响应模型和手动运行配置响应模型
- `backend/tests/test_collection_execution_startup_paths.py`
  - 启动路径改为验证“入队 run”
- `backend/tests/test_collection_config_schedule_sync_api.py`
  - 定时配置验证调整为队列语义
- `backend/tests/test_task_center_collection_projection.py`
  - 如受影响则更新任务映射契约

### Existing Tests To Re-run

- `backend/tests/test_collection_config_execution_service.py`
- `backend/tests/test_collection_execution_startup_paths.py`
- `backend/tests/test_collection_config_schedule_sync_api.py`
- `backend/tests/test_collection_task_live_updates.py`
- `backend/tests/test_collection_account_capability_alignment.py`

## Task 1: Add Schema And Migration For Config Runs

**Files:**
- Modify: `modules/core/db/schema.py`
- Create: `alembic/versions/<timestamp>_collection_config_runs.py`
- Test: `backend/tests/test_collection_schema_contract.py`

- [ ] **Step 1: Write the failing schema contract test**

Add assertions that:
- `CollectionConfigRun` exists in `modules/core/db/schema.py`
- `collection_config_runs` table is mapped under `core`
- `CollectionTask` exposes `config_run_id`

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_collection_schema_contract.py -q`
Expected: FAIL because `CollectionConfigRun` and `config_run_id` do not exist yet.

- [ ] **Step 3: Add minimal schema implementation**

Implement in `modules/core/db/schema.py`:
- `CollectionConfigRun` model
- relationship from run to tasks
- `CollectionTask.config_run_id`
- indexes for `status`, `created_at`, `config_id`, `main_account_id`

- [ ] **Step 4: Add Alembic migration**

Implement migration to:
- create `core.collection_config_runs`
- add nullable `config_run_id` to `core.collection_tasks`
- add foreign key and indexes

- [ ] **Step 5: Run schema contract test**

Run: `python -m pytest backend/tests/test_collection_schema_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/core/db/schema.py alembic/versions/<timestamp>_collection_config_runs.py backend/tests/test_collection_schema_contract.py
git commit -m "feat: add collection config run schema"
```

## Task 2: Implement Config Run Service

**Files:**
- Create: `backend/services/collection_config_run_service.py`
- Test: `backend/tests/test_collection_config_run_service.py`

- [ ] **Step 1: Write failing service tests**

Cover:
- create queued run for config
- reject duplicate enqueue when same config already has `queued/running`
- claim oldest queued run and mark `running`
- complete run as `completed`
- complete run as `partial_success` when tasks partially fail

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_collection_config_run_service.py -q`
Expected: FAIL because the service file does not exist.

- [ ] **Step 3: Implement minimal service**

Implement methods such as:
- `enqueue_config_run(...)`
- `get_running_run(...)`
- `claim_next_queued_run(...)`
- `mark_run_completed(...)`
- `mark_run_failed(...)`
- `summarize_run_status(...)`

Keep the service async-first and use optimistic claim semantics where needed.

- [ ] **Step 4: Run service tests**

Run: `python -m pytest backend/tests/test_collection_config_run_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_config_run_service.py backend/tests/test_collection_config_run_service.py
git commit -m "feat: add collection config run service"
```

## Task 3: Refactor Config Expansion To Stop Auto-Launching Tasks

**Files:**
- Modify: `backend/services/collection_config_execution.py`
- Modify: `backend/tests/test_collection_config_execution_service.py`

- [ ] **Step 1: Write failing tests for no-autostart behavior**

Adjust tests so `create_tasks_for_config(...)` verifies:
- tasks are created and committed
- tasks are associated with `config_run_id`
- tasks are not launched with `asyncio.create_task(...)` by default

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_config_execution_service.py -q`
Expected: FAIL because current implementation still auto-starts background tasks and lacks `config_run_id`.

- [ ] **Step 3: Implement minimal refactor**

Update `create_tasks_for_config(...)` to:
- accept `config_run_id`
- create `CollectionTask` rows tied to that run
- return the created tasks only
- remove direct background launch responsibility from the default path

Do not remove runtime preflight and capability filtering.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_config_execution_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_config_execution.py backend/tests/test_collection_config_execution_service.py
git commit -m "refactor: decouple config expansion from task launch"
```

## Task 4: Convert Scheduler To Queue Submission

**Files:**
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/tests/test_collection_execution_startup_paths.py`
- Modify: `backend/tests/test_collection_config_schedule_sync_api.py`

- [ ] **Step 1: Write failing tests for scheduler enqueue semantics**

Update tests so scheduled execution expects:
- `execute_scheduled_collection_config(...)` creates or requests a queued run
- scheduler no longer calls `create_tasks_for_config(..., start_background=True)` directly

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_execution_startup_paths.py backend/tests/test_collection_config_schedule_sync_api.py -q`
Expected: FAIL because the scheduler still directly expands and starts tasks.

- [ ] **Step 3: Implement minimal scheduler refactor**

Change `backend/services/collection_scheduler.py` so:
- APScheduler callback only enqueues `CollectionConfigRun`
- it performs duplicate queued/running protection
- logs shift from “created tasks” to “queued config run”

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_execution_startup_paths.py backend/tests/test_collection_config_schedule_sync_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_scheduler.py backend/tests/test_collection_execution_startup_paths.py backend/tests/test_collection_config_schedule_sync_api.py
git commit -m "refactor: queue scheduled collection config runs"
```

## Task 5: Convert Manual Config Run Endpoint To Queue Submission

**Files:**
- Modify: `backend/domains/collection/routers/collection_tasks.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_execution_startup_paths.py`

- [ ] **Step 1: Write failing API tests**

Cover:
- `POST /configs/{config_id}/run` enqueues a config run
- response returns queue-oriented payload rather than immediate task-start semantics
- duplicate active run for same config is rejected or returned idempotently

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_execution_startup_paths.py -q`
Expected: FAIL because the endpoint still directly expands and starts tasks.

- [ ] **Step 3: Implement endpoint refactor**

Update:
- route handler to enqueue `CollectionConfigRun`
- response model to surface `run_id`, `status`, `queued_at`

Keep existing auth and config validation behavior.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_execution_startup_paths.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/collection/routers/collection_tasks.py backend/schemas/collection.py backend/tests/test_collection_execution_startup_paths.py
git commit -m "feat: enqueue manual collection config runs"
```

## Task 6: Implement Single-Worker Queue Runner

**Files:**
- Create: `backend/services/collection_queue_runner.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_collection_queue_runner.py`

- [ ] **Step 1: Write failing queue runner tests**

Cover:
- runner claims one queued run when none is running
- runner does not claim a second run while one is running
- completed run triggers next queued run
- shutdown stops the polling loop cleanly

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_queue_runner.py -q`
Expected: FAIL because the runner does not exist yet.

- [ ] **Step 3: Implement runner**

Implement:
- `start()`
- `shutdown()`
- internal loop
- `process_once()`

Runner responsibilities:
- claim one queued run
- expand tasks for that run
- execute tasks sequentially
- finalize run state

Initialize it from `backend/main.py` and store on `app.state`.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_queue_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_queue_runner.py backend/main.py backend/tests/test_collection_queue_runner.py
git commit -m "feat: add collection queue runner"
```

## Task 7: Add Sequential Task Execution Under A Config Run

**Files:**
- Modify: `backend/services/collection_queue_runner.py`
- Modify: `backend/domains/collection/routers/collection_tasks.py`
- Test: `backend/tests/test_collection_task_live_updates.py`

- [ ] **Step 1: Write failing sequential execution test**

Cover:
- one config run with multiple shop scopes executes tasks one-by-one
- second task does not start before first task reaches terminal state

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_task_live_updates.py -q`
Expected: FAIL because current system does not enforce config-run-level sequential shop execution.

- [ ] **Step 3: Implement sequential task execution**

Extract or reuse a callable that runs a single `CollectionTask` and waits for terminal completion.

Avoid:
- `asyncio.create_task(...)` fan-out for all shop tasks

Ensure:
- verification pause keeps the run blocked on the current task
- task final state updates still mirror to task center and websocket notifications

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_task_live_updates.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_queue_runner.py backend/domains/collection/routers/collection_tasks.py backend/tests/test_collection_task_live_updates.py
git commit -m "feat: execute config run tasks sequentially"
```

## Task 8: Add Quick Collection Gate While Config Runs Are Active

**Files:**
- Modify: `backend/domains/collection/routers/collection_tasks.py`
- Test: `backend/tests/test_collection_account_capability_alignment.py`
- Test: `backend/tests/test_task_center_collection_projection.py`

- [ ] **Step 1: Write failing gate tests**

Cover:
- manual quick task creation is rejected when a config run is `running`
- quick task creation still works when no config run is active

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_account_capability_alignment.py backend/tests/test_task_center_collection_projection.py -q`
Expected: FAIL because no running-config gate exists today.

- [ ] **Step 3: Implement minimal gate**

In the quick task creation path:
- check for any `CollectionConfigRun(status='running')`
- if found, return a clear `409` or `400` style conflict response with queue-busy message

Do not change the runtime manifest resolution logic.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_account_capability_alignment.py backend/tests/test_task_center_collection_projection.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/collection/routers/collection_tasks.py backend/tests/test_collection_account_capability_alignment.py backend/tests/test_task_center_collection_projection.py
git commit -m "feat: gate quick collection during config runs"
```

## Task 9: Extend Health And Observability To Config Runs

**Files:**
- Modify: `backend/routers/collection_schedule.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_config_schedule_sync_api.py`

- [ ] **Step 1: Write failing health/response tests**

Cover:
- health response exposes queued run count
- health response exposes running config run summary
- config run status payload fields serialize correctly

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_config_schedule_sync_api.py -q`
Expected: FAIL because the current health model only reflects task counts.

- [ ] **Step 3: Implement observability changes**

Expose:
- queued config runs
- current running config run
- `main_account_id`, `config_id`, `trigger_type`, `status`, `started_at`

Keep existing task-level health fields where still useful.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_config_schedule_sync_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/collection_schedule.py backend/schemas/collection.py backend/tests/test_collection_config_schedule_sync_api.py
git commit -m "feat: expose collection config run health"
```

## Task 10: End-To-End Verification

**Files:**
- Modify as needed based on failures discovered in verification

- [ ] **Step 1: Run targeted collection queue test suite**

Run:
```bash
python -m pytest ^
  backend/tests/test_collection_schema_contract.py ^
  backend/tests/test_collection_config_run_service.py ^
  backend/tests/test_collection_queue_runner.py ^
  backend/tests/test_collection_config_execution_service.py ^
  backend/tests/test_collection_execution_startup_paths.py ^
  backend/tests/test_collection_config_schedule_sync_api.py ^
  backend/tests/test_collection_task_live_updates.py ^
  backend/tests/test_collection_account_capability_alignment.py ^
  backend/tests/test_task_center_collection_projection.py -q
```

Expected: PASS

- [ ] **Step 2: Run migration sanity checks**

Run:
```bash
alembic upgrade head
python -m pytest backend/tests/test_collection_execution_mode_migration_contract.py -q
```

Expected: PASS

- [ ] **Step 3: Run rule checks relevant to backend changes**

Run:
```bash
python scripts/verify_architecture_ssot.py
python scripts/verify_root_md_whitelist.py
python scripts/verify_no_emoji.py
```

Expected: PASS

- [ ] **Step 4: Review git diff for accidental unrelated changes**

Run:
```bash
git status --short
git diff --stat
```

Expected: only queue-runner related files are modified.

- [ ] **Step 5: Final commit**

```bash
git add <verified files>
git commit -m "feat: add serialized collection config queue runner"
```

## Risks And Checks

- `CollectionTask` currently has existing status semantics used by frontend and task center. Keep config-level queue state in `CollectionConfigRun` to avoid destabilizing existing task status consumers.
- Verification pause semantics are intentionally blocking at config-run level in phase 1. Do not silently continue to the next config while one run is paused for captcha.
- Avoid reintroducing fan-out via `asyncio.create_task(...)` in config execution. The queue runner should own task launch order.
- Preserve current runtime preflight and capability filtering; queue refactor must not weaken component readiness checks.
- Keep migrations additive and backward-compatible where possible.

## Notes For Executor

- Follow TDD strictly for each task.
- Keep commits small and scoped to the task being completed.
- Do not widen scope into “global two-run parallelism” or “quick collection priority queue” in this implementation.

