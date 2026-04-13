# Storage-State-First Formal Collection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make formal collection tasks default to the same `storage_state`-based session reuse model that component tests already use, while keeping `persistent_profile` only as a controlled bootstrap/fallback path.

**Architecture:** Introduce one shared runtime strategy layer that decides how a task opens browser state, how login-gate evidence is evaluated, and when fallback to `persistent_profile` is allowed. Refactor formal collection and component tests to consume that shared strategy so both paths produce the same login-reuse behavior and the same gate verdicts for the same page state.

**Tech Stack:** Python, Playwright async runtime, `runtime_session.py`, `executor_v2.py`, `tools/test_component.py`, pytest, existing `SessionManager`, existing `DeviceFingerprintManager`, @test-driven-development, @verification-before-completion.

---

## File Map

- Modify: `modules/apps/collection_center/runtime_session.py`
  Responsibility: become the single owner of runtime mode selection, fallback rules, gate evaluation, and post-login session persistence.
- Modify: `modules/apps/collection_center/executor_v2.py`
  Responsibility: stop hard-coding profile-first sequential collection; request a shared runtime strategy decision instead.
- Modify: `backend/routers/collection_tasks.py`
  Responsibility: stop forcing `session_runtime_mode="persistent_profile"` for formal collection entry points.
- Modify: `tools/test_component.py`
  Responsibility: consume the same runtime strategy decision used by formal collection instead of its own private default.
- Modify: `modules/utils/login_status_detector.py`
  Responsibility: expose structured login evidence that the runtime strategy can evaluate consistently across platforms.
- Modify: `modules/apps/collection_center/transition_gates.py`
  Responsibility: replace the single global confidence threshold with rule-based gate evaluation over structured evidence.
- Modify: `backend/tests/test_collection_runtime_session.py`
  Responsibility: cover runtime strategy selection, gate evidence evaluation, and fallback behavior.
- Modify: `backend/tests/test_collection_executor_session_alignment.py`
  Responsibility: prove formal sequential collection now prefers `storage_state`.
- Modify: `backend/tests/test_component_tester_runtime_config.py`
  Responsibility: prove component tester and formal collection use the same runtime strategy defaults.
- Create: `backend/tests/test_login_gate_strategy_contract.py`
  Responsibility: cover shared login-gate decision rules independent of platform business components.
- Modify: `docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md`
  Responsibility: mark the earlier profile-first direction as superseded by this plan when implementation starts.

## Task 1: Lock In the Desired Runtime Strategy With Failing Tests

**Files:**
- Modify: `backend/tests/test_collection_runtime_session.py`
- Modify: `backend/tests/test_collection_executor_session_alignment.py`
- Modify: `backend/tests/test_component_tester_runtime_config.py`
- Create: `backend/tests/test_login_gate_strategy_contract.py`

- [ ] **Step 1: Write a failing test for formal sequential collection defaulting to `storage_state-first`**

```python
@pytest.mark.asyncio
async def test_formal_sequential_runtime_prefers_storage_state_when_available(monkeypatch):
    decision = choose_runtime_strategy(
        platform="miaoshou",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        component_type="export",
        execution_kind="formal_collection",
        parallel_mode=False,
    )

    assert decision.mode == "storage_state_fanout"
    assert decision.reason == "storage_state_available"
```

- [ ] **Step 2: Run the runtime-session tests to verify failure**

Run: `python -m pytest backend/tests/test_collection_runtime_session.py -q`
Expected: FAIL because the shared strategy selector does not exist and current behavior still assumes profile-first.

- [ ] **Step 3: Write a failing executor alignment test proving formal collection no longer hard-codes `persistent_profile`**

```python
@pytest.mark.asyncio
async def test_executor_requests_shared_runtime_strategy_for_sequential_collection(monkeypatch):
    open_runtime = AsyncMock()
    choose_strategy = AsyncMock(return_value=SimpleNamespace(mode="storage_state_fanout"))

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.choose_runtime_strategy",
        choose_strategy,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.CollectionExecutorV2._open_runtime_bundle",
        open_runtime,
    )

    # invoke execute(...)
    choose_strategy.assert_awaited()
```

