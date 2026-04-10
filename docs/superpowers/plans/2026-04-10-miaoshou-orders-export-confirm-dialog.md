# Miaoshou Orders Export Confirm Dialog Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the Miaoshou orders export flow so the component confirms export when the site shows the new post-menu confirmation dialog, while keeping the no-dialog path working.

**Architecture:** Keep the existing Miaoshou orders export helper structure and insert one new helper boundary for export confirmation. The flow remains search -> export menu -> export menu item -> optional confirm dialog -> download wait -> progress/file handling.

**Tech Stack:** async Playwright, Python export component runtime, pytest source-contract tests

---

## File Map

- Modify: `modules/platforms/miaoshou/components/orders_export_base.py`
  - Add a dedicated confirm-dialog helper and place it in the download flow.
- Modify: `modules/platforms/miaoshou/components/orders_config.py`
  - Add confirm-dialog title/body/button text candidates.
- Modify: `backend/tests/test_miaoshou_orders_export_v2_flow.py`
  - Lock the new helper ordering in the run flow.
- Modify: `backend/tests/test_miaoshou_orders_export_contract.py`
  - Lock config and helper-source expectations.

## Task 1: Write Failing Tests

**Files:**
- Modify: `backend/tests/test_miaoshou_orders_export_v2_flow.py`
- Modify: `backend/tests/test_miaoshou_orders_export_contract.py`

- [ ] **Step 1: Add a failing source-contract test for confirm-dialog handling**

Require:
- a `_confirm_export_if_needed` helper exists
- the run flow keeps `expect_download(...)`
- confirm handling happens after `_click_export_all_orders(page)`

- [ ] **Step 2: Add a failing config-contract test**

Require:
- confirm-dialog title/body/button text candidates are declared in `OrdersSelectors`

- [ ] **Step 3: Run focused tests to verify red**

Run:

```powershell
python -m pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: failing assertions because the helper/config do not exist yet.

## Task 2: Implement The Confirm Dialog Step

**Files:**
- Modify: `modules/platforms/miaoshou/components/orders_export_base.py`
- Modify: `modules/platforms/miaoshou/components/orders_config.py`

- [ ] **Step 1: Add confirm-dialog config candidates**

Add:
- dialog titles
- dialog body texts
- confirm button texts

- [ ] **Step 2: Implement `_confirm_export_if_needed(page)`**

Behavior:
- detect a visible export confirm dialog
- click `确定导出` only in that dialog
- return quickly when no dialog appears

- [ ] **Step 3: Update the run flow**

Inside `expect_download(...)`:
- click `导出全部订单`
- confirm export if the dialog appears

- [ ] **Step 4: Keep generic popup cleanup untouched for pre-export cleanup only**

Do not route export confirmation through generic popup-close selectors.

## Task 3: Verify

**Files:**
- Re-run: `backend/tests/test_miaoshou_orders_export_contract.py`
- Re-run: `backend/tests/test_miaoshou_orders_export_v2_flow.py`

- [ ] **Step 1: Run focused tests**

```powershell
python -m pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Record residual risk**

Residual risk to note if tests pass:
- runtime site may change dialog wording again
- a future live-browser verification is still useful for end-to-end confirmation
