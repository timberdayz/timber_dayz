# Main Account Session Coordination Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent same-main-account concurrent collection failures by serializing shared authentication and shop-context preparation while preserving safe downstream task concurrency.

**Architecture:** Introduce a platform-agnostic main-account session coordinator keyed by `platform + main_account_id`, then split collection runtime into a shared-state phase and a task-private phase. Remove shop-bound login entry assumptions, move target-shop readiness behind login, and expose clearer waiting/preparing step text to the task UI.

**Tech Stack:** FastAPI, SQLAlchemy async, Playwright async runtime, existing collection executor V2, Vue 3 collection task UI

---

## File Structure

### New files to create

- `backend/services/main_account_session_coordinator.py`
  Responsibility: provide per-main-account async locking and shared-state coordination helpers for collection runtime.
- `backend/tests/test_main_account_session_coordinator.py`
  Responsibility: verify same-main-account serialization and different-main-account concurrency.

### Existing files to modify

- `modules/apps/collection_center/executor_v2.py`
  Responsibility: split runtime into shared-state and task-private phases; integrate coordinator; remove unsafe same-main-account concurrent login/shop-switch behavior.
- `backend/routers/collection_tasks.py`
  Responsibility: expose waiting/preparing/current-step transitions for main-account coordination.
- `modules/platforms/shopee/components/login.py`
  Responsibility: narrow login responsibility to authenticated platform-shell readiness and stop conflating shop readiness with login success.
- `modules/utils/login_status_detector.py`
  Responsibility: relax authenticated-shell detection so already-authenticated shells do not fail just because a shop-specific URL is not yet present.
- `backend/tests/test_collection_verification_flow.py`
  Responsibility: ensure verification flows still work with the new shared-state sequencing.
- `backend/tests/test_collection_task_status_contract.py`
  Responsibility: verify new waiting/preparing step messages remain visible to the task UI.
- `backend/tests/test_collection_executor_reused_session_scope.py`
  Responsibility: extend reuse tests to cover same-main-account concurrent execution boundaries.
- `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: lock task UI contract expectations for the new waiting/preparing step labels.
- `frontend/src/views/collection/CollectionTasks.vue`
  Responsibility: consume and render the new waiting/preparing task-step text cleanly if any explicit status-label mapping is needed.

### Existing files to inspect during implementation

- `modules/platforms/tiktok/components/login.py`
- `modules/platforms/miaoshou/components/login.py`

These may not need code changes in the first pass, but must be reviewed so the coordinator design remains platform-agnostic rather than Shopee-only.

---

## Task 1: Add Main-Account Coordinator Contract

**Files:**
- Create: `backend/services/main_account_session_coordinator.py`
- Test: `backend/tests/test_main_account_session_coordinator.py`

- [ ] **Step 1: Write the failing coordinator tests**

Cover:

- same `platform + main_account_id` calls serialize
- different main-account keys may proceed concurrently
- waiting tasks can observe when they are queued

- [ ] **Step 2: Run the focused coordinator tests and verify failure**

Run:

```bash
pytest backend/tests/test_main_account_session_coordinator.py -q
```

Expected: FAIL because the coordinator file does not exist yet.

- [ ] **Step 3: Implement the minimal coordinator**

Add:

- in-memory async lock registry keyed by `platform + main_account_id`
- async context manager or equivalent acquire/release helper
- optional queue-depth / waiting introspection if useful for task-step reporting

Do not add Redis/distributed locking in this phase.

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_main_account_session_coordinator.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/main_account_session_coordinator.py backend/tests/test_main_account_session_coordinator.py
git commit -m "feat: add main account session coordinator"
```

## Task 2: Split Executor Runtime Into Shared-State And Task-Private Phases

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_executor_reused_session_scope.py`

- [ ] **Step 1: Write the failing runtime tests**

Cover:

- same-main-account concurrent tasks do not run login preparation at the same time
- target-shop readiness completes before domain collection begins
- different main accounts still run without unnecessary serialization

- [ ] **Step 2: Run the focused runtime tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_executor_reused_session_scope.py -q
```

Expected: FAIL until the executor is coordinator-aware.

- [ ] **Step 3: Implement the runtime phase split**

Refactor `executor_v2.py` so each task becomes:

1. acquire coordinator for `platform + main_account_id`
2. validate / refresh main-account session
3. switch to target shop
4. confirm target-shop readiness
5. release coordinator
6. run domain collection in task-private context

Keep the existing data-domain export flow unchanged outside the shared-state phase.

- [ ] **Step 4: Re-run the focused runtime tests**

Run:

```bash
pytest backend/tests/test_collection_executor_reused_session_scope.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py
git commit -m "feat: serialize shared state for same main account collection"
```

## Task 3: Make Login Entry Shop-Neutral And Re-Scope Login Responsibility

