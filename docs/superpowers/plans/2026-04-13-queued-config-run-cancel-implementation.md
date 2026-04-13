# Queued Config Run Cancel Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to cancel collection config runs that are still queued, while leaving running config runs untouched.

**Architecture:** Extend the existing `CollectionConfigRun` service and schedule router with a queue-only cancellation path that flips `queued` runs to `cancelled`. Keep runner behavior unchanged so cancelled runs are naturally skipped because the runner only claims `queued` rows. Add a frontend queue action that is only rendered for queued runs and refreshes the queue after success.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, pytest

---

## File Map

- Modify: `backend/services/collection_config_run_service.py`
  Responsibility: add queue-only cancel state transition for `CollectionConfigRun`
- Modify: `backend/routers/collection_schedule.py`
  Responsibility: expose cancel endpoint for config runs
- Modify: `frontend/src/api/collection.js`
  Responsibility: add config-run cancel API call
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
  Responsibility: render cancel action for queued runs and refresh queue state
- Modify: `backend/tests/test_collection_config_run_service.py`
  Responsibility: cover service-level queued cancel rules
- Modify: `backend/tests/test_collection_config_schedule_sync_api.py`
  Responsibility: cover API-level cancel behavior
- Modify: `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: lock frontend queue cancel affordance into file contracts

## Task 1: Add Service-Level Queued Cancel

**Files:**
- Modify: `backend/tests/test_collection_config_run_service.py`
- Modify: `backend/services/collection_config_run_service.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run `python -m pytest backend/tests/test_collection_config_run_service.py -q` and verify the new test fails for missing cancel behavior**
- [ ] **Step 3: Implement minimal `cancel_run_by_run_id(...)` logic that only cancels `queued` runs**
- [ ] **Step 4: Run `python -m pytest backend/tests/test_collection_config_run_service.py -q` and verify it passes**

## Task 2: Add Config-Run Cancel API

**Files:**
- Modify: `backend/tests/test_collection_config_schedule_sync_api.py`
- Modify: `backend/routers/collection_schedule.py`

- [ ] **Step 1: Write the failing API tests**
- [ ] **Step 2: Run `python -m pytest backend/tests/test_collection_config_schedule_sync_api.py -q` and verify the new tests fail**
- [ ] **Step 3: Implement minimal cancel endpoint for queued config runs**
- [ ] **Step 4: Run `python -m pytest backend/tests/test_collection_config_schedule_sync_api.py -q` and verify it passes**

## Task 3: Add Frontend Queue Cancel Action

**Files:**
- Modify: `backend/tests/test_collection_frontend_contracts.py`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`

- [ ] **Step 1: Write the failing frontend contract test**
- [ ] **Step 2: Run `python -m pytest backend/tests/test_collection_frontend_contracts.py -q` and verify the new test fails**
- [ ] **Step 3: Add cancel API wrapper and queued-run cancel button in the queue panel**
- [ ] **Step 4: Run `python -m pytest backend/tests/test_collection_frontend_contracts.py -q` and verify it passes**

## Task 4: Focused Verification

**Files:**
- Modify as needed based on test failures

- [ ] **Step 1: Run `python -m pytest backend/tests/test_collection_config_run_service.py backend/tests/test_collection_config_schedule_sync_api.py backend/tests/test_collection_frontend_contracts.py -q`**
- [ ] **Step 2: Run `git status --short` and `git diff --stat`**
- [ ] **Step 3: Confirm only queued-config-run cancel related files changed**
