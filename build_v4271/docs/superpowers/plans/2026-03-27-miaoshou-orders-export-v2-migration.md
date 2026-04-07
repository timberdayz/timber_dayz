# Miaoshou Orders Export V2 Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `miaoshou/orders_export` onto the V2 slot model so it becomes the canonical Shopee-order export container, uses the unified `time_selection` contract, and relies on explicit search/export/download completion signals instead of recorder-style fallback behavior.

**Architecture:** The export component remains a container component, but all orchestration must stay inside the orders-export flow rather than leaking into top-level executor phases. The migration should lock the Miaoshou order path around explicit helper boundaries: page ready, subtype selection, popup cleanup, time selection, filter application, search refresh, export menu open, progress readiness, and final download confirmation.

**Tech Stack:** async Playwright, Python component runtime, V2 collection contracts, shared export gate semantics

---

## File Map

### Primary files

- Modify: `modules/platforms/miaoshou/components/orders_export.py`
  - Canonical orders export implementation.
- Modify: `modules/platforms/miaoshou/components/orders_config.py`
  - Selector/text candidates, preset labels, progress-dialog signals, export menu signals.

### Related runtime/test files

- Modify: `modules/apps/collection_center/python_component_adapter.py`
  - Only if orders-export loading or domain/sub-domain handling needs additional V2 tightening.
- Modify: `backend/routers/component_versions.py`
  - Only if component test runtime config for orders export needs a targeted patch.

### Tests

- Modify: `backend/tests/test_miaoshou_orders_export_contract.py`
- Add: `backend/tests/test_miaoshou_orders_export_v2_flow.py`
- Re-run: `backend/tests/test_component_test_runtime_config.py`
- Re-run: `backend/tests/test_collection_time_selection_contract.py`

---

### Task 1: Lock The Orders Export V2 Flow Contract

**Files:**
- Modify: `backend/tests/test_miaoshou_orders_export_contract.py`
- Add: `backend/tests/test_miaoshou_orders_export_v2_flow.py`

- [ ] **Step 1: Write failing flow tests**

Cover:
- canonical orders export remains `orders_export.py`
- flow requires `click_search()` before export
- export opens via hover/menu, not direct terminal click on the main button
- progress dialog is intermediate only; file landing is final success
- component uses unified `time_selection` semantics

- [ ] **Step 2: Run the focused export tests and confirm failure**

Run:

```bash
pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: FAIL until the full V2 flow contract is covered and implemented.

- [ ] **Step 3: Commit the failing test baseline**

```bash
git add backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py
git commit -m "test: define miaoshou orders export v2 flow contract"
```

### Task 2: Finish The Canonical Orders Export Flow

**Files:**
- Modify: `modules/platforms/miaoshou/components/orders_export.py`
- Modify: `modules/platforms/miaoshou/components/orders_config.py`

- [ ] **Step 1: Implement the V2 helper boundaries**

Ensure `orders_export.py` is structured around:
- `wait_navigation_ready`
- `ensure_orders_subtype_selected`
- `ensure_popup_closed`
- `ensure_time_selected`
- `ensure_order_statuses_selected`
- `click_search`
- `wait_search_results_ready`
- `ensure_export_menu_open`
- `click_export_all_orders`
- `wait_export_progress_ready`
- `wait_export_complete`

- [ ] **Step 2: Keep selectors/text in config, not inlined everywhere**

Move or keep in `orders_config.py`:
- date shortcuts
- custom input names
- search button texts
- export menu labels
- progress title/text candidates
- popup close selectors

- [ ] **Step 3: Re-run focused flow tests**

Run:

```bash
pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add modules/platforms/miaoshou/components/orders_export.py modules/platforms/miaoshou/components/orders_config.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py
git commit -m "refactor: migrate miaoshou orders export to v2 flow"
```

### Task 3: Lock Unified Time Selection Usage

**Files:**
- Modify: `modules/platforms/miaoshou/components/orders_export.py`
- Re-run: `backend/tests/test_component_test_runtime_config.py`
- Re-run: `backend/tests/test_collection_time_selection_contract.py`

- [ ] **Step 1: Add failing coverage if needed**

Cover:
- preset mode uses only `today/yesterday/last_7_days/last_30_days`
- custom mode reads `start_date/end_date/start_time/end_time`
- no mixed preset/custom fallback behavior remains

- [ ] **Step 2: Run contract regressions**

Run:

```bash
pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: PASS once the component fully respects the shared contract.

- [ ] **Step 3: Commit if contract-alignment changes were needed**

```bash
git add modules/platforms/miaoshou/components/orders_export.py backend/tests/test_component_test_runtime_config.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py
git commit -m "refactor: align miaoshou orders export with unified time selection"
```

### Task 4: Confirm Download Completion Semantics

**Files:**
- Modify: `modules/platforms/miaoshou/components/orders_export.py`
- Test: `backend/tests/test_miaoshou_orders_export_v2_flow.py`

- [ ] **Step 1: Add failing regression for final success criteria**

Cover:
- clicking export starts download listening before menu item click
- progress dialog presence is not enough
- final success requires landed non-empty file path

- [ ] **Step 2: Run the download regression and watch it fail**

Run:

```bash
pytest backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: FAIL if the component still allows progress-only success or late download capture.

- [ ] **Step 3: Tighten the implementation**

Keep the rules:
- start download listener before clicking the export menu item
- allow progress dialog as intermediate signal only
- confirm file existence and size before success

- [ ] **Step 4: Re-run the focused download regression**

Run:

```bash
pytest backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/platforms/miaoshou/components/orders_export.py backend/tests/test_miaoshou_orders_export_v2_flow.py
git commit -m "fix: enforce final download semantics for miaoshou orders export"
```

### Task 5: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run the focused orders export regression set**

Run:

```bash
pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py backend/tests/test_component_test_runtime_config.py backend/tests/test_collection_time_selection_contract.py -q
```

Expected: PASS

- [ ] **Step 2: Syntax-check touched files**

Run:

```bash
python -m py_compile modules/platforms/miaoshou/components/orders_export.py modules/platforms/miaoshou/components/orders_config.py
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: verify miaoshou orders export v2 migration"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-27-miaoshou-orders-export-v2-migration.md`. Ready to execute?
