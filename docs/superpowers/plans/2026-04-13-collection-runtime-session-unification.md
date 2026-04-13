# Collection Runtime Session Unification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make formal collection tasks and component tests share one canonical runtime session model so sequential collection runs directly on persistent account profiles and parallel collection uses persistent-profile login plus `storage_state` fan-out.

**Architecture:** Introduce a shared runtime session layer that owns session-scope resolution, fingerprint-backed context creation, login-gate probing, profile-first runtime opening, and post-login session persistence. Refactor the collection executor and component tester to consume that layer instead of maintaining separate session orchestration code paths.

**Tech Stack:** Python, Playwright async runtime, existing `SessionManager` and `DeviceFingerprintManager`, collection executor V2, component tester, pytest, @test-driven-development, @verification-before-completion.

---

## File Map

- `modules/apps/collection_center/runtime_session.py`
  Responsibility: canonical runtime session orchestration shared by collection and component-test flows.
- `modules/apps/collection_center/executor_v2.py`
  Responsibility: formal collection execution; must delegate session runtime ownership to `runtime_session.py`.
- `tools/test_component.py`
  Responsibility: component-test runtime; must stop maintaining a separate session orchestration layer and call `runtime_session.py`.
- `modules/utils/sessions/session_manager.py`
  Responsibility: session and persistent-profile paths; should remain authoritative and only receive narrow compatibility adjustments if needed.
- `backend/tests/test_collection_runtime_session.py`
  Responsibility: direct unit coverage for the new shared runtime session layer.
- `backend/tests/test_collection_executor_session_alignment.py`
  Responsibility: executor-level regression coverage for sequential and parallel runtime session behavior.
- `backend/tests/test_component_tester_session_alignment.py`
  Responsibility: component-tester regression coverage proving it now uses the shared runtime session layer.
- `docs/superpowers/specs/2026-04-13-collection-runtime-session-unification-design.md`
  Responsibility: approved architecture reference for the refactor.

### Task 1: Lock In the Shared Runtime Session Contract

**Files:**
- Create: `backend/tests/test_collection_runtime_session.py`
- Create: `backend/tests/test_collection_executor_session_alignment.py`
- Create: `backend/tests/test_component_tester_session_alignment.py`

- [ ] **Step 1: Write failing tests for the shared sequential runtime**

Add tests proving:
- sequential runtime opens a persistent profile when a session owner exists
- login is skipped when the login gate is already ready
- login runs when the gate is not ready
- refreshed session is persisted after successful login

- [ ] **Step 2: Run the shared-runtime tests to confirm failure**

Run: `python -m pytest backend/tests/test_collection_runtime_session.py -q`
Expected: FAIL because `runtime_session.py` does not exist yet

- [ ] **Step 3: Write failing executor alignment tests**

Add tests proving:
- sequential collection no longer treats `storage_state + new_context()` as the primary runtime path
- parallel collection still derives fan-out contexts only after a persistent-profile login phase

- [ ] **Step 4: Run the executor alignment tests to confirm failure**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: FAIL for the new runtime-path expectations

- [ ] **Step 5: Write failing component tester alignment tests**

Add tests proving:
- component tester delegates session-runtime orchestration to the shared module
- component tester no longer owns a divergent session runtime path

- [ ] **Step 6: Run the component tester alignment tests to confirm failure**

Run: `python -m pytest backend/tests/test_component_tester_session_alignment.py -q`
Expected: FAIL for the new delegation expectations

- [ ] **Step 7: Commit the failing-test baseline**

```bash
git add backend/tests/test_collection_runtime_session.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_component_tester_session_alignment.py
git commit -m "test: add collection runtime session unification cases"
```

### Task 2: Implement the Shared Runtime Session Layer

**Files:**
- Create: `modules/apps/collection_center/runtime_session.py`
- Modify: `modules/utils/sessions/session_manager.py` only if a narrow helper is required
- Test: `backend/tests/test_collection_runtime_session.py`

- [ ] **Step 1: Implement session-scope and context-opening helpers**

Add explicit helpers for:
- session owner resolution
- fingerprint-backed Playwright context option building
- persistent profile opening with `launch_persistent_context(...)`
- `storage_state`-backed `new_context(...)` opening
- post-login session snapshot persistence

- [ ] **Step 2: Implement login-gate-aware runtime preparation**

Add helpers that:
- open the runtime page
- probe login readiness
- run login only when the gate is not ready
- return a runtime bundle with page, context, mode, and refreshed-session metadata

- [ ] **Step 3: Keep `storage_state` support as an explicit derived path**

Implement helpers that snapshot live `storage_state` from a persistent runtime for later parallel fan-out, instead of treating it as the primary runtime by default.

- [ ] **Step 4: Run the shared-runtime tests**

Run: `python -m pytest backend/tests/test_collection_runtime_session.py -q`
Expected: PASS

- [ ] **Step 5: Commit the shared runtime layer**

```bash
git add modules/apps/collection_center/runtime_session.py modules/utils/sessions/session_manager.py backend/tests/test_collection_runtime_session.py
git commit -m "refactor: add shared collection runtime session layer"
```

