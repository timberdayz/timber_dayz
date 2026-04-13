# Startup Latest Entrypoint Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure launching from legacy snapshot entrypoints automatically delegates to the latest workspace root entrypoints.

**Architecture:** Keep the change limited to startup scripts. Add a tiny delegation helper in legacy `build_v4271` entrypoints so they invoke the repository-root `run.py` or `local_run.py` with the same CLI arguments and working directory.

**Tech Stack:** Python, subprocess, pathlib, pytest

---

### Task 1: Cover legacy startup delegation with tests

**Files:**
- Create: `backend/tests/test_legacy_startup_entrypoints.py`
- Test: `backend/tests/test_legacy_startup_entrypoints.py`

- [ ] **Step 1: Write the failing tests**

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_legacy_startup_entrypoints.py -q`
Expected: FAIL because legacy startup delegation helper does not exist yet

### Task 2: Implement delegation in legacy snapshot entrypoints

**Files:**
- Modify: `build_v4271/run.py`
- Modify: `build_v4271/local_run.py`
- Test: `backend/tests/test_legacy_startup_entrypoints.py`

- [ ] **Step 1: Add a minimal delegation helper**

- [ ] **Step 2: Call the helper before normal startup**

- [ ] **Step 3: Re-run targeted tests**

Run: `pytest backend/tests/test_legacy_startup_entrypoints.py -q`
Expected: PASS

### Task 3: Verify no regressions in existing run.py tests

**Files:**
- Test: `backend/tests/data_pipeline/test_run_py.py`
- Test: `backend/tests/test_local_infra_runtime.py`

- [ ] **Step 1: Run focused startup test suite**

Run: `pytest backend/tests/test_legacy_startup_entrypoints.py backend/tests/data_pipeline/test_run_py.py backend/tests/test_local_infra_runtime.py -q`
Expected: PASS
