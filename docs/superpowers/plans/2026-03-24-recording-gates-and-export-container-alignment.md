# Recording Gates And Export Container Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify recorder, component tester, and runtime execution around one login gate and one export-completion contract while keeping `export` as the self-contained container component.

**Architecture:** Introduce shared transition-gate helpers for login readiness and export completion, then route recorder, tester, and runtime through those helpers instead of each layer re-implementing transition logic. Preserve recorder step tagging, but treat tags as metadata inside the export container rather than as a competing top-level execution model.

**Tech Stack:** Python, FastAPI, Playwright async, Vue 3, Element Plus, pytest

---

## File Structure

### New Files

- `modules/apps/collection_center/transition_gates.py`
  - Shared gate primitives for:
    - `login_ready`
    - `export_complete`
  - Shared result shape used by recorder/test/runtime

- `backend/tests/test_transition_gates.py`
  - Unit coverage for shared gate rules and result interpretation

- `backend/tests/test_component_recorder_gate_contract.py`
  - Recorder API/status contract coverage

- `backend/tests/test_component_tester_gate_contract.py`
  - Component tester gate and export-complete coverage

### Existing Files To Modify

- `tools/launch_inspector_recorder.py`
  - Keep current partial Python-login fix
  - Refactor recorder pre-login to use shared gate helpers
  - Block Inspector until `login_ready`

- `backend/routers/component_recorder.py`
  - Make recorder start/status contract truthful about gate progress
  - Stop implying “ready to record” when only subprocess startup has happened

- `backend/schemas/component_recorder.py`
  - Extend recorder contract models to carry gate/status semantics

- `frontend/src/views/ComponentRecorder.vue`
  - Reflect recorder gate states in UI
  - Show “checking login / waiting verification / ready to record / failed before recording”

- `tools/test_component.py`
  - Align pre-login gating with recorder/runtime
  - Reuse export-complete helper instead of ad hoc success assumptions

- `modules/apps/collection_center/executor_v2.py`
  - Route runtime pre-login and export-complete checks through shared helpers

- `modules/platforms/miaoshou/components/miaoshou_login.py`
  - Preserve current active-session short-circuit
  - Adjust only if shared gate integration reveals remaining contract gaps

- `docs/guides/COMPONENT_COLLABORATION.md`
  - Update to state:
    - login is a gate
    - export is container
    - tagged substeps live inside export

- `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
  - Add mandatory completion-signal guidance for tagged substeps and export completion

- `docs/guides/COMPONENT_RECORDING_GUIDE.md`
  - Update recorder flow to require `login_ready` before Inspector

### Existing Partial Fixes To Preserve

- `tools/launch_inspector_recorder.py`
- `modules/platforms/miaoshou/components/miaoshou_login.py`
- `backend/tests/test_inspector_recorder_auto_login.py`

Do not revert these changes while implementing the plan. Build on them.

---

### Task 1: Shared Transition Gate Primitives

**Files:**
- Create: `modules/apps/collection_center/transition_gates.py`
- Test: `backend/tests/test_transition_gates.py`

- [ ] **Step 1: Write the failing tests for login-ready and export-complete primitives**

```python
from modules.apps.collection_center.transition_gates import (
    GateStatus,
    evaluate_login_ready,
    evaluate_export_complete,
)


def test_login_ready_requires_logged_in_status_and_threshold():
    result = evaluate_login_ready(
        status="logged_in",
        confidence=0.69,
        current_url="https://erp.91miaoshou.com/welcome",
        matched_signal="url+element",
    )
    assert result.status is GateStatus.FAILED


def test_export_complete_requires_existing_non_empty_file(tmp_path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"ok")
    result = evaluate_export_complete(file_path=str(target))
    assert result.status is GateStatus.READY
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_transition_gates.py -q`  
Expected: FAIL because `transition_gates.py` does not exist yet.

- [ ] **Step 3: Implement the shared gate module**

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class GateStatus(str, Enum):
    READY = "ready"
    PENDING_VERIFICATION = "pending_verification"
    FAILED = "failed"


@dataclass
class GateResult:
    stage: str
    status: GateStatus
    reason: str
    confidence: float = 0.0
    current_url: Optional[str] = None
    matched_signal: Optional[str] = None
    screenshot_path: Optional[str] = None


def evaluate_login_ready(*, status: str, confidence: float, current_url: str, matched_signal: Optional[str]) -> GateResult:
    if status == "logged_in" and confidence >= 0.7:
        return GateResult("login_gate", GateStatus.READY, "login confirmed", confidence, current_url, matched_signal)
    return GateResult("login_gate", GateStatus.FAILED, "login not confirmed", confidence, current_url, matched_signal)


def evaluate_export_complete(*, file_path: Optional[str]) -> GateResult:
    if not file_path:
        return GateResult("export", GateStatus.FAILED, "missing file path")
    target = Path(file_path)
    if not target.exists():
        return GateResult("export", GateStatus.FAILED, "download file missing")
    if target.stat().st_size <= 0:
        return GateResult("export", GateStatus.FAILED, "download file empty")
    return GateResult("export", GateStatus.READY, "download file confirmed", matched_signal="file_exists")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest backend/tests/test_transition_gates.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/transition_gates.py backend/tests/test_transition_gates.py
git commit -m "feat: add shared collection transition gates"
```