**Files:**
- Modify: `modules/platforms/shopee/components/login.py`
- Modify: `modules/utils/login_status_detector.py`
- Test: `backend/tests/test_collection_verification_flow.py`

- [ ] **Step 1: Write or extend failing tests for authenticated-shell detection**

Cover:

- already-authenticated seller shell counts as login success even before final target shop is confirmed
- login component no longer requires a shop-specific URL to declare authentication success
- verification-required paths still pause correctly

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_verification_flow.py -q
```

Expected: FAIL until login success detection is relaxed and responsibility is narrowed.

- [ ] **Step 3: Implement the minimal login/gate adjustment**

Update:

- Shopee login component so it proves authenticated platform shell readiness only
- login status detector so authenticated shell pages are not falsely treated as not logged in

Do not yet rewrite every platform login component in this task; keep the first pass minimal and architecture-driven.

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_verification_flow.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/platforms/shopee/components/login.py modules/utils/login_status_detector.py backend/tests/test_collection_verification_flow.py
git commit -m "fix: decouple login success from shop-specific readiness"
```

## Task 4: Expose Main-Account Coordination States To Tasks

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_task_status_contract.py`
- Test: `backend/tests/test_collection_frontend_contracts.py`

- [ ] **Step 1: Write the failing status-contract tests**

Cover:

- task steps can show:
  - `waiting_for_main_account_session`
  - `preparing_main_account_session`
  - `switching_target_shop`
  - `target_shop_ready`
- task UI payload still serializes cleanly for polling and websocket consumers

- [ ] **Step 2: Run the focused contract tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_task_status_contract.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: FAIL until the new status/step text is emitted.

- [ ] **Step 3: Implement the minimal task-status updates**

Add:

- clear current-step messages during coordinator wait/acquire/release lifecycle
- persistence of those messages through existing task polling responses

Avoid introducing a brand-new persisted status enum unless necessary; prefer current-step messaging first.

- [ ] **Step 4: Re-run the focused contract tests**

Run:

```bash
pytest backend/tests/test_collection_task_status_contract.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/collection_tasks.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_task_status_contract.py backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: expose main account coordination task steps"
```

## Task 5: Minimal Task UI Wiring

**Files:**
- Modify: `frontend/src/views/collection/CollectionTasks.vue`
- Test: `backend/tests/test_collection_frontend_contracts.py`

- [ ] **Step 1: Add failing assertions if needed**

Cover:

- task page recognizes and renders the new waiting/preparing/switching messages cleanly
- existing verification/manual-intervention behavior is unaffected

- [ ] **Step 2: Run the focused frontend contract check and verify failure**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
```

Expected: FAIL only if explicit label handling is missing.

- [ ] **Step 3: Implement the minimal UI changes**

Only change what is needed to keep task progression understandable. Do not redesign the task page.

- [ ] **Step 4: Re-run the focused contract check**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionTasks.vue backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: surface main account coordination states in task ui"
```

## Task 6: Full Verification And Concurrent Manual Walkthrough

**Files:**
- Verify: `backend/services/main_account_session_coordinator.py`
- Verify: `modules/apps/collection_center/executor_v2.py`
- Verify: `backend/routers/collection_tasks.py`
- Verify: `modules/platforms/shopee/components/login.py`
- Verify: `modules/utils/login_status_detector.py`
- Verify: `frontend/src/views/collection/CollectionTasks.vue`

- [ ] **Step 1: Run backend verification**

Run:

```bash
pytest backend/tests/test_main_account_session_coordinator.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_verification_flow.py backend/tests/test_collection_task_status_contract.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend static verification**

Run:

```bash
npm run build
npm run type-check
```

Expected: PASS

- [ ] **Step 3: Run compile verification for backend runtime files**

Run:

```bash
python -m py_compile backend/services/main_account_session_coordinator.py backend/routers/collection_tasks.py modules/apps/collection_center/executor_v2.py modules/platforms/shopee/components/login.py modules/utils/login_status_detector.py
```

Expected: PASS

- [ ] **Step 4: Manual concurrent walkthrough**

Verify manually:

- launch two Shopee tasks under the same main account
- confirm the second task waits during shared-state preparation
- confirm both tasks eventually pass login/shop readiness without racing
- confirm downstream collection can still proceed concurrently
- confirm tasks under different main accounts can still start without unnecessary waiting

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: coordinate same-main-account collection session preparation"
```

## Implementation Notes

- Keep the first coordinator in-process and memory-backed. Do not add Redis locking in this phase unless the runtime topology proves it is strictly required.
- Favor current-step reporting over persisted-status explosion.
- The initial first-pass platform behavior should be validated on Shopee because that is where the concrete evidence exists, but the coordinator API must remain platform-agnostic.
- Shop-neutral login-entry cleanup should not mutate unrelated account-management UI in this phase; keep it runtime-focused unless a supporting admin fix is unavoidable.
