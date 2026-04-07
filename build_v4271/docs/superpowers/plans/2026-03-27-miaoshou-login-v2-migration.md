# Miaoshou Login V2 Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `miaoshou/login` onto the V2 canonical model so the canonical source file becomes the maintenance entrypoint, login success is gated by observable signals, and graphical captcha recovery remains compatible with both component testing and formal collection.

**Architecture:** This migration keeps the shared verification recovery contract intact while collapsing Miaoshou login toward the V2 two-layer model: canonical `login.py` as the maintenance source, versioned runtime files as runtime artifacts only. The implementation should move success detection away from recorder-era placeholders and align it with login gate evaluation rather than URL guesswork.

**Tech Stack:** FastAPI, Pydantic, async Playwright, Python component runtime, shared verification state contracts

---

## File Map

### Primary files

- Modify: `modules/platforms/miaoshou/components/login.py`
  - Promote this file from compatibility alias to canonical maintenance implementation.
- Modify: `modules/platforms/miaoshou/components/login_v1_0_3.py`
  - Either align it to the canonical implementation or replace it with a thin versioned wrapper after the canonical logic is stable.
- Modify: `modules/platforms/miaoshou/components/miaoshou_login.py`
  - Reduce or retire recorder-era duplication once canonical `login.py` owns the real logic.

### Related runtime/test files

- Modify: `modules/utils/login_status_detector.py`
  - Only if Miaoshou login detection needs new stable signals exposed centrally.
- Modify: `modules/apps/collection_center/transition_gates.py`
  - Only if a missing login-ready signal needs a shared gate addition.
- Modify: `tools/test_component.py`
  - Only if the login test harness needs explicit handling for a tightened Miaoshou success gate.

### Tests

- Modify: `backend/tests/test_miaoshou_login_component.py`
- Add: `backend/tests/test_miaoshou_login_v2_contract.py`
- Re-run: `backend/tests/test_component_tester_verification_flow.py`
- Re-run: `backend/tests/test_collection_verification_flow.py`
- Re-run: `backend/tests/test_collection_multi_account_verification_contract.py`

---

### Task 1: Lock The Canonical Login Success Contract

**Files:**
- Modify: `backend/tests/test_miaoshou_login_component.py`
- Add: `backend/tests/test_miaoshou_login_v2_contract.py`

- [ ] **Step 1: Write failing tests for canonical success detection**

Add tests covering:
- `login.py` is the canonical maintenance target, not just an alias shell
- success detection accepts only real post-login URLs/signals such as `/welcome` or dashboard pages
- success detection rejects root/public pages and login redirect pages
- no placeholder “always success after click” behavior remains

- [ ] **Step 2: Run the login component tests and watch them fail**

Run:

```bash
pytest backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py -q
```

Expected: FAIL on missing canonical contract and/or recorder-era success placeholder behavior.

- [ ] **Step 3: Commit the failing test baseline**

```bash
git add backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py
git commit -m "test: define miaoshou login v2 contract"
```

### Task 2: Move Canonical Logic Into `login.py`

**Files:**
- Modify: `modules/platforms/miaoshou/components/login.py`
- Modify: `modules/platforms/miaoshou/components/miaoshou_login.py`

- [ ] **Step 1: Implement the canonical login logic in `login.py`**

`login.py` should own:
- login page navigation
- username/password fill
- captcha detection and screenshot capture
- post-submit login confirmation helpers

It should no longer be a passive alias over `miaoshou_login.py`.

- [ ] **Step 2: Reduce `miaoshou_login.py` to compatibility-only status**

Choose one of these outcomes:
- make it a thin import wrapper over canonical `login.py`, or
- clearly mark it archive/compatibility-only and stop using it as the maintenance source

- [ ] **Step 3: Re-run the contract tests**

Run:

```bash
pytest backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add modules/platforms/miaoshou/components/login.py modules/platforms/miaoshou/components/miaoshou_login.py backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py
git commit -m "refactor: move miaoshou login to canonical v2 entrypoint"
```

### Task 3: Align Versioned Runtime File With Canonical Login

**Files:**
- Modify: `modules/platforms/miaoshou/components/login_v1_0_3.py`

- [ ] **Step 1: Write a failing parity test**

Add a focused test asserting the stable runtime file does not diverge from the canonical login success/verification behavior.

- [ ] **Step 2: Run the parity test and confirm failure**

Run:

```bash
pytest backend/tests/test_miaoshou_login_v2_contract.py -q
```

Expected: FAIL if `login_v1_0_3.py` still carries placeholder success logic.

- [ ] **Step 3: Convert `login_v1_0_3.py` into a thin aligned runtime wrapper**

Prefer:
- canonical logic in `login.py`
- versioned file delegating to canonical implementation or reproducing the same gated behavior with no extra drift

- [ ] **Step 4: Re-run parity tests**

Run:

```bash
pytest backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/platforms/miaoshou/components/login_v1_0_3.py backend/tests/test_miaoshou_login_v2_contract.py
git commit -m "refactor: align miaoshou stable login runtime with canonical v2"
```

### Task 4: Preserve Shared Verification Recovery Semantics

**Files:**
- Reuse existing runtime files unless tests force a focused patch
- Test: `backend/tests/test_component_tester_verification_flow.py`
- Test: `backend/tests/test_collection_verification_flow.py`
- Test: `backend/tests/test_collection_multi_account_verification_contract.py`

- [ ] **Step 1: Add or tighten verification regression assertions if needed**

Cover:
- exactly one of `captcha_code` or `otp`
- component test flow still uses `verification_response.json`
- formal collection flow still resumes through Redis and paused-task semantics
- Miaoshou login still raises graphical captcha in the shared format

- [ ] **Step 2: Run verification regressions**

Run:

```bash
pytest backend/tests/test_component_tester_verification_flow.py backend/tests/test_collection_verification_flow.py backend/tests/test_collection_multi_account_verification_contract.py -q
```

Expected: PASS

- [ ] **Step 3: Commit if any test-only adjustments were needed**

```bash
git add backend/tests/test_component_tester_verification_flow.py backend/tests/test_collection_verification_flow.py backend/tests/test_collection_multi_account_verification_contract.py
git commit -m "test: preserve shared verification recovery during miaoshou login migration"
```

### Task 5: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run the focused login regression set**

Run:

```bash
pytest backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_login_v2_contract.py backend/tests/test_component_tester_verification_flow.py backend/tests/test_collection_verification_flow.py backend/tests/test_collection_multi_account_verification_contract.py -q
```

Expected: PASS

- [ ] **Step 2: Syntax-check touched Python files**

Run:

```bash
python -m py_compile modules/platforms/miaoshou/components/login.py modules/platforms/miaoshou/components/miaoshou_login.py modules/platforms/miaoshou/components/login_v1_0_3.py
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: verify miaoshou login v2 migration"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-27-miaoshou-login-v2-migration.md`. Ready to execute?