### Task 2: Recorder Gate Contract And Honest Status

**Files:**
- Modify: `tools/launch_inspector_recorder.py`
- Modify: `backend/routers/component_recorder.py`
- Modify: `backend/schemas/component_recorder.py`
- Test: `backend/tests/test_inspector_recorder_auto_login.py`
- Test: `backend/tests/test_component_recorder_gate_contract.py`

- [ ] **Step 1: Write the failing recorder contract tests**

```python
def test_start_recording_returns_starting_not_ready(client):
    response = client.post("/collection/recorder/start", json={
        "platform": "miaoshou",
        "component_type": "export",
        "account_id": "acc-1",
    })
    assert response.json()["data"]["state"] == "starting"


def test_recorder_status_can_report_failed_before_recording():
    status = build_recorder_status_payload(
        state="failed_before_recording",
        gate_stage="login_gate",
        ready_to_record=False,
    )
    assert status["ready_to_record"] is False
```

- [ ] **Step 2: Run the recorder contract tests to verify they fail**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py backend/tests/test_inspector_recorder_auto_login.py -q`  
Expected: FAIL because the recorder API/status payload does not yet expose the new states.

- [ ] **Step 3: Update recorder schema and router response model**

```python
class RecorderStartResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any]
```

Required payload fields:

- `state`
- `gate_stage`
- `ready_to_record`
- `session_id`
- `account`

Initial state after successful launch should be:

- `state="starting"`
- `gate_stage="login_gate"`
- `ready_to_record=False`

- [ ] **Step 4: Refactor `launch_inspector_recorder.py` to use shared `evaluate_login_ready()`**

Requirements:

- preserve the current canonical Python login execution path
- replace ad hoc post-login success check with `evaluate_login_ready()`
- if gate is not `READY`, raise and stop before `page.pause()`

- [ ] **Step 5: Add recorder-side status file/state propagation**

Add a small status file in recorder temp output to track:

- `starting`
- `login_checking`
- `login_verification_pending`
- `login_ready`
- `inspector_recording`
- `failed_before_recording`

The router status endpoint should read and expose this truthfully.

- [ ] **Step 6: Run the recorder-related tests to verify they pass**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py backend/tests/test_inspector_recorder_auto_login.py -q`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tools/launch_inspector_recorder.py backend/routers/component_recorder.py backend/schemas/component_recorder.py backend/tests/test_component_recorder_gate_contract.py backend/tests/test_inspector_recorder_auto_login.py
git commit -m "feat: make recorder login gate explicit"
```

### Task 3: Recorder UI State Alignment

**Files:**
- Modify: `frontend/src/views/ComponentRecorder.vue`

- [ ] **Step 1: Add a failing UI checklist in the plan and verify current UI assumptions**

Manual checklist:

- start export recording
- verify UI does not claim recording is active before login gate clears
- verify gate failures show a blocking message instead of “recording in progress”

- [ ] **Step 2: Implement recorder UI state mapping**

Update UI to display these states:

- `starting`
- `login_checking`
- `login_verification_pending`
- `login_ready`
- `inspector_recording`
- `failed_before_recording`

Required behavior:

- only show “正在录制” when `state == "inspector_recording"`
- show blocking warning/error when `failed_before_recording`
- show login verification waiting message when `login_verification_pending`

- [ ] **Step 3: Verify manually**

Run:

```bash
npm --prefix frontend run dev
```

Expected:

- recorder page state text follows backend state truthfully

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ComponentRecorder.vue
git commit -m "feat: align recorder ui with gate states"
```

### Task 4: Component Tester Gate Alignment

**Files:**
- Modify: `tools/test_component.py`
- Test: `backend/tests/test_component_tester_gate_contract.py`
- Test: `backend/tests/test_first_batch_login_contracts.py`

- [ ] **Step 1: Write failing tests for tester pre-login gate and export completion**

```python
def test_component_tester_blocks_export_until_login_ready():
    ...


def test_component_tester_marks_export_failed_without_downloaded_file():
    ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py backend/tests/test_first_batch_login_contracts.py -q`  
Expected: FAIL because tester still uses its own pre-login flow.

- [ ] **Step 3: Refactor tester to use shared gate helpers**

Requirements:

