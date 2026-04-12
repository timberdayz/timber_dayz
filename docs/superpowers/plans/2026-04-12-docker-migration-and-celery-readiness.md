# Docker Migration And Celery Readiness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将数据库迁移从 backend/celery runtime 启动链路中拆出为独立一次性 job，并把 Celery worker 健康检查改为真实 readiness 检查。

**Architecture:** 通过 `RUN_MIGRATIONS` 控制入口脚本是否执行 Alembic；在 dev/prod compose 中新增 `migrate` 服务专门执行迁移；runtime 服务统一关闭自动迁移。Celery worker 健康检查改为容器内 `celery inspect ping`，验证 worker 已经向 broker 完成注册。

**Tech Stack:** Docker Compose, Bash entrypoint, Celery, Pytest, YAML config assertions

---

### Task 1: 锁定配置目标行为

**Files:**
- Modify: `backend/tests/test_runtime_config_alignment.py`

- [ ] **Step 1: Write the failing test**

为以下行为增加断言：
- dev/prod 存在 `migrate` 服务
- `migrate` 服务启用 `RUN_MIGRATIONS=1`
- `backend` / `celery-worker` / `celery-beat` 禁用自动迁移
- `celery-worker` 健康检查基于 Celery readiness，而不是 Redis ping

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: FAIL because compose files still use runtime migration and Redis-only healthcheck

- [ ] **Step 3: Write minimal implementation**

更新测试使其准确表达预期配置。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: PASS after compose and entrypoint changes land

### Task 2: 解耦 runtime 与迁移

**Files:**
- Modify: `docker/scripts/backend-entrypoint.sh`

- [ ] **Step 1: Write the failing test**

由 Task 1 的配置测试间接约束 runtime 不再默认迁移。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: FAIL before script/config changes

- [ ] **Step 3: Write minimal implementation**

为 entrypoint 增加 `RUN_MIGRATIONS` 开关：
- 为 `1/true/yes` 时执行 `alembic upgrade heads`
- 其他情况直接 `exec "$@"`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: runtime services no longer require migrations by default

### Task 3: 更新 dev/prod compose

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: Write the failing test**

由 Task 1 的配置测试覆盖。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: FAIL before compose changes

- [ ] **Step 3: Write minimal implementation**

在 dev/prod compose 中：
- 新增 `migrate` 服务
- runtime 服务显式设置 `RUN_MIGRATIONS=0`
- `migrate` 服务设置 `RUN_MIGRATIONS=1`
- `celery-worker` 健康检查改为 `celery inspect ping`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: PASS

### Task 4: 回归验证

**Files:**
- Modify: none

- [ ] **Step 1: Run targeted verification**

Run: `pytest backend/tests/test_runtime_config_alignment.py -q`
Expected: PASS

- [ ] **Step 2: Summarize operational follow-up**

记录新的启动方式：先运行 `migrate`，再启动 runtime 服务。
