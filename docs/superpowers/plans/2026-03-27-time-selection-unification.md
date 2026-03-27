# Time Selection Unification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify preset/custom time selection across component testing, formal collection config/tasks, and runtime component execution while keeping `granularity` only for output naming, ingestion classification, and scheduling.

**Architecture:** Introduce a single `time_selection` runtime model with mutually exclusive `preset` and `custom` modes. Keep `granularity` as a separate field; derive it automatically from preset values and require it explicitly for custom ranges. Add compatibility shims so existing callers using legacy date fields continue to work during migration.

**Tech Stack:** FastAPI, Pydantic, Python component runtime, pytest, Vue frontend (follow-up compatibility only where needed)

---

### Task 1: Lock the contract with failing backend tests

**Files:**
- Modify: `backend/tests/test_component_test_runtime_config.py`
- Modify: `backend/tests/test_component_tester_runtime_config.py`
- Modify: `backend/tests/test_collection_contracts.py`
- Create: `backend/tests/test_collection_time_selection_contract.py`

- [ ] **Step 1: Add failing tests for component test runtime config preset/custom modes**

- [ ] **Step 2: Add failing tests for collection contract normalization**

- [ ] **Step 3: Add failing tests for preset-to-granularity mapping**

- [ ] **Step 4: Run focused tests to verify RED**

Run:
```bash
pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py
```

Expected:
- At least one failure for missing `time_selection` behavior

### Task 2: Implement shared time-selection contract helpers

**Files:**
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/schemas/component_version.py`
- Modify: `backend/schemas/collection.py`

- [ ] **Step 1: Add shared preset enum and preset-to-granularity mapping helper**

- [ ] **Step 2: Add normalization helper that converts legacy date inputs into unified `time_selection`**

- [ ] **Step 3: Add validation helper for mutually exclusive preset/custom modes**

- [ ] **Step 4: Update Pydantic request models to carry `time_mode/date_preset/start_time/end_time`**

- [ ] **Step 5: Re-run focused tests**

Run:
```bash
pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py
```

Expected:
- Previously failing contract tests pass

### Task 3: Update runtime config construction for component tests

**Files:**
- Modify: `backend/routers/component_versions.py`
- Modify: `tools/test_component.py`
- Modify: `backend/tests/test_component_test_runtime_config.py`
- Modify: `backend/tests/test_component_tester_runtime_config.py`

- [ ] **Step 1: Refactor `_build_component_test_runtime_config()` to emit unified `time_selection`**

- [ ] **Step 2: Preserve `granularity` separately and auto-derive it for preset mode**

- [ ] **Step 3: Refactor `ComponentTester._build_runtime_component_config()` to pass through unified `time_selection`**

- [ ] **Step 4: Reject invalid combinations at the test-entry layer**

- [ ] **Step 5: Re-run focused tests**

Run:
```bash
pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py
```

Expected:
- All runtime config tests pass

### Task 4: Update formal collection config and task normalization

**Files:**
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/schemas/collection.py`
- Modify: `backend/services/collection_contracts.py`
- Create or modify tests near collection contracts / tasks if needed

- [ ] **Step 1: Normalize create/update collection config requests into unified `time_selection`**

- [ ] **Step 2: Normalize task creation requests into unified `time_selection`**

- [ ] **Step 3: Auto-derive `granularity` from preset mode and require it for custom mode**

- [ ] **Step 4: Keep legacy fields readable for compatibility**

- [ ] **Step 5: Re-run collection-related tests**

Run:
```bash
pytest backend/tests/test_collection_contracts.py
```

Expected:
- Collection time normalization tests pass

### Task 5: Update component runtime consumption

**Files:**
- Modify: `modules/platforms/miaoshou/components/orders_export.py`
- Modify: `modules/platforms/miaoshou/components/date_picker.py`
- Modify other date-picker/export components only if they already depend on old direct date fields in the same touched flow

- [ ] **Step 1: Make Miaoshou orders export read `time_selection` first**

- [ ] **Step 2: Keep legacy fallback for old runtime configs**

- [ ] **Step 3: Ensure preset mode uses only supported global presets**

- [ ] **Step 4: Ensure custom mode uses input fill path and explicit granularity**

- [ ] **Step 5: Run Miaoshou export contract tests**

Run:
```bash
pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_export_contract.py
```

Expected:
- All Miaoshou export tests pass

### Task 6: Verify no regression in component loading and registration

**Files:**
- Existing tests only

- [ ] **Step 1: Run dataclass loader regression test**

- [ ] **Step 2: Run canonical registration tests**

- [ ] **Step 3: Run combined verification**

Run:
```bash
pytest backend/tests/test_component_loader_dataclass_runtime.py backend/tests/test_component_versions_canonical_registration.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_export_contract.py
```

Expected:
- Full targeted suite passes

### Task 7: Document migration rules

**Files:**
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
- Modify: `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
- Optionally modify: `docs/guides/COMPONENT_RECORDING_GUIDE.md`

- [ ] **Step 1: Document `time_selection` as the single time interaction model**

- [ ] **Step 2: Document preset-to-granularity hard mapping**

- [ ] **Step 3: Document compatibility with old `date_from/date_to` fields as transitional only**

- [ ] **Step 4: Re-read docs for consistency**

### Task 8: Final verification

**Files:**
- No code changes

- [ ] **Step 1: Run targeted backend verification suite**

- [ ] **Step 2: Confirm modified files import cleanly**

- [ ] **Step 3: Summarize residual risks**

Run:
```bash
pytest backend/tests/test_component_loader_dataclass_runtime.py backend/tests/test_component_versions_canonical_registration.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_export_contract.py
```

Expected:
- 0 failures