- [ ] **Step 4: Run the executor alignment tests to verify failure**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: FAIL because executor still routes sequential formal collection through `persistent_profile`.

- [ ] **Step 5: Write a failing tester/runtime config test proving formal collection and component tests share one default**

```python
def test_component_tester_and_formal_collection_share_storage_state_first_default():
    decision = choose_runtime_strategy(
        platform="shopee",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        component_type="export",
        execution_kind="component_test",
        parallel_mode=False,
    )

    assert decision.mode == "storage_state_fanout"
```

- [ ] **Step 6: Write failing login-gate strategy tests for structured evidence rules**

```python
def test_login_gate_accepts_cookie_backed_shell_when_no_login_form_visible():
    evidence = LoginGateEvidence(
        detector_status="logged_in",
        detector_confidence=0.65,
        auth_cookies_present=True,
        login_form_visible=False,
        logged_in_markers_present=False,
        current_url="https://erp.91miaoshou.com/",
    )

    result = evaluate_login_gate_evidence(platform="miaoshou", evidence=evidence)

    assert result.status is GateStatus.READY
```

- [ ] **Step 7: Run the new gate strategy tests to verify failure**

Run: `python -m pytest backend/tests/test_login_gate_strategy_contract.py -q`
Expected: FAIL because current gate evaluation still uses a single confidence threshold.

- [ ] **Step 8: Commit the failing-test baseline**

```bash
git add backend/tests/test_collection_runtime_session.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_login_gate_strategy_contract.py
git commit -m "test: add storage-state-first runtime strategy cases"
```

## Task 2: Add a Shared Runtime Strategy and Structured Gate Evidence

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py`
- Modify: `modules/utils/login_status_detector.py`
- Modify: `modules/apps/collection_center/transition_gates.py`
- Modify: `backend/tests/test_collection_runtime_session.py`
- Create: `backend/tests/test_login_gate_strategy_contract.py`

- [ ] **Step 1: Add a runtime strategy decision type**

```python
@dataclass
class RuntimeStrategyDecision:
    mode: str
    reason: str
    used_storage_state: bool
    used_persistent_profile: bool
    fallback_allowed: bool
```

- [ ] **Step 2: Add a shared strategy selector to `runtime_session.py`**

```python
def choose_runtime_strategy(
    *,
    platform: str,
    session_owner_id: str | None,
    has_storage_state: bool,
    has_persistent_profile: bool,
    force_persistent_profile: bool,
    execution_kind: str,
    component_type: str | None,
    parallel_mode: bool,
) -> RuntimeStrategyDecision:
    if force_persistent_profile:
        return RuntimeStrategyDecision("persistent_profile", "forced", False, True, False)
    if parallel_mode:
        return RuntimeStrategyDecision("persistent_profile", "parallel_bootstrap", False, True, True)
    if has_storage_state:
        return RuntimeStrategyDecision("storage_state_fanout", "storage_state_available", True, False, True)
    if has_persistent_profile:
        return RuntimeStrategyDecision("persistent_profile", "storage_state_missing", False, True, True)
    return RuntimeStrategyDecision("storage_state_fanout", "fresh_login_required", False, False, True)
```

- [ ] **Step 3: Extend `LoginDetectionResult` or add a normalized evidence object**

```python
@dataclass
class LoginGateEvidence:
    detector_status: str
    detector_confidence: float
    auth_cookies_present: bool
    login_form_visible: bool
    logged_in_markers_present: bool
    current_url: str
    matched_signal: str | None = None
