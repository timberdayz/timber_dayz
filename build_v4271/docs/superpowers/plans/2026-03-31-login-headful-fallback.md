# Login Headful Fallback Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a login-stage headed fallback so that unrecoverable login failures can be manually completed to homepage, persisted, and then resumed through the normal collection flow.

**Architecture:** Keep normal login logic in platform login components, but move headed-fallback orchestration into the executor/tester layer. Successful manual completion saves session and then resumes from the standard login entry rather than trying to continue from an arbitrary mid-flow browser state.

**Tech Stack:** Python, async Playwright, session manager, verification protocol, pytest

---

### Task 1: Lock current and target fallback behavior with tests

**Files:**
- Create: `backend/tests/test_login_headful_fallback_contract.py`
- Modify: `backend/tests/test_component_tester_gate_contract.py`

- [ ] **Step 1: Write failing tests for login-stage manual fallback trigger conditions**
- [ ] **Step 2: Write failing tests for headed fallback success -> session save -> login short-circuit resume**
- [ ] **Step 3: Run tests to verify failure**

### Task 2: Add executor/tester orchestration for login headful fallback

**Files:**
- Modify: `tools/test_component.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/services/verification_protocol.py`

- [ ] **Step 1: Define login fallback trigger handling for `manual_intervention` / `slide_captcha`**
- [ ] **Step 2: Add headed login fallback runner using same account/session namespace**
- [ ] **Step 3: Re-check homepage readiness before accepting manual completion**
- [ ] **Step 4: Persist session and restart from normal login entry**

### Task 3: Wire TikTok login component into manual fallback branch

**Files:**
- Modify: `modules/platforms/tiktok/components/login.py`

- [ ] **Step 1: Add explicit `manual_intervention` branch for unrecoverable login states**
- [ ] **Step 2: Ensure homepage short-circuit still works after fallback session save**

### Task 4: Verify end-to-end behavior

**Files:**
- Modify: `backend/tests/test_login_headful_fallback_contract.py`

- [ ] **Step 1: Run targeted fallback tests**
- [ ] **Step 2: Run TikTok login/export regression tests**
- [ ] **Step 3: Run `py_compile` on changed files**
