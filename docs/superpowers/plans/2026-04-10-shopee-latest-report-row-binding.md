# Shopee Latest Report Row Binding Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Shopee `products` and `services/agent` exports click the download button for the current export row instead of a historical undownloaded row.

**Architecture:** Keep the fix local to the active canonical Shopee components. Introduce row-based report matching in `products_export.py`, reuse the same approach in `services_export_base.py`, and drive the change through regression tests that model mixed old/new report rows in the same dialog.

**Tech Stack:** Python, async Playwright component helpers, pytest, existing Shopee component configs, recorded page evidence under `output/playwright/work/shopee/`

---

### Task 1: Add Regression Tests For Row Binding

**Files:**
- Modify: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Write failing tests for mixed old/new report rows**

Cover:
- products export prefers the row whose text matches the current date signature over an older downloadable row
- products export keeps polling a matching row while it is still `processing`
- services-agent export reuses the same row-binding behavior for an `agent/chat` filename pattern

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_shopee_products_export.py -q`
Expected: FAIL because current helpers only look for the first available download action

- [ ] **Step 3: Keep test doubles focused on row identity**

Add small fake panel/row/button helpers that expose:
- row text
- visible action text
- click tracking

- [ ] **Step 4: Re-run the targeted tests**

Run: `pytest tests/unit/test_shopee_products_export.py -q`
Expected: still FAIL until production code is updated

### Task 2: Implement Row-Based Matching In Products Export

**Files:**
- Modify: `modules/platforms/shopee/components/products_export.py`

- [ ] **Step 1: Add helpers for report-row text and expected signatures**

Implement focused helpers for:
- row text normalization
- deriving `YYYYMMDD_YYYYMMDD` signatures from config
- products filename-prefix matching

- [ ] **Step 2: Add panel row enumeration and baseline snapshot helpers**

Implement helpers to:
- collect visible report rows from the latest-report panel
- capture baseline row texts before export when available
- classify row status as `download`, `processing`, or other

- [ ] **Step 3: Replace top-button scanning with target-row resolution**

Update the waiting logic so it:
- resolves the target row from expected signature or baseline delta
- keeps polling the same logical row if it is still `processing`
- returns only the download button inside the matched row

- [ ] **Step 4: Keep existing file download completion behavior unchanged**

Do not redesign output-path or final save logic; only swap the row-selection step.

- [ ] **Step 5: Run products regression tests**

Run: `pytest tests/unit/test_shopee_products_export.py -q`
Expected: PASS for the new products cases

### Task 3: Reuse Row Binding In Services Agent Export

**Files:**
- Modify: `modules/platforms/shopee/components/services_export_base.py`
- Modify: `modules/platforms/shopee/components/services_agent_export.py`

- [ ] **Step 1: Add subtype-aware signature matching**

Implement subtype-specific report-row matching for `agent`, centered on the visible report filename and current date signature.

- [ ] **Step 2: Reuse the same row-resolution flow as products**

Avoid another generic `first panel action` scan. The base should resolve a target row and click only within that row.

- [ ] **Step 3: Preserve existing subtype/page boundaries**

Do not broaden this into a fake universal Shopee export abstraction.

- [ ] **Step 4: Re-run targeted tests**

Run: `pytest tests/unit/test_shopee_products_export.py -q`
Expected: PASS including services-agent coverage

### Task 4: Verify The Fix And Guard The Regression

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] **Step 1: Run the focused regression suite**

Run: `pytest tests/unit/test_shopee_products_export.py -q`
Expected: PASS with zero failures

- [ ] **Step 2: Review the final diff**

Confirm the change set is limited to:
- Shopee report-row matching helpers
- Shopee services-agent reuse
- unit regression tests

- [ ] **Step 3: Update the local planning files**

Record:
- the root cause
- the implemented row-binding fix
- the verification command and result
