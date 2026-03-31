# Collection Module Boundaries Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Realign the collection module so `采集配置` is the template/scheduling surface, `采集任务` is the single runtime/verification/intervention surface, and `采集历史` is the terminal audit surface, while supporting multi-account concurrent verification and headed/manual intervention flows.

**Architecture:** This implementation keeps the current executor and collection component runtime, and instead restructures the product flow and contracts around one shared task state machine. Configuration creates tasks and defines default execution mode; task pages own verification recovery and manual intervention; history consumes only terminal tasks.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Vue 3, Element Plus, existing collection task runtime and verification flow

---

## File Map

### Backend

- Modify: `backend/schemas/collection.py`
  - Extend config/task schemas for execution mode and task-facing recovery metadata if needed.
- Modify: `backend/routers/collection_config.py`
  - Keep config endpoints focused on template/schedule concerns and task creation handoff.
- Modify: `backend/routers/collection_tasks.py`
  - Make task endpoints the single recovery/intervention entrypoint.
- Modify: `backend/services/collection_scheduler.py`
  - Ensure scheduled tasks inherit config execution mode.

### Frontend

- Modify: `frontend/src/views/collection/CollectionConfig.vue`
  - Reduce runtime concerns; add execution mode; redirect to task view after task creation.
- Modify: `frontend/src/views/collection/CollectionTasks.vue`
  - Add waiting-action queue, grouped task views, verification/manual intervention actions.
- Modify: `frontend/src/views/collection/CollectionHistory.vue`
  - Restrict to terminal-state querying and remove runtime affordances.
- Modify: `frontend/src/api/collection.js`
  - Add or align task recovery/headed-mode APIs.
- Modify: `frontend/src/constants/collection.js`
  - Centralize execution mode, task queue filters, and config-to-task defaults.
- Modify: `frontend/src/components/verification/VerificationResumeDialog.vue`
  - Reuse as the single verification recovery surface.

### Tests

- Create: `backend/tests/test_collection_config_task_handoff_api.py`
- Create: `backend/tests/test_collection_task_intervention_contract.py`
- Modify: `backend/tests/test_collection_config_api.py`
- Modify: `frontend/scripts/collectionApiContract.test.mjs`
- Create: `frontend/scripts/collectionTaskInterventionUi.test.mjs`
- Modify: `frontend/scripts/collectionTasksVerificationUi.test.mjs`

---

### Task 1: Lock Module Boundaries In Tests

**Files:**
- Create: `backend/tests/test_collection_config_task_handoff_api.py`
- Create: `backend/tests/test_collection_task_intervention_contract.py`
- Create: `frontend/scripts/collectionTaskInterventionUi.test.mjs`

- [ ] **Step 1: Write failing backend tests for config/task boundary**

Cover:
- config execution creates tasks but does not expose runtime-only recovery fields directly
- task endpoints remain the only recovery/intervention API surface
- scheduled tasks inherit config execution mode

- [ ] **Step 2: Run focused backend tests and confirm failure**

Run:

```bash
pytest backend/tests/test_collection_config_task_handoff_api.py backend/tests/test_collection_task_intervention_contract.py -q
```

Expected: FAIL until the boundary rules are implemented.

- [ ] **Step 3: Write failing frontend boundary test**

Cover:
- config page does not embed runtime recovery UI
- task page owns verification/manual intervention UI
- history page does not expose runtime controls

- [ ] **Step 4: Run focused frontend boundary test and confirm failure**

Run:

```bash
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: FAIL until the UI boundaries are implemented.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_collection_config_task_handoff_api.py backend/tests/test_collection_task_intervention_contract.py frontend/scripts/collectionTaskInterventionUi.test.mjs
git commit -m "test: define collection module boundary contract"
```

### Task 2: Add Execution Mode To Config And Task Creation

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `frontend/src/constants/collection.js`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `backend/tests/test_collection_config_api.py`

- [ ] **Step 1: Write failing tests for execution mode propagation**

Cover:
- config create/update accepts `execution_mode`
- manual config execution passes the mode to created tasks
- scheduled task creation inherits the same mode

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_config_task_handoff_api.py -q
```

Expected: FAIL until execution mode is persisted and propagated.

- [ ] **Step 3: Implement minimal backend support**

Ensure:
- config schema persists `execution_mode`
- task creation includes `execution_mode` or mapped runtime field
- scheduler uses the same default

- [ ] **Step 4: Implement minimal frontend support**

Ensure:
- config form shows headed/headless selector
- quick setup and manual run use the same default

- [ ] **Step 5: Re-run focused tests**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_config_task_handoff_api.py -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/routers/collection_tasks.py backend/services/collection_scheduler.py frontend/src/constants/collection.js frontend/src/views/collection/CollectionConfig.vue backend/tests/test_collection_config_api.py backend/tests/test_collection_config_task_handoff_api.py
git commit -m "feat: add config-driven execution mode for collection tasks"
```