- before export test, run the same login gate semantics as recorder/runtime
- reuse `evaluate_login_ready()`
- treat export success as file-confirmed success via `evaluate_export_complete()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py backend/tests/test_first_batch_login_contracts.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/test_component.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_first_batch_login_contracts.py
git commit -m "feat: align component tester with transition gates"
```

### Task 5: Runtime Gate Alignment

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_miaoshou_export_contract.py`
- Test: `backend/tests/test_shopee_services_export_contract.py`
- Test: `backend/tests/test_tiktok_export_contract.py`

- [ ] **Step 1: Add a failing runtime contract test**

```python
def test_runtime_export_requires_login_ready_and_file_complete():
    ...
```

- [ ] **Step 2: Run the runtime-focused tests to verify failure**

Run: `python -m pytest backend/tests/test_miaoshou_export_contract.py backend/tests/test_shopee_services_export_contract.py backend/tests/test_tiktok_export_contract.py -q`  
Expected: at least one failure or missing contract coverage requiring runtime gate integration.

- [ ] **Step 3: Refactor runtime to use shared gate helpers**

Requirements:

- route pre-login confirmation through `evaluate_login_ready()`
- keep existing platform login components
- after export returns file path, route completion through `evaluate_export_complete()`
- if export returns success without valid file, treat as runtime failure

- [ ] **Step 4: Re-run runtime-focused tests**

Run: `python -m pytest backend/tests/test_miaoshou_export_contract.py backend/tests/test_shopee_services_export_contract.py backend/tests/test_tiktok_export_contract.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_miaoshou_export_contract.py backend/tests/test_shopee_services_export_contract.py backend/tests/test_tiktok_export_contract.py
git commit -m "feat: align runtime gates with recorder and tester"
```

### Task 6: Standards And Documentation Update

**Files:**
- Modify: `docs/guides/COMPONENT_COLLABORATION.md`
- Modify: `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
- Modify: `docs/guides/COMPONENT_RECORDING_GUIDE.md`
- Reference: `docs/superpowers/specs/2026-03-24-recording-gates-and-export-container-design.md`

- [ ] **Step 1: Update collaboration doc**

Add explicit statements:

- login is a gate
- export is a container
- tagged substeps are metadata inside export

- [ ] **Step 2: Update script-writing standard**

Add mandatory completion-signal rules for:

- `login_ready`
- `navigation_ready`
- `date_picker_ready`
- `filters_ready`
- `export_complete`

- [ ] **Step 3: Update recorder guide**

Document that export recording:

- does not start before login gate success
- pauses on verification
- fails before recording if login cannot be confirmed

- [ ] **Step 4: Review docs for contradictions**

Search:

```bash
git grep -n -I -E "login -> navigation -> date_picker|Inspector|录制|export.*container|login gate" -- docs
```

Expected:

- no remaining doc sections that contradict the new model

- [ ] **Step 5: Commit**

```bash
git add docs/guides/COMPONENT_COLLABORATION.md docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md docs/guides/COMPONENT_RECORDING_GUIDE.md
git commit -m "docs: standardize recording gates and export container model"
```

### Task 7: Final Verification

**Files:**
- Verify modified files in Tasks 1-6

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
python -m pytest \
  backend/tests/test_transition_gates.py \
  backend/tests/test_component_recorder_gate_contract.py \
  backend/tests/test_inspector_recorder_auto_login.py \
  backend/tests/test_component_tester_gate_contract.py \
  backend/tests/test_first_batch_login_contracts.py \
  backend/tests/test_miaoshou_login_component.py \
  backend/tests/test_miaoshou_export_contract.py \
  backend/tests/test_shopee_services_export_contract.py \
  backend/tests/test_tiktok_export_contract.py \
  -q
```

Expected: all pass

- [ ] **Step 2: Run syntax/build sanity checks**

Run:

```bash
python -m py_compile tools/launch_inspector_recorder.py tools/test_component.py modules/apps/collection_center/transition_gates.py modules/apps/collection_center/executor_v2.py
```

Expected: no output

- [ ] **Step 3: Run frontend build or targeted lint if available**

Run:

```bash
npm --prefix frontend run build
```

Expected: build succeeds

- [ ] **Step 4: Manual acceptance**

Verify:

1. Miaoshou export recording with invalid session does **not** enter Inspector until login gate clears.
2. Verification-required login pauses before recording and resumes correctly.
3. Export recording starts only after backend page is reached.
4. Export test/runtime only report success when a file is actually downloaded.

- [ ] **Step 5: Commit final integration changes**

```bash
git add .
git commit -m "feat: unify recording, tester, and runtime transition gates"
```

## Notes For The Implementer

- Preserve the current partial recorder fix already in this worktree.
- Do not reintroduce top-level `navigation/date_picker/filters` execution as the canonical runtime model.
- Favor small helper extraction over large rewrites.
- When adding recorder state files/status propagation, keep the payload minimal and truthful.
- Do not claim export success from button clicks, toasts, or modal disappearance alone.

