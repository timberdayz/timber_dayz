# Collection Config Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the collection configuration frontend and backend with the current stable runtime contract so manual runs and scheduled runs create the same valid tasks without changing the working collection component logic.

**Architecture:** This plan is config-layer only. It keeps the existing task executor, scheduler, and collection components as-is, and instead rebuilds the config contract around `platform`, account scope, `data_domains`, `sub_domains`, `time_selection`, and `granularity`. Legacy fields remain readable for compatibility, but new create/edit flows should be driven by the new contract.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Vue 3, Element Plus, existing collection scheduler/runtime

---

## Scope

This plan covers:

- collection config create/edit contract cleanup
- manual run vs scheduled run semantic alignment
- platform/domain/subtype/time-selection UI constraints
- focused regression tests for config-driven task creation

This plan does **not** cover:

- changing working collection component logic
- changing executor runtime topology
- changing stable component registration rules

---

### Task 1: Lock The Config Contract

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/routers/collection_config.py`
- Test: `backend/tests/test_collection_time_selection_contract.py`

- [ ] **Step 1: Add failing coverage for the intended config contract**

Cover:
- `time_selection` is the primary input shape
- `custom` requires explicit `granularity`
- legacy `date_range_type/custom_date_*` remains compatibility input only
- `sub_domains` is normalized as a domain-scoped mapping

- [ ] **Step 2: Run focused contract tests and confirm failure**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py -q
```

Expected: FAIL until the config entrypoints consistently enforce the new contract.

- [ ] **Step 3: Implement the backend contract alignment**

Ensure:
- create/update config paths normalize through `collection_contracts`
- returned config payloads expose the normalized contract clearly
- compatibility fields are still stored/read where needed

- [ ] **Step 4: Re-run the focused contract tests**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/services/collection_contracts.py backend/routers/collection_config.py backend/tests/test_collection_time_selection_contract.py
git commit -m "refactor: align collection config contract with runtime time selection"
```

### Task 2: Align Manual Run Semantics With Scheduled Semantics

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/routers/collection_tasks.py`
- Test: `backend/tests/test_collection_scheduler_capability_filter.py`

- [ ] **Step 1: Add failing coverage for account-scope and task-scope alignment**

Cover:
- `account_ids=[]` means all active accounts for the platform
- manual run and scheduled run resolve the same effective account set
- disabled or unsupported accounts are skipped consistently

- [ ] **Step 2: Run the focused scheduler/account tests**

Run:

```bash
pytest backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: FAIL or require extension until the same semantics are enforced across both paths.

- [ ] **Step 3: Fix the account-resolution mismatch**

Ensure:
- frontend manual run filters to active platform accounts
- backend scheduled run keeps the same active-account semantics
- task creation still filters by account capability before execution

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
pytest backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue backend/services/collection_scheduler.py backend/routers/collection_tasks.py backend/tests/test_collection_scheduler_capability_filter.py
git commit -m "fix: align manual and scheduled collection account scope"
```

### Task 3: Constrain The Config UI To Real Platform Capabilities

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/constants/collection.js`
- Test: `frontend/scripts/collectionApiContract.test.mjs`

- [ ] **Step 1: Add failing UI/contract coverage**

Cover:
- platform-specific data-domain choices
- domain-scoped subtype selection
- custom time mode requires explicit granularity choice in UI
- quick setup does not create configs for unsupported platform/domain combinations

- [ ] **Step 2: Run the focused frontend contract test**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
```

Expected: FAIL until the UI is restricted to the runtime-supported model.

- [ ] **Step 3: Update the config UI**

Ensure:
- `miaoshou` only exposes currently intended domains
- subtype controls only appear for valid domain/platform combinations
- custom date mode shows granularity explicitly
- quick setup uses the same rules as the create/edit form

- [ ] **Step 4: Re-run the focused frontend contract test**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/constants/collection.js frontend/scripts/collectionApiContract.test.mjs
git commit -m "refactor: constrain collection config UI to runtime-supported options"
```

### Task 4: Verify Config-To-Task Mapping End To End

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/routers/collection_config.py`
- Test: `backend/tests/test_component_runtime_resolver.py`
- Test: `backend/tests/test_component_test_runtime_config.py`

- [ ] **Step 1: Add failing regression coverage for config-driven task creation**

Cover:
- config-derived `data_domains/sub_domains/time_selection/granularity` resolve to valid runtime manifests
- invalid config combinations are rejected before task execution
- manual create-task and scheduled create-task derive the same normalized shape

- [ ] **Step 2: Run focused runtime-config regressions**

Run:

```bash
pytest backend/tests/test_component_runtime_resolver.py backend/tests/test_component_test_runtime_config.py -q
```

Expected: FAIL until config-to-task normalization is fully aligned.

- [ ] **Step 3: Tighten the config-to-task normalization**

Ensure:
- both manual and scheduled flows derive the same normalized `time_selection`
- both flows pass the same `sub_domains` mapping shape into runtime resolution
- preflight errors remain explicit

- [ ] **Step 4: Re-run focused regressions**

Run:

```bash
pytest backend/tests/test_component_runtime_resolver.py backend/tests/test_component_test_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/collection_tasks.py backend/routers/collection_config.py backend/tests/test_component_runtime_resolver.py backend/tests/test_component_test_runtime_config.py
git commit -m "refactor: align collection config to task runtime mapping"
```

### Task 5: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run focused backend regressions**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_scheduler_capability_filter.py backend/tests/test_component_runtime_resolver.py backend/tests/test_component_test_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 2: Run focused frontend verification**

Run:

```bash
node frontend/scripts/collectionApiContract.test.mjs
```

Expected: PASS

- [ ] **Step 3: Syntax-check touched backend files**

Run:

```bash
python -m py_compile backend/schemas/collection.py backend/services/collection_contracts.py backend/routers/collection_config.py backend/routers/collection_tasks.py backend/services/collection_scheduler.py
```

Expected: no output

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify collection config alignment"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-31-collection-config-alignment.md`. Ready to execute?