```

- [ ] **Step 4: Replace threshold-only gate evaluation with rule-based evidence evaluation**

```python
def evaluate_login_gate_evidence(*, platform: str, evidence: LoginGateEvidence) -> GateResult:
    if evidence.login_form_visible:
        return GateResult(stage="login_gate", status=GateStatus.FAILED, reason="login form visible")
    if evidence.logged_in_markers_present:
        return GateResult(stage="login_gate", status=GateStatus.READY, reason="logged-in markers confirmed")
    if evidence.auth_cookies_present and evidence.detector_status == "logged_in":
        return GateResult(stage="login_gate", status=GateStatus.READY, reason="cookie-backed session confirmed")
    if evidence.detector_status == "logged_in" and evidence.detector_confidence >= 0.7:
        return GateResult(stage="login_gate", status=GateStatus.READY, reason="login confirmed")
    return GateResult(stage="login_gate", status=GateStatus.FAILED, reason="login not confirmed")
```

- [ ] **Step 5: Run the runtime-session and gate strategy tests**

Run:
- `python -m pytest backend/tests/test_collection_runtime_session.py -q`
- `python -m pytest backend/tests/test_login_gate_strategy_contract.py -q`

Expected: PASS

- [ ] **Step 6: Commit the shared strategy layer**

```bash
git add modules/apps/collection_center/runtime_session.py modules/utils/login_status_detector.py modules/apps/collection_center/transition_gates.py backend/tests/test_collection_runtime_session.py backend/tests/test_login_gate_strategy_contract.py
git commit -m "refactor: add storage-state-first runtime strategy"
```

## Task 3: Switch Formal Sequential Collection to Storage-State-First

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/tests/test_collection_executor_session_alignment.py`

- [ ] **Step 1: Remove hard-coded profile-first mode from formal collection entry points**

```python
result = await executor.execute(
    ...,
    session_runtime_mode="auto",
)
```

- [ ] **Step 2: Make executor resolve the runtime strategy at execution time**

```python
decision = runtime_session.choose_runtime_strategy(
    platform=platform,
    session_owner_id=session_owner_id,
    has_storage_state=bool(await runtime_session.load_runtime_storage_state(...)),
    has_persistent_profile=runtime_session.runtime_profile_exists(...),
    force_persistent_profile=False,
    execution_kind="formal_collection",
    component_type="export",
    parallel_mode=False,
)
runtime_bundle = await self._open_runtime_bundle(
    session_runtime_mode=decision.mode,
    ...,
)
```

- [ ] **Step 3: Preserve login success persistence back into `storage_state`**

```python
storage_state = await runtime_session.snapshot_runtime_storage_state(
    platform=platform,
    session_owner_id=session_owner_id,
    context=play_context,
    persist=True,
)
```

- [ ] **Step 4: Keep fallback to `persistent_profile` only when strategy says so**

```python
if decision.mode == "storage_state_fanout" and gate_not_ready and decision.fallback_allowed:
    # optional fallback only after primary path fails
```

- [ ] **Step 5: Run executor alignment tests**

Run: `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
Expected: PASS

- [ ] **Step 6: Run targeted collection runtime tests**

Run:
- `python -m pytest backend/tests/test_collection_runtime_session.py -q`
- `python -m pytest backend/tests/test_collection_executor_headful_fallback.py -q`
- `python -m pytest tests/test_executor_v2.py -q`

Expected: PASS, or any failures are limited to old profile-first assumptions and updated explicitly.

- [ ] **Step 7: Commit the formal collection switch**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_executor_headful_fallback.py tests/test_executor_v2.py
git commit -m "refactor: switch formal collection to storage-state-first"
```

## Task 4: Align Component Tests With the Shared Runtime Strategy

**Files:**
- Modify: `tools/test_component.py`
- Modify: `backend/tests/test_component_tester_runtime_config.py`

- [ ] **Step 1: Remove the tester-only session strategy assumption**

```python
decision = choose_runtime_strategy(
    platform=self.platform,
    session_owner_id=session_owner_id,
    has_storage_state=bool(storage_state),
    has_persistent_profile=bool(session_owner_id),
    force_persistent_profile=False,
    execution_kind="component_test",
    component_type=component_type,
    parallel_mode=False,
)
```

