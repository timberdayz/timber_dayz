# Collection Verification Workbench Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the collection task page into a stable multi-account verification workbench that separates pending human verification items from the raw task table while keeping the shared verification dialog and collection owner model intact.

**Architecture:** Add a dedicated collection verification-item projection on the backend, then upgrade the task page to consume that projection through a dedicated enhanced panel. Reuse the shared verification dialog and keep captcha image readability improvements inside that component instead of creating a separate page.

**Tech Stack:** FastAPI, Pydantic, Vue 3, Element Plus, pytest, Node test smoke scripts

---

### Task 1: Add collection verification item backend contract

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_multi_account_verification_contract.py`
- Test: `backend/tests/test_collection_verification_flow.py`

- [ ] **Step 1: Write or extend the failing contract test**

```python
def test_build_task_verification_item_is_scoped_per_account():
    ...
```

- [ ] **Step 2: Run contract tests and verify failure**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py backend/tests/test_collection_verification_flow.py -q`
Expected: FAIL if verification item projection or resume-state payload is incomplete

- [ ] **Step 3: Add/finish the task verification response projection**

Implement or tighten:
- `_build_task_response_payload(task)`
- `_build_task_verification_item(task)`

- [ ] **Step 4: Ensure resume response returns `verification_submitted`**

`resume_task()` should update the task status and return the projected payload.

- [ ] **Step 5: Run backend tests**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py backend/tests/test_collection_verification_flow.py -q`
Expected: PASS

---

### Task 2: Add dedicated verification-items aggregation endpoint

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_multi_account_verification_contract.py`

- [ ] **Step 1: Write a failing endpoint contract test**

```python
def test_list_collection_verification_items_filters_paused_verification_tasks():
    ...
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py -q`
Expected: FAIL because endpoint/schema do not exist yet

- [ ] **Step 3: Implement `GET /collection/tasks/verification-items`**

Support first-version filters:
- `platform`
- `verification_type`
- `account_id`
- `status`

- [ ] **Step 4: Re-run contract tests**

Run: `python -m pytest backend/tests/test_collection_multi_account_verification_contract.py -q`
Expected: PASS

---

### Task 3: Upgrade CollectionTasks workbench panel

**Files:**
- Modify: `frontend/src/views/CollectionTasks.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `frontend/scripts/collectionTasksVerificationUi.test.mjs`
- Test: `frontend/scripts/sharedVerificationDialogsUi.test.mjs`
- Test: `frontend/scripts/sharedVerificationDialogPropsUi.test.mjs`

- [ ] **Step 1: Write or extend the failing smoke coverage**

Target:
- pending verification workbench panel exists
- shared verification dialog still used
- pending items come from dedicated data source rather than task-row-only inference

- [ ] **Step 2: Run frontend smoke tests and verify failure**

Run: `node --test frontend/scripts/collectionTasksVerificationUi.test.mjs frontend/scripts/sharedVerificationDialogsUi.test.mjs frontend/scripts/sharedVerificationDialogPropsUi.test.mjs`
Expected: FAIL if the new workbench panel is not fully wired

- [ ] **Step 3: Add verification-items API wrapper**

In `frontend/src/api/collection.js`, add:
- `getVerificationItems(...)`

- [ ] **Step 4: Upgrade task-page workbench**

Implement:
- summary strip
- filterable pending verification panel
- actions: `立即回填`, `查看截图`, `跳到任务详情`, `复制任务ID`

- [ ] **Step 5: Re-run frontend smoke tests**

Run: `node --test frontend/scripts/collectionTasksVerificationUi.test.mjs frontend/scripts/sharedVerificationDialogsUi.test.mjs frontend/scripts/sharedVerificationDialogPropsUi.test.mjs`
Expected: PASS

- [ ] **Step 6: Build frontend**

Run: `npm run build`
Expected: PASS

---

### Task 4: Improve image readability in shared verification dialog

**Files:**
- Modify: `frontend/src/components/verification/VerificationResumeDialog.vue`
- Test: `frontend/scripts/verificationResumeDialogExperience.test.mjs`

- [ ] **Step 1: Extend the failing smoke/experience test**

Add checks for:
- enlarge/preview capability hook
- fallback message on image failure
- restoring-state info message while submitting

- [ ] **Step 2: Run the smoke test and verify failure**

Run: `node --test frontend/scripts/verificationResumeDialogExperience.test.mjs`
Expected: FAIL if preview/fallback behavior is missing

- [ ] **Step 3: Implement collection-friendly screenshot readability**

First version:
- keep inline preview
- allow click-to-enlarge preview
- preserve fallback when image load fails

- [ ] **Step 4: Re-run smoke test**

Run: `node --test frontend/scripts/verificationResumeDialogExperience.test.mjs`
Expected: PASS

---

### Task 5: Final regression pass for the workbench

**Files:**
- Verify only

- [ ] **Step 1: Run backend verification regression**

Run:
`python -m pytest backend/tests/test_collection_multi_account_verification_contract.py backend/tests/test_collection_verification_flow.py backend/tests/test_verification_service_contract.py backend/tests/test_component_recorder_gate_contract.py backend/tests/test_component_tester_verification_flow.py backend/tests/test_transition_gates_contract.py backend/tests/test_recorder_segment_validator.py -q`

Expected: PASS

- [ ] **Step 2: Run frontend smoke regression**

Run:
`node --test frontend/scripts/collectionTasksVerificationUi.test.mjs frontend/scripts/componentVersionsVerificationUi.test.mjs frontend/scripts/sharedVerificationDialogsUi.test.mjs frontend/scripts/sharedVerificationDialogPropsUi.test.mjs frontend/scripts/verificationResumeDialogExperience.test.mjs frontend/scripts/componentRecorderApiResponseShape.test.mjs`

Expected: PASS

- [ ] **Step 3: Run frontend production build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 4: Record manual acceptance outcome**

Reference:
- `docs/guides/VERIFICATION_FINAL_ACCEPTANCE_CHECKLIST.md`

Log whether the collection-task workbench passes:
- single-account paused item
- multi-item display
- readable captcha screenshot
- resume to `verification_submitted`

---

### Notes

- Do not create a separate verification center page in this plan.
- Do not introduce OCR or screenshot auto-cropping.
- Keep the workbench inside `CollectionTasks.vue` for now.
