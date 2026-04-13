# Shopee Login Shell Stability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Shopee login treat stable logged-in shell pages as success and wait for page stability before declaring login state.

**Architecture:** Keep the fix focused on the canonical Shopee login component and the shared Shopee login status detector. First lock the regression with tests, then implement a shared “stable shell success” path and finally align runtime gate behavior so component execution and collection runtime no longer disagree.

**Tech Stack:** Python, async Playwright-style page fakes, pytest, canonical collection runtime helpers

---

## File Map

- Modify: `modules/platforms/shopee/components/login.py`
  Responsibility: canonical Shopee login success semantics, post-login outcome waiting, manual/OTP recovery behavior.
- Modify: `modules/utils/login_status_detector.py`
  Responsibility: shared runtime login-state detection for Shopee URL, cookie, and shell-element evidence.
- Modify: `tests/unit/test_shopee_login.py`
  Responsibility: unit regression coverage for Shopee login component timing and shell-success behavior.
- Modify: `tests/unit/test_login_status_detector.py`
  Responsibility: detector regression coverage for Shopee shell pages and conservative login-page fallback.
- Modify: `backend/tests/test_collection_runtime_session.py` only if runtime wait semantics need explicit shared gate coverage.

### Task 1: Lock the Shopee shell-page regression in login component tests

**Files:**
- Modify: `tests/unit/test_shopee_login.py`
- Test: `tests/unit/test_shopee_login.py`

- [ ] **Step 1: Write the failing test for shell-page success after OTP/manual completion**

Add a test proving that a page with seller-center shell signals, account menu, and customer-service/chat affordances is treated as successful even when the main panel is not the homepage.

- [ ] **Step 2: Write the failing test for delayed shell stabilization**

Add a test where the page briefly still exposes login-form DOM before stabilizing into shell signals; expected result is no early failure.

- [ ] **Step 3: Run the targeted login tests to verify they fail**

Run: `python -m pytest tests/unit/test_shopee_login.py -q`
Expected: FAIL on the new shell-success and stabilization cases.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/unit/test_shopee_login.py
git commit -m "test: cover shopee login shell stability cases"
```

### Task 2: Implement stable shell-success semantics in `shopee/login.py`

**Files:**
- Modify: `modules/platforms/shopee/components/login.py`
- Test: `tests/unit/test_shopee_login.py`

- [ ] **Step 1: Introduce a distinct stable shell success path**

Update `_wait_for_post_login_outcome()` so `_session_shell_looks_ready()` yields a success-like outcome rather than `manual_intervention`.

- [ ] **Step 2: Add explicit page-stability waiting before final success/failure**

Require repeated successful polls or equivalent stability confirmation before returning success or failure from post-login waiting.

- [ ] **Step 3: Keep conservative failure boundaries intact**

Ensure OTP visible, slide captcha visible, or pure login-form pages still return verification/failure rather than shell success.

- [ ] **Step 4: Run the login component tests**

Run: `python -m pytest tests/unit/test_shopee_login.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the login component implementation**

```bash
git add modules/platforms/shopee/components/login.py tests/unit/test_shopee_login.py
git commit -m "fix: accept stable shopee shell pages after login"
```

### Task 3: Lock detector regressions for shell pages and mixed DOM pages

**Files:**
- Modify: `tests/unit/test_login_status_detector.py`
- Test: `tests/unit/test_login_status_detector.py`

- [ ] **Step 1: Write the failing detector test for logged-in shell pages**

Add a Shopee detector case where URL is non-homepage or transitional but shell selectors and/or auth cookies indicate an authenticated seller shell.

- [ ] **Step 2: Write the failing detector test for mixed login DOM plus shell evidence**

Add a case proving the detector does not immediately prefer a residual password field over stronger authenticated shell evidence once the page is stable.

- [ ] **Step 3: Run the targeted detector tests to verify they fail**

Run: `python -m pytest tests/unit/test_login_status_detector.py -q`
Expected: FAIL on the new Shopee shell detection cases.

- [ ] **Step 4: Commit the failing detector tests**