- [ ] **Step 2: Route the tester through the same bundle opener used by formal collection**

```python
runtime_bundle = await open_runtime_bundle_for_strategy(
    browser=browser,
    browser_type=browser_type,
    decision=decision,
    ...,
)
```

- [ ] **Step 3: Keep current tester behavior intact**

```python
if not login_gate_ready:
    login_ok, context, page = await self._run_login_before_non_login(...)
```

- [ ] **Step 4: Run the tester runtime config tests**

Run: `python -m pytest backend/tests/test_component_tester_runtime_config.py -q`
Expected: PASS

- [ ] **Step 5: Run targeted existing tester/session tests**

Run:
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
- `python -m pytest backend/tests/test_component_tester_verification_flow.py -q`
- `python -m pytest backend/tests/test_inspector_recorder_auto_login.py -q`

Expected: PASS

- [ ] **Step 6: Commit tester alignment**

```bash
git add tools/test_component.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_component_tester_verification_flow.py backend/tests/test_inspector_recorder_auto_login.py
git commit -m "refactor: align component tester runtime strategy"
```

## Task 5: Add Fallback Telemetry and Operator-Facing Diagnostics

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/tests/test_collection_task_runtime_metadata.py`

- [ ] **Step 1: Record runtime strategy diagnostics in task metadata**

```python
details = {
    "runtime_session_mode": decision.mode,
    "runtime_strategy_reason": decision.reason,
    "session_source": "storage_state" if decision.used_storage_state else "persistent_profile",
    "fallback_allowed": decision.fallback_allowed,
}
```

- [ ] **Step 2: Record when fallback actually happens**

```python
details["runtime_fallback_triggered"] = True
details["runtime_fallback_reason"] = "login_gate_not_ready_after_storage_state"
```

- [ ] **Step 3: Run runtime metadata tests**

Run: `python -m pytest backend/tests/test_collection_task_runtime_metadata.py -q`
Expected: PASS

- [ ] **Step 4: Commit telemetry improvements**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/tests/test_collection_task_runtime_metadata.py
git commit -m "feat: expose collection runtime strategy diagnostics"
```

## Task 6: Final Verification and Plan Handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-04-13-collection-runtime-session-unification.md`
- Modify: `docs/superpowers/plans/2026-04-14-storage-state-first-formal-collection.md`

- [ ] **Step 1: Mark the older profile-first plan as superseded**

```markdown
> Superseded by `docs/superpowers/plans/2026-04-14-storage-state-first-formal-collection.md`.
```

- [ ] **Step 2: Run the focused verification bundle**

Run:
- `python -m pytest backend/tests/test_collection_runtime_session.py -q`
- `python -m pytest backend/tests/test_login_gate_strategy_contract.py -q`
- `python -m pytest backend/tests/test_collection_executor_session_alignment.py -q`
- `python -m pytest backend/tests/test_component_tester_runtime_config.py -q`
- `python -m pytest backend/tests/test_collection_task_runtime_metadata.py -q`
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
- `python -m pytest backend/tests/test_component_tester_verification_flow.py -q`
- `python -m pytest backend/tests/test_inspector_recorder_auto_login.py -q`
- `python -m pytest backend/tests/test_collection_executor_headful_fallback.py -q`
- `python -m pytest tests/test_executor_v2.py -q`

Expected: all targeted runtime/session tests pass.

- [ ] **Step 3: Review scope discipline**

Run: `git diff -- modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py tools/test_component.py modules/utils/login_status_detector.py modules/apps/collection_center/transition_gates.py backend/tests docs/superpowers/plans`
Expected: changes stay limited to runtime strategy, gate evaluation, diagnostics, and their tests.

- [ ] **Step 4: Record final implementation commit**

```bash
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py tools/test_component.py modules/utils/login_status_detector.py modules/apps/collection_center/transition_gates.py backend/tests docs/superpowers/plans
git commit -m "refactor: make formal collection storage-state-first"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-14-storage-state-first-formal-collection.md`. Ready to execute?
