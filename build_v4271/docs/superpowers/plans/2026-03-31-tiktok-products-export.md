# TikTok Products Export Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canonical TikTok products-domain export component that navigates to product-analysis, applies supported quick-range date options, and returns a real downloaded file path.

**Architecture:** Implement a thin orchestrator in `products_export.py` that composes the existing TikTok `shop_switch`, `date_picker`, and `export` helpers. Keep page semantics products-specific while reusing stable helper behaviors already validated by snapshot evidence.

**Tech Stack:** Python, async Playwright component pattern, pytest

---

### Task 1: Add failing tests for the canonical products export entry

**Files:**
- Create: `backend/tests/test_tiktok_products_export_component.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the new test file and confirm failure**

### Task 2: Implement the canonical products export component

**Files:**
- Create: `modules/platforms/tiktok/components/products_export.py`

- [ ] **Step 1: Add products-page URL and readiness helpers**
- [ ] **Step 2: Compose shop switch + date picker + shared export**
- [ ] **Step 3: Return `ExportResult` with real `file_path`**

### Task 3: Verify and stabilize

**Files:**
- Modify: `backend/tests/test_tiktok_products_export_component.py`
- Modify: `modules/platforms/tiktok/components/products_export.py`

- [ ] **Step 1: Run targeted TikTok tests**
- [ ] **Step 2: Run broader TikTok regression tests**
- [ ] **Step 3: Run `py_compile` on new/changed files**
