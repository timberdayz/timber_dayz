# Recorder Segment Validation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live recorder step syncing and a recorder-page “validate current segment” flow that replays a selected contiguous step range in an isolated browser context and checks an explicit ready signal.

**Architecture:** Extend the existing recorder pipeline instead of creating a parallel one. Keep live recording in the current Inspector path, add incremental `steps_file` sync for in-progress visibility, then add a new recorder segment validator service and route that reuse existing gate semantics from tester/runtime.

**Tech Stack:** FastAPI, Pydantic, Playwright async, Vue 3, Element Plus, pytest

---

### Task 1: Lock the backend contract for live recorder steps and segment validation

**Files:**
- Modify: `backend/tests/test_component_recorder_gate_contract.py`
- Create: `backend/tests/test_recorder_segment_validator.py`
- Modify: `backend/schemas/component_recorder.py`

- [ ] **Step 1: Write a failing contract test for live `/recorder/steps` file-backed reads**

```python
async def test_get_recording_steps_reads_latest_steps_file_when_recording_active(tmp_path):
    ...
    assert body["data"]["steps"][0]["action"] == "click"
```

- [ ] **Step 2: Run the targeted recorder gate tests and verify the new test fails**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py -q`
Expected: FAIL because `/recorder/steps` still prefers in-memory session steps

- [ ] **Step 3: Write a failing validator contract test for contiguous segment validation**

```python
def test_validate_segment_rejects_non_contiguous_selection():
    ...
    assert response["success"] is False
```

- [ ] **Step 4: Write a failing validator test for auto signal resolution**

```python
def test_resolve_expected_signal_prefers_step_group_before_component_type():
    ...
    assert resolved == "navigation_ready"
```

- [ ] **Step 5: Run the new validator test file and verify both tests fail**

Run: `python -m pytest backend/tests/test_recorder_segment_validator.py -q`
Expected: FAIL because validator service and schemas do not exist yet

- [ ] **Step 6: Add request/response schema stubs in `backend/schemas/component_recorder.py`**

```python
class RecorderValidateSegmentRequest(BaseModel):
    ...
```

- [ ] **Step 7: Commit the red-phase test and schema setup**

```bash
git add backend/tests/test_component_recorder_gate_contract.py backend/tests/test_recorder_segment_validator.py backend/schemas/component_recorder.py
git commit -m "test: lock recorder segment validation contracts"
```

### Task 2: Implement live recorder step syncing from `steps_file`

**Files:**
- Modify: `tools/launch_inspector_recorder.py`
- Modify: `backend/routers/component_recorder.py`
- Test: `backend/tests/test_component_recorder_gate_contract.py`

- [ ] **Step 1: Add a helper that incrementally writes the latest step payload whenever recorder state changes**

```python
def _persist_live_steps(self) -> None:
    ...
```

- [ ] **Step 2: Call the helper after each meaningful step mutation in normal and discovery modes**

```python
self.recorded_steps.append(step)
self._persist_live_steps()
```

- [ ] **Step 3: Update `/recorder/steps` to read the latest `steps_file` when the recorder session is active**

```python
live_data = _parse_inspector_output()
```

- [ ] **Step 4: Run the recorder gate tests and verify the new live-step test passes**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit the live sync work**

```bash
git add tools/launch_inspector_recorder.py backend/routers/component_recorder.py backend/tests/test_component_recorder_gate_contract.py
git commit -m "feat: stream live recorder steps from inspector output"
```

### Task 3: Build the segment validator service and route

**Files:**
- Create: `backend/services/recorder_segment_validator.py`
- Modify: `backend/routers/component_recorder.py`
- Modify: `backend/schemas/component_recorder.py`
- Test: `backend/tests/test_recorder_segment_validator.py`

- [ ] **Step 1: Implement a minimal validator object with explicit signal resolution and contiguous-range validation**

```python
class RecorderSegmentValidator:
    def resolve_expected_signal(...): ...
    def validate_selected_range(...): ...
```

- [ ] **Step 2: Add a failing test for structured export gate failure**

```python
def test_export_complete_failure_returns_structured_result():
    ...
    assert result["error_message"] == "download file missing"
```

- [ ] **Step 3: Run the validator tests and verify the new export failure test fails**

Run: `python -m pytest backend/tests/test_recorder_segment_validator.py -q`
Expected: FAIL because export-complete failure path is not implemented yet

- [ ] **Step 4: Implement isolated-context replay with minimal supported actions**

```python
async def replay_segment(...):
    ...
```

- [ ] **Step 5: Reuse existing gate semantics for `login_ready` and `export_complete`**

```python
evaluate_login_ready(...)
evaluate_export_complete(...)
```

- [ ] **Step 6: Add `POST /recorder/validate-segment` in `backend/routers/component_recorder.py`**

```python
@router.post("/recorder/validate-segment")
async def validate_segment(...):
    ...
```

- [ ] **Step 7: Run the validator tests and targeted recorder router tests**

Run: `python -m pytest backend/tests/test_recorder_segment_validator.py backend/tests/test_component_recorder_gate_contract.py -q`
Expected: PASS

- [ ] **Step 8: Commit the validator backend**

```bash
git add backend/services/recorder_segment_validator.py backend/routers/component_recorder.py backend/schemas/component_recorder.py backend/tests/test_recorder_segment_validator.py
git commit -m "feat: add recorder segment validation backend"
```

### Task 4: Add recorder page segment validation UI

**Files:**
- Modify: `frontend/src/views/ComponentRecorder.vue`

- [ ] **Step 1: Add client-side contiguous selection checks and validation state**

```javascript
const validationState = ref(...)
```

- [ ] **Step 2: Add expected-signal selector and `校验当前段` button to the existing step toolbar**

```vue
<el-button @click="validateSelectedSegment">校验当前段</el-button>
```

- [ ] **Step 3: Implement the API call using the selected contiguous step slice**

```javascript
await api.post("/collection/recorder/validate-segment", payload)
```

- [ ] **Step 4: Render a validation result panel with pass/fail, resolved signal, URL, failure step, screenshot, and suggestions**

```vue
<el-alert v-if="segmentValidationResult" ... />
```

- [ ] **Step 5: Run the frontend build or targeted lint check**

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: Commit the recorder UI work**

```bash
git add frontend/src/views/ComponentRecorder.vue
git commit -m "feat: validate recorder step segments from the recorder page"
```

### Task 5: Verify end-to-end recorder validation behavior

**Files:**
- Verify: `backend/tests/test_component_recorder_gate_contract.py`
- Verify: `backend/tests/test_recorder_segment_validator.py`
- Verify: `backend/tests/test_component_tester_gate_contract.py`
- Verify: `frontend/src/views/ComponentRecorder.vue`

- [ ] **Step 1: Run the consolidated backend test set**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py backend/tests/test_component_recorder_lint.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_recorder_segment_validator.py -q`
Expected: PASS

- [ ] **Step 2: Run the frontend build one more time**

Run: `npm run build`
Expected: PASS

- [ ] **Step 3: Manually verify the recorder flow in the UI**

```text
Start recording -> observe live steps -> select contiguous range -> click 校验当前段 -> inspect result panel
```

- [ ] **Step 4: Record residual risks if manual verification cannot be completed locally**

```text
Document missing browser/manual evidence explicitly in the final summary
```

- [ ] **Step 5: Commit verification-only updates if any were needed**

```bash
git add ...
git commit -m "test: verify recorder segment validation flow"
```