### Task 3: Switch Sequential Collection to Profile-First Runtime

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_executor_session_alignment.py`
- Test: existing executor session-related tests under `backend/tests/`

- [ ] **Step 1: Replace sequential runtime bootstrap logic with shared runtime calls**

Update the sequential collection path so it:
- requests a persistent-profile runtime bundle from `runtime_session.py`
- probes login gate before login
- keeps login, navigation, date-picker, and export on the same runtime context

- [ ] **Step 2: Remove primary-path dependence on `storage_state + new_context()` for sequential execution**

Retain compatibility helpers only where still needed for fallback or fan-out, but do not let them remain the default sequential path.

- [ ] **Step 3: Run executor alignment tests**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: PASS

- [ ] **Step 4: Run targeted existing executor tests**

Run:
- `python -m pytest backend/tests/test_collection_executor_headful_fallback.py -q`
- `python -m pytest tests/test_executor_v2.py -q`

Expected:
- all targeted executor tests pass or any expectation changes are clearly isolated to the new runtime model

- [ ] **Step 5: Commit the sequential runtime switch**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_executor_headful_fallback.py tests/test_executor_v2.py
git commit -m "refactor: switch sequential collection to profile-first runtime"
```

### Task 4: Refactor Parallel Collection to Login via Profile Before Fan-Out

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_executor_session_alignment.py`

- [ ] **Step 1: Write or extend failing parallel-runtime cases**

Add tests proving:
- parallel collection performs login preparation in a persistent profile runtime
- fresh `storage_state` is captured only after login-gate readiness
- per-domain contexts fan out from the refreshed session snapshot

- [ ] **Step 2: Run the parallel-runtime tests to confirm failure**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: FAIL for the new fan-out sequencing cases

- [ ] **Step 3: Implement persistent-profile login plus `storage_state` fan-out**

Update the parallel path so it:
- opens a shared persistent runtime for login readiness
- performs login in that runtime when needed
- snapshots fresh `storage_state`
- closes the shared profile runtime before domain fan-out
- creates per-domain contexts with the refreshed session snapshot

- [ ] **Step 4: Re-run the executor alignment tests**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: PASS

- [ ] **Step 5: Commit the parallel runtime refactor**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "refactor: align parallel collection session fan-out"
```

### Task 5: Make Component Tester Consume the Shared Runtime Layer

**Files:**
- Modify: `tools/test_component.py`
- Test: `backend/tests/test_component_tester_session_alignment.py`
- Test: existing component tester gate/session tests under `backend/tests/`

- [ ] **Step 1: Replace duplicated session-runtime helpers with shared runtime calls**

Update the component tester to delegate:
- session owner resolution
- browser context opening
- login-gate preparation
- post-login session persistence

to `runtime_session.py`

- [ ] **Step 2: Preserve current stable tester behavior**

Ensure the tester still:
- reuses sessions when the gate is ready
- auto-logins when the gate is not ready
- persists refreshed session state after successful login

- [ ] **Step 3: Run the component tester alignment tests**

Run: `python -m pytest backend/tests/test_component_tester_session_alignment.py -q`
Expected: PASS

- [ ] **Step 4: Run targeted existing component tester tests**

Run:
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
- `python -m pytest backend/tests/test_component_tester_account_loading.py -q`
- `python -m pytest backend/tests/test_inspector_recorder_auto_login.py -q`

Expected:
- current component tester session/gate behavior still passes under the shared runtime model

- [ ] **Step 5: Commit the component tester alignment**

```bash
git add tools/test_component.py backend/tests/test_component_tester_session_alignment.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_component_tester_account_loading.py backend/tests/test_inspector_recorder_auto_login.py
git commit -m "refactor: align component tester with shared runtime session"
```

### Task 6: Run the Full Targeted Verification Bundle

**Files:**
- Modify: `docs/superpowers/specs/2026-04-13-collection-runtime-session-unification-design.md` only if implementation reality requires a documented correction
- Modify: `docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md` to check off completed tasks if execution happens in-plan

- [ ] **Step 1: Run the shared-runtime verification bundle**

Run:
- `python -m pytest backend/tests/test_collection_runtime_session.py -q`
- `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
- `python -m pytest backend/tests/test_component_tester_session_alignment.py -q`
- `python -m pytest backend/tests/test_collection_executor_headful_fallback.py -q`
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
- `python -m pytest backend/tests/test_inspector_recorder_auto_login.py -q`
- `python -m pytest tests/test_executor_v2.py -q`

Expected:
- all targeted session/runtime tests pass

- [ ] **Step 2: Review scope discipline**

Run: `git diff -- modules/apps/collection_center tools/test_component.py modules/utils/sessions backend/tests docs/superpowers/specs/2026-04-13-collection-runtime-session-unification-design.md docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md`
Expected: changes are limited to runtime session orchestration, session helpers, and associated tests; business component logic is not broadly rewritten

- [ ] **Step 3: Record final implementation commit**

```bash
git add modules/apps/collection_center tools/test_component.py modules/utils/sessions backend/tests docs/superpowers/specs/2026-04-13-collection-runtime-session-unification-design.md docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md
git commit -m "refactor: unify collection runtime session model"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md`. Ready to execute?
