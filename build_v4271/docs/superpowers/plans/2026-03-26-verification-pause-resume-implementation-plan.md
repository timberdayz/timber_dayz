# Verification Pause Resume Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified verification pause/resume protocol across recorder, component testing, and collection execution so captcha and OTP recovery always pause, surface UI, accept input, and resume the same execution context.

**Architecture:** Introduce a shared verification state/payload service first, then connect recorder, tester, and collection task flows to that contract one by one. Keep captcha solving out of scope; this project only standardizes pause, input, retry, and result handling.

**Tech Stack:** FastAPI, Pydantic, Vue 3, Element Plus, Playwright async, pytest

---

### Task 1: Define the shared verification contract

**Files:**
- Create: `backend/schemas/verification.py`
- Create: `backend/services/verification_state_store.py`
- Create: `backend/services/verification_service.py`
- Test: `backend/tests/test_verification_service_contract.py`

- [ ] **Step 1: Write a failing contract test for the shared payload shape**

```python
def test_verification_payload_contains_owner_and_expiry():
    ...
    assert payload["owner_type"] == "recorder"
```

- [ ] **Step 2: Run the new contract test and verify it fails**

Run: `python -m pytest backend/tests/test_verification_service_contract.py -q`
Expected: FAIL because shared verification schemas/services do not exist

- [ ] **Step 3: Add Pydantic schemas for verification state and resume request**

```python
class VerificationResumeRequest(BaseModel):
    ...
```

- [ ] **Step 4: Add minimal state store and service implementation**

```python
class VerificationService:
    ...
```

- [ ] **Step 5: Run the contract test and verify it passes**

Run: `python -m pytest backend/tests/test_verification_service_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/schemas/verification.py backend/services/verification_state_store.py backend/services/verification_service.py backend/tests/test_verification_service_contract.py
git commit -m "feat: add shared verification pause resume contract"
```

### Task 2: Connect recorder flow to the shared verification protocol

**Files:**
- Modify: `tools/launch_inspector_recorder.py`
- Modify: `backend/routers/component_recorder.py`
- Modify: `frontend/src/views/ComponentRecorder.vue`
- Create: `frontend/src/components/verification/VerificationResumeDialog.vue`
- Test: `backend/tests/test_component_recorder_gate_contract.py`

- [ ] **Step 1: Write a failing recorder test for shared verification payload reuse**

```python
async def test_recorder_resume_uses_shared_verification_request():
    ...
```

- [ ] **Step 2: Run recorder tests and verify failure**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py -q`
Expected: FAIL

- [ ] **Step 3: Replace recorder-specific ad hoc payload writing with shared verification service**

```python
verification_service.raise_required(...)
```

- [ ] **Step 4: Replace inline recorder captcha UI with shared dialog component**

```vue
<VerificationResumeDialog ... />
```

- [ ] **Step 5: Run recorder tests and frontend build**

Run: `python -m pytest backend/tests/test_component_recorder_gate_contract.py -q`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/launch_inspector_recorder.py backend/routers/component_recorder.py frontend/src/views/ComponentRecorder.vue frontend/src/components/verification/VerificationResumeDialog.vue backend/tests/test_component_recorder_gate_contract.py
git commit -m "feat: unify recorder verification pause resume flow"
```

### Task 3: Connect component testing flow

**Files:**
- Modify: `tools/test_component.py`
- Modify: `backend/routers/component_versions.py`
- Test: `backend/tests/test_component_tester_gate_contract.py`
- Test: `backend/tests/test_component_tester_verification_flow.py`

- [ ] **Step 1: Write a failing tester verification flow test**

```python
async def test_component_tester_enters_verification_required_state():
    ...
```

- [ ] **Step 2: Run tester tests and verify failure**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py backend/tests/test_component_tester_verification_flow.py -q`
Expected: FAIL

- [ ] **Step 3: Route tester verification status and resume through shared verification service**

```python
verification_service.raise_required(...)
```

- [ ] **Step 4: Add/adjust test-status and resume endpoints to carry shared fields**

```python
POST /component-versions/test-resume/{id}
```

- [ ] **Step 5: Run tester tests**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py backend/tests/test_component_tester_verification_flow.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/test_component.py backend/routers/component_versions.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_component_tester_verification_flow.py
git commit -m "feat: unify component test verification pause resume flow"
```

### Task 4: Connect production collection flow

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: task-detail/task-center frontend views
- Test: `backend/tests/test_collection_verification_flow.py`

- [ ] **Step 1: Write a failing collection verification flow test**

```python
async def test_collection_task_enters_verification_required_state():
    ...
```

- [ ] **Step 2: Run collection verification tests and verify failure**

Run: `python -m pytest backend/tests/test_collection_verification_flow.py -q`
Expected: FAIL

- [ ] **Step 3: Integrate executor pause/resume with shared verification service**

```python
verification_service.raise_required(...)
```

- [ ] **Step 4: Expose task status/resume endpoints with shared verification fields**

```python
POST /collection/tasks/{id}/resume
```

- [ ] **Step 5: Run collection verification tests**

Run: `python -m pytest backend/tests/test_collection_verification_flow.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/tests/test_collection_verification_flow.py
git commit -m "feat: unify collection task verification pause resume flow"
```

### Task 5: Add multi-account task verification presentation

**Files:**
- Modify: task center/detail frontend views
- Modify: task status payload serializers if needed
- Test: `backend/tests/test_collection_multi_account_verification_contract.py`

- [ ] **Step 1: Write a failing multi-account verification contract test**

```python
def test_multi_account_verification_items_are_scoped_per_account():
    ...
```

- [ ] **Step 2: Run the contract test and verify failure**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py -q`
Expected: FAIL

- [ ] **Step 3: Add per-account verification item projection**

```python
{"task_id": ..., "account_id": ..., "verification_id": ...}
```

- [ ] **Step 4: Render per-account pending verification items in task UI**

```vue
<VerificationResumeDialog ... />
```

- [ ] **Step 5: Run tests and frontend build**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py -q`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_collection_multi_account_verification_contract.py ...
git commit -m "feat: surface multi-account verification items in task ui"
```
