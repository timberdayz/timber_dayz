# Shopee Products Export Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a canonical `shopee/products_export` component that reuses Shopee business-analysis navigation, shop switching, and date selection logic, then triggers export and treats automatic file download completion as success.

**Architecture:** Keep the Shopee business-analysis common flow as reusable helper logic rather than three unrelated scripts. `products_export` should own the domain-specific entry page and export button behavior, while `shop_switch` and `date_picker` helpers cover the stable cross-domain parts. Throttling on export must be an explicit branch, not an accidental retry.

**Tech Stack:** Python, Playwright async API, pytest, current collection executor/component contracts, pwcli evidence from `output/playwright/work/shopee/products-export/`

---

### Task 1: Lock Down Shopee Common Flow Tests

**Files:**
- Create: `backend/tests/test_shopee_business_analysis_common_flow.py`
- Test: `backend/tests/test_shopee_business_analysis_common_flow.py`

- [ ] **Step 1: Write failing tests for shared Shopee business-analysis rules**

Cover:
- business-analysis navigation target mapping for `products`, `services`, `analytics`
- date preset/granularity mapping
- analytics rejecting `today_realtime`
- shop-switch success detection helper inputs

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_shopee_business_analysis_common_flow.py -q`
Expected: FAIL because helper module does not exist yet

- [ ] **Step 3: Write minimal shared helper module**

Create a focused helper/config module that only contains:
- domain route mapping
- allowed presets by domain
- date-mode normalization
- shared semantic constants for later component use

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_shopee_business_analysis_common_flow.py -q`
Expected: PASS

### Task 2: Add Products Export Component Tests

**Files:**
- Create: `backend/tests/test_shopee_products_export_component.py`
- Test: `backend/tests/test_shopee_products_export_component.py`

- [ ] **Step 1: Write failing tests for products export behavior**

Cover:
- products export page URL detection
- date preset acceptance for `daily`, `weekly`, `monthly`
- export throttling detection
- automatic-download completion as success criterion
- failure when export is throttled and never recovers

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_shopee_products_export_component.py -q`
Expected: FAIL because canonical `products_export.py` is missing

- [ ] **Step 3: Write minimal component code to satisfy the tests**

Implement only the helpers needed by the tests first:
- page detection
- export trigger
- throttling detection
- success result building

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_shopee_products_export_component.py -q`
Expected: PASS

### Task 3: Implement Shared Shopee Helpers

**Files:**
- Create: `modules/platforms/shopee/components/business_analysis_common.py`
- Modify: `modules/platforms/shopee/components/__init__.py`

- [ ] **Step 1: Add domain routing definitions**

Include:
- `products`
- `services`
- `analytics`

Each entry should define:
- expected URL markers
- page labels
- allowed presets

- [ ] **Step 2: Add date selection normalization**

Support:
- `today_realtime`
- `yesterday`
- `last_7_days`
- `last_30_days`
- `daily`
- `weekly`
- `monthly`

- [ ] **Step 3: Add shop-switch/date-picker semantic helper contracts**

Add small focused helpers for:
- current shop text normalization
- domain capability lookup
- preset validation by domain

### Task 4: Implement Canonical Shopee Products Export

**Files:**
- Create: `modules/platforms/shopee/components/products_export.py`
- Create: `modules/platforms/shopee/components/products_config.py`

- [ ] **Step 1: Add metadata and config surface**

Implement:
- `platform = "shopee"`
- `component_type = "export"`
- `data_domain = "products"`
- target page URL/path markers
- export button selectors
- throttling message selectors

- [ ] **Step 2: Add products page readiness helpers**

Implement:
- `detect_products_page_ready`
- `ensure_products_page_ready`
- `detect_export_button_ready`

- [ ] **Step 3: Add export throttling helpers**

Implement:
- `detect_export_throttled`
- `wait_export_retry_ready`

- [ ] **Step 4: Implement export runtime flow**

Implement:
- ensure business-analysis products page
- ensure selected shop
- ensure chosen date range
- click export once
- handle throttling branch
- treat automatic download completion as success

### Task 5: Verify Registration And Discovery

**Files:**
- Test: `backend/tests/test_component_versions_canonical_registration.py`
- Test: `backend/tests/test_active_collection_components.py`

- [ ] **Step 1: Run new shared-flow tests**

Run: `pytest backend/tests/test_shopee_business_analysis_common_flow.py -q`

- [ ] **Step 2: Run new products-export tests**

Run: `pytest backend/tests/test_shopee_products_export_component.py -q`

- [ ] **Step 3: Run canonical registration coverage**

Run: `pytest backend/tests/test_component_versions_canonical_registration.py -q`

- [ ] **Step 4: Run active-component discovery coverage**

Run: `pytest backend/tests/test_active_collection_components.py -q`

- [ ] **Step 5: Review final diff**

Confirm this batch only adds:
- shared Shopee business-analysis helper/config
- canonical `products_export`
- focused test coverage