```bash
git add tests/unit/test_login_status_detector.py
git commit -m "test: cover shopee shell login detection"
```

### Task 4: Implement detector alignment for Shopee shell pages

**Files:**
- Modify: `modules/utils/login_status_detector.py`
- Test: `tests/unit/test_login_status_detector.py`

- [ ] **Step 1: Expand Shopee logged-in selectors with stable shell signals**

Add seller-shell evidence such as account-menu, managed-service entry, customer-service/message/chat affordances that appear after authenticated shell load.

- [ ] **Step 2: Make detector ordering less brittle for shell pages**

Keep true login pages failing, but avoid treating a single residual password field as final if stronger authenticated shell evidence or cookies indicate login success.

- [ ] **Step 3: Run the detector tests**

Run: `python -m pytest tests/unit/test_login_status_detector.py -q`
Expected: PASS.

- [ ] **Step 4: Commit the detector implementation**

```bash
git add modules/utils/login_status_detector.py tests/unit/test_login_status_detector.py
git commit -m "fix: recognize stable shopee seller shell as logged in"
```

### Task 5: Verify runtime gate behavior against the new semantics

**Files:**
- Modify: `backend/tests/test_collection_runtime_session.py` if needed
- Modify: `backend/tests/test_runtime_gate_contract.py` if needed
- Test: `backend/tests/test_collection_runtime_session.py`
- Test: `backend/tests/test_runtime_gate_contract.py`

- [ ] **Step 1: Add runtime-gate regression coverage only if current tests do not already cover stability waiting**

Prefer the smallest targeted regression proving `check_login_gate_ready()` accepts the new detector result.

- [ ] **Step 2: Run the runtime gate tests**

Run: `python -m pytest backend/tests/test_collection_runtime_session.py backend/tests/test_runtime_gate_contract.py -q`
Expected: PASS.

- [ ] **Step 3: Commit runtime gate test updates if any**

```bash
git add backend/tests/test_collection_runtime_session.py backend/tests/test_runtime_gate_contract.py
git commit -m "test: align runtime gate with shopee shell login semantics"
```

### Task 6: Final verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-13-shopee-login-shell-stability-design.md` only if implementation materially changes the design
- Modify: `docs/superpowers/plans/2026-04-13-shopee-login-shell-stability.md` to check off completed steps if executing in-plan

- [ ] **Step 1: Run focused verification suite**

Run: `python -m pytest tests/unit/test_shopee_login.py tests/unit/test_login_status_detector.py backend/tests/test_collection_runtime_session.py backend/tests/test_runtime_gate_contract.py -q`
Expected: PASS.

- [ ] **Step 2: Run lightweight syntax verification on touched runtime files**

Run: `python -m py_compile modules/platforms/shopee/components/login.py modules/utils/login_status_detector.py modules/apps/collection_center/runtime_session.py`
Expected: no output.

- [ ] **Step 3: Inspect diff scope**

Run: `git diff -- modules/platforms/shopee/components/login.py modules/utils/login_status_detector.py tests/unit/test_shopee_login.py tests/unit/test_login_status_detector.py backend/tests/test_collection_runtime_session.py backend/tests/test_runtime_gate_contract.py docs/superpowers/specs/2026-04-13-shopee-login-shell-stability-design.md docs/superpowers/plans/2026-04-13-shopee-login-shell-stability.md`
Expected: changes are limited to Shopee login success semantics, detector alignment, and related tests/docs.

- [ ] **Step 4: Commit final integrated fix**

```bash
git add modules/platforms/shopee/components/login.py modules/utils/login_status_detector.py tests/unit/test_shopee_login.py tests/unit/test_login_status_detector.py backend/tests/test_collection_runtime_session.py backend/tests/test_runtime_gate_contract.py docs/superpowers/specs/2026-04-13-shopee-login-shell-stability-design.md docs/superpowers/plans/2026-04-13-shopee-login-shell-stability.md
git commit -m "fix: stabilize shopee login shell detection"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-13-shopee-login-shell-stability.md`. Ready to execute?
