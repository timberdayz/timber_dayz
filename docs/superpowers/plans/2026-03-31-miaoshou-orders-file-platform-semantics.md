# Miaoshou Orders File Platform Semantics Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure Miaoshou-collected Shopee/TikTok orders files are registered and displayed using the business platform (`shopee`/`tiktok`) while preserving `miaoshou` only as the collection source.

**Architecture:** Keep collection runtime semantics unchanged (`miaoshou` + orders sub-flow), but normalize file registration semantics at `catalog_files`. Registration will write `platform_code` as the business platform, preserve `source_platform` as `miaoshou`, and clear `orders` sub-domain usage. File grouping reads will group by `platform_code` instead of `COALESCE(source_platform, platform_code)`.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest

---

### Task 1: Add Regression Tests

**Files:**
- Create: `backend/tests/test_file_registration_service_platform_semantics.py`
- Modify: `backend/tests/test_field_mapping_file_groups_platform_semantics.py`

- [ ] **Step 1: Write the failing tests**

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest backend/tests/test_file_registration_service_platform_semantics.py backend/tests/test_field_mapping_file_groups_platform_semantics.py -q`

Expected: FAIL because the current registration logic writes the collection platform to `platform_code`, preserves `orders` `sub_domain`, and file group queries still prioritize `source_platform`.

- [ ] **Step 3: Implement the minimal fix**

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `pytest backend/tests/test_file_registration_service_platform_semantics.py backend/tests/test_field_mapping_file_groups_platform_semantics.py -q`

Expected: PASS

### Task 2: Update File Registration Semantics

**Files:**
- Modify: `backend/services/file_registration_service.py`

- [ ] **Step 1: Derive canonical file-registration dimensions from runtime inputs**

- [ ] **Step 2: Write `platform_code` as business platform, `source_platform` as collection source**

- [ ] **Step 3: Clear `orders` `sub_domain` when registering to `catalog_files`**

### Task 3: Update File Grouping Read Semantics

**Files:**
- Modify: `backend/routers/field_mapping_files.py`

- [ ] **Step 1: Group and list files by `platform_code`**

- [ ] **Step 2: Keep `source_platform` only for traceability, not primary grouping**

### Task 4: Verify

**Files:**
- Test: `backend/tests/test_file_registration_service_platform_semantics.py`
- Test: `backend/tests/test_field_mapping_file_groups_platform_semantics.py`

- [ ] **Step 1: Run targeted tests**

Run: `pytest backend/tests/test_file_registration_service_platform_semantics.py backend/tests/test_field_mapping_file_groups_platform_semantics.py -q`

- [ ] **Step 2: If stable, run an adjacent regression test**

Run: `pytest backend/tests/test_field_mapping_scan_pure_registration.py -q`