### Task 3: Make Config Execution Redirect Into Task Management

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/views/collection/CollectionTasks.vue`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/scripts/collectionApiContract.test.mjs`

- [ ] **Step 1: Write failing UI tests for config-to-task handoff**

Cover:
- config execution redirects to task page with task/config filters
- config page no longer tries to handle verification directly

- [ ] **Step 2: Run focused frontend tests and confirm failure**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
```

Expected: FAIL until the handoff flow is implemented.

- [ ] **Step 3: Implement config-to-task redirect**

Ensure:
- task creation returns enough identity for redirect
- config page navigates to task page after successful creation
- task page accepts incoming filters

- [ ] **Step 4: Re-run focused frontend tests**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/views/collection/CollectionTasks.vue frontend/src/api/collection.js frontend/scripts/collectionApiContract.test.mjs
git commit -m "refactor: hand off config execution to task management flow"
```

### Task 4: Build A Unified Waiting-Action Queue In Task Management

**Files:**
- Modify: `frontend/src/views/collection/CollectionTasks.vue`
- Modify: `frontend/src/components/verification/VerificationResumeDialog.vue`
- Modify: `frontend/src/api/collection.js`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/tests/test_collection_task_intervention_contract.py`
- Modify: `frontend/scripts/collectionTasksVerificationUi.test.mjs`
- Create: `frontend/scripts/collectionTaskInterventionUi.test.mjs`

- [ ] **Step 1: Write failing tests for waiting-action queue behavior**

Cover:
- multiple accounts in `verification_required` or `manual_intervention_required` appear in one queue
- queue items include platform/account/config/block type/blocked time
- verification dialog is reused, not duplicated

- [ ] **Step 2: Run task intervention tests and confirm failure**

Run:

```bash
pytest backend/tests/test_collection_task_intervention_contract.py -q
node frontend/scripts/collectionTasksVerificationUi.test.mjs
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: FAIL until queue behavior is implemented.

- [ ] **Step 3: Implement backend task payload support**

Ensure:
- task list and verification-items endpoints expose enough metadata for queue rendering
- manual intervention status is represented alongside verification-required tasks

- [ ] **Step 4: Implement task page waiting-action queue**

Ensure:
- dedicated queue section for blocked tasks
- grouped actions for captcha / OTP / manual intervention
- queue ordering is deterministic

- [ ] **Step 5: Re-run focused intervention tests**

Run:

```bash
pytest backend/tests/test_collection_task_intervention_contract.py -q
node frontend/scripts/collectionTasksVerificationUi.test.mjs
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/collection_tasks.py backend/tests/test_collection_task_intervention_contract.py frontend/src/views/collection/CollectionTasks.vue frontend/src/components/verification/VerificationResumeDialog.vue frontend/src/api/collection.js frontend/scripts/collectionTasksVerificationUi.test.mjs frontend/scripts/collectionTaskInterventionUi.test.mjs
git commit -m "feat: add unified task intervention queue for collection module"
```

### Task 5: Restrict History To Terminal States

**Files:**
- Modify: `frontend/src/views/collection/CollectionHistory.vue`
- Modify: `frontend/scripts/collectionTaskInterventionUi.test.mjs`

- [ ] **Step 1: Write failing UI test for history terminal-only behavior**

Cover:
- history page does not show verification/manual intervention actions
- history page focuses on terminal states and audit metadata

- [ ] **Step 2: Run focused history test and confirm failure**

Run:

```bash
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: FAIL until history UI is reduced to terminal behavior.

- [ ] **Step 3: Implement minimal history cleanup**

Ensure:
- runtime controls removed
- filters/defaults focus on terminal tasks

- [ ] **Step 4: Re-run focused history test**

Run:

```bash
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionHistory.vue frontend/scripts/collectionTaskInterventionUi.test.mjs
git commit -m "refactor: limit collection history to terminal task review"
```

### Task 6: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run focused backend regressions**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_config_task_handoff_api.py backend/tests/test_collection_task_intervention_contract.py backend/tests/test_collection_scheduler_capability_filter.py backend/tests/test_component_runtime_resolver.py backend/tests/test_component_test_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 2: Run focused frontend regressions**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
node frontend/scripts/collectionTasksVerificationUi.test.mjs
node frontend/scripts/collectionTaskInterventionUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Syntax-check touched backend files**

Run:

```bash
python -m py_compile backend/schemas/collection.py backend/routers/collection_config.py backend/routers/collection_tasks.py backend/services/collection_scheduler.py
```

Expected: no output

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify collection module boundary alignment"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-31-collection-module-boundaries-implementation.md`. Ready to execute?
