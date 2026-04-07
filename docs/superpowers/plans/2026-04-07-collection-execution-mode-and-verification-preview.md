# Collection Execution Mode And Verification Preview Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make collection task `execution_mode` map strictly to runtime browser launch behavior while preserving login-only headful fallback, and add click-to-preview support for verification screenshots.

**Architecture:** Route config/task execution mode through a single explicit launch-options helper that accepts the persisted mode instead of inferring it from development defaults. Keep login-only `manual_continue` fallback as a separate executor path. Reuse the shared `VerificationResumeDialog` and upgrade the screenshot block to Element Plus image preview without changing backend screenshot APIs.

**Tech Stack:** FastAPI, SQLAlchemy async, Playwright async, Vue 3, Element Plus, node:test, pytest

---

### Task 1: Lock Backend Execution-Mode Semantics With Tests

**Files:**
- Modify: `backend/tests/test_browser_config_helper.py`
- Modify: `backend/tests/test_collection_task_live_updates.py`

- [ ] **Step 1: Write the failing backend tests**
- [ ] **Step 2: Run targeted pytest commands and verify the new assertions fail for the current implementation**
- [ ] **Step 3: Cover both helper-level behavior and background task launch wiring**

### Task 2: Implement Strict Headless/Headed Launch Behavior

**Files:**
- Modify: `modules/apps/collection_center/browser_config_helper.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `modules/apps/collection_center/executor_v2.py` if parameter plumbing needs adjustment

- [ ] **Step 1: Introduce an execution-mode-aware launch helper that preserves debug override only for explicit headed/manual flows**
- [ ] **Step 2: Update collection task background execution to pass the persisted mode explicitly**
- [ ] **Step 3: Keep login fallback launching a dedicated headed browser for `manual_continue` verification types**
- [ ] **Step 4: Re-run targeted pytest commands and confirm green**

### Task 3: Lock Verification Screenshot Preview Behavior With Tests

**Files:**
- Modify: `frontend/scripts/verificationResumeDialogExperience.test.mjs`

- [ ] **Step 1: Add failing source-contract assertions for preview-capable screenshot rendering**
- [ ] **Step 2: Run the targeted node test and verify it fails before implementation**

### Task 4: Implement Click-To-Preview Verification Screenshot UI

**Files:**
- Modify: `frontend/src/components/verification/VerificationResumeDialog.vue`

- [ ] **Step 1: Replace the plain `<img>` block with preview-capable Element Plus image rendering**
- [ ] **Step 2: Preserve existing load-failure fallback copy and non-screenshot paths**
- [ ] **Step 3: Re-run the targeted node test and any shared dialog source-contract tests**

### Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the full targeted backend pytest suite for touched execution-mode files**
- [ ] **Step 2: Run the relevant frontend node:test scripts for shared verification dialog usage**
- [ ] **Step 3: Inspect `git diff --stat` and confirm the change set matches the approved scope**
