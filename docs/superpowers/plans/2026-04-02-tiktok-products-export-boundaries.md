# TikTok Products Export Boundaries Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the TikTok products-domain export flow into a mature platform-specific component with explicit entry-state checks, confirmed shop normalization, confirmed quick-date execution, and real download-based export success.

**Architecture:** Keep TikTok components platform-specific while upgrading their runtime boundaries to follow Shopee-grade operational discipline. `products_export.py` becomes the canonical orchestrator, `date_picker.py` confirms quick-date state instead of only clicking controls, `shop_switch.py` confirms normalized region context instead of only rewriting the URL, and `export.py` remains the download executor.

**Tech Stack:** Python, async Playwright component pattern, pytest

---

### Task 1: Rebuild the products-export contract tests around mature boundaries

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_tiktok_products_export_component.py`
- Reference: `F:\Vscode\python_programme\AI_code\xihong_erp\docs\superpowers\specs\2026-04-02-tiktok-products-export-boundaries-design.md`

- [ ] **Step 1: Add failing tests for stage-scoped failures and success boundaries**

Add tests for:
- product-page readiness detection using URL + page signals
- shop-switch failure preventing export
- current quick-date already satisfied causing date stage skip
- quick-date confirmation failure preventing export
- export success requiring non-empty `file_path`
- unsupported custom-date request staying explicit and non-destructive

- [ ] **Step 2: Run the products-export test file and confirm new tests fail for the expected reasons**

Run: `pytest backend/tests/test_tiktok_products_export_component.py -q`

Expected: FAIL on the newly added assertions for readiness, confirmation, or failure classification.

- [ ] **Step 3: Commit the red test state**

```bash
git add backend/tests/test_tiktok_products_export_component.py
git commit -m "test: expand tiktok products export boundary coverage"
```

### Task 2: Upgrade the date-picker contract from click helper to confirmed quick-date operator

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_tiktok_date_picker_component.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\date_picker.py`

- [ ] **Step 1: Add failing tests for current-state recognition and post-click confirmation**

Add tests for:
- detecting when `LAST_7_DAYS` is already active
- detecting when `LAST_28_DAYS` is already active
- failing when panel opens and click succeeds but no confirmation signal appears
- keeping custom-date behavior explicit without pretending success

- [ ] **Step 2: Run the date-picker test file and confirm failure**

Run: `pytest backend/tests/test_tiktok_date_picker_component.py -q`

Expected: FAIL on the new state-recognition or confirmation assertions.

- [ ] **Step 3: Implement minimal confirmation-aware date-picker logic**

Implement focused helpers in `modules/platforms/tiktok/components/date_picker.py`:
- current page kind detection for products pages
- date-trigger text reading
- current quick-option recognition
- panel-open detection
- quick-option apply
- post-apply confirmation wait
- unsupported custom-date state path

Do not implement custom-date selection in this task.

- [ ] **Step 4: Run the date-picker tests and confirm green**

Run: `pytest backend/tests/test_tiktok_date_picker_component.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tiktok_date_picker_component.py modules/platforms/tiktok/components/date_picker.py
git commit -m "feat: harden tiktok quick date picker boundaries"
```

### Task 3: Upgrade shop switching from URL rewrite to confirmed context normalization

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_tiktok_shop_switch_component.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\shop_switch.py`

- [ ] **Step 1: Add failing tests for context confirmation**

Add tests for:
- region mismatch after navigation returning failure
- visible store display required for success when the page exposes region text
- preserving path and unrelated query params during rewrite
- backfilling `shop_region`, `shop_name`, and `shop_display_name`

- [ ] **Step 2: Run the shop-switch test file and confirm failure**

Run: `pytest backend/tests/test_tiktok_shop_switch_component.py -q`

Expected: FAIL on the new confirmation assertions.

- [ ] **Step 3: Implement minimal confirmed shop-normalization logic**

Implement focused helpers in `modules/platforms/tiktok/components/shop_switch.py`:
- target region resolution
- query rewrite preserving path/query
- page region extraction from URL and visible display
- short stabilization wait loop after navigation
- explicit failure when normalized region cannot be confirmed

- [ ] **Step 4: Run the shop-switch tests and confirm green**

Run: `pytest backend/tests/test_tiktok_shop_switch_component.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tiktok_shop_switch_component.py modules/platforms/tiktok/components/shop_switch.py
git commit -m "feat: confirm tiktok shop normalization state"
```

### Task 4: Rebuild the products orchestrator around staged readiness and confirmation

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\products_export.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_tiktok_products_export_component.py`
- Reference: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\date_picker.py`
- Reference: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\shop_switch.py`
- Reference: `F:\Vscode\python_programme\AI_code\xihong_erp\modules\platforms\tiktok\components\export.py`

- [ ] **Step 1: Implement products-page readiness helpers**

Add helpers for:
- entry-state detection using URL + visible signals
- canonical products deep-link resolution
- products-page readiness detection after navigation
- quick-date request resolution from config
- explicit custom-date reserved path

- [ ] **Step 2: Implement staged orchestration**

Update `run()` to:
- detect entry state
- deep-link when needed
- stop on stable login-required state
- require products-page readiness
- normalize shop context and stop on failure
- skip date execution when already satisfied
- apply supported quick date and require confirmation
- trigger export only after earlier stages succeed
- require non-empty `file_path`

- [ ] **Step 3: Run the products-export tests and confirm green**

Run: `pytest backend/tests/test_tiktok_products_export_component.py -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_tiktok_products_export_component.py modules/platforms/tiktok/components/products_export.py
git commit -m "feat: rebuild tiktok products export boundaries"
```

### Task 5: Run focused regression verification for the TikTok component set

**Files:**
- Verify only; no file changes intended

- [ ] **Step 1: Run the targeted TikTok component tests**

Run:
- `pytest backend/tests/test_tiktok_date_picker_component.py -q`
- `pytest backend/tests/test_tiktok_shop_switch_component.py -q`
- `pytest backend/tests/test_tiktok_products_export_component.py -q`
- `pytest backend/tests/test_tiktok_export_component.py -q`

Expected: PASS for all targeted TikTok component suites.

- [ ] **Step 2: Run compile verification on changed component files**

Run:
- `python -m py_compile modules/platforms/tiktok/components/date_picker.py`
- `python -m py_compile modules/platforms/tiktok/components/shop_switch.py`
- `python -m py_compile modules/platforms/tiktok/components/products_export.py`

Expected: no output

- [ ] **Step 3: Commit any final stabilization edits**

```bash
git add backend/tests/test_tiktok_date_picker_component.py backend/tests/test_tiktok_shop_switch_component.py backend/tests/test_tiktok_products_export_component.py modules/platforms/tiktok/components/date_picker.py modules/platforms/tiktok/components/shop_switch.py modules/platforms/tiktok/components/products_export.py
git commit -m "test: verify tiktok product export boundary redesign"
```
