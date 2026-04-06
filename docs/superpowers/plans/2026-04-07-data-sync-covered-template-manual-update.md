# Data Sync Covered Template Manual Update Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators manually update already-covered data-sync templates from the frontend, with an explicit choice between a lightweight deduplication-only correction flow and the existing sample-file-driven reset flow.

**Architecture:** Keep `/data-sync/templates` as the single management route and reuse the current versioned template save path. Extend the existing template update-context API to support a template-only mode, add one lightweight mode-selection dialog in the frontend, and route both manual-update modes through the current update workbench so the UI stays consistent.

**Tech Stack:** FastAPI, SQLAlchemy async, Vue 3, Element Plus, existing `frontend/src/api/index.js` wrappers, existing `POST /field-mapping/templates/save` versioned template flow, Node `node:test` source-contract tests, pytest backend API tests

---

## File Structure

### Existing files to modify

- `frontend/src/views/DataSyncTemplates.vue`
  Responsibility: orchestrate manual-update entry points, mode-selection dialog state, update-context loading, and workbench open/close behavior.
- `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
  Responsibility: expose `Manual Update` for covered templates in the governance panel.
- `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`
  Responsibility: align existing update action with the new manual-update orchestration flow and text labels.
- `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
  Responsibility: render both `core-only` and `with-sample` update contexts while reusing the current save flow.
- `frontend/src/api/index.js`
  Responsibility: expose frontend wrappers for loading update context in both modes and saving the resulting template version.
- `backend/routers/field_mapping_dictionary.py`
  Responsibility: extend the template update-context endpoint to support `mode=core-only` while keeping the current `with-sample` behavior.
- `backend/services/field_mapping_template_service.py`
  Responsibility: expose any template-owned fields or helper data needed by the `core-only` update context without changing write semantics.

### New files to create

- `frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue`
  Responsibility: lightweight modal that lets the operator explicitly choose `Core Fields Only` or `Reset From Sample File`.
- `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`
  Responsibility: source-level UI contract test covering new manual-update entry points, the mode-selection dialog, and the `core-only` orchestration markers.
- `backend/tests/test_template_manual_update_context_api.py`
  Responsibility: backend contract test for `GET /field-mapping/templates/{template_id}/update-context` with `mode=core-only` and `mode=with-sample`.

### Existing tests to review or extend if already present

- `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`
  Responsibility: retain existing update-workbench expectations if the file is already the canonical UI contract test for this module.
- `backend/tests/test_field_mapping_template_update_context_api.py`
  Responsibility: if this file already exists or is introduced before implementation, merge the new `core-only` assertions into it instead of duplicating contracts.

---

## Task 1: Lock The Backend Manual-Update Contract

**Files:**
- Create: `backend/tests/test_template_manual_update_context_api.py`
- Modify: `backend/routers/field_mapping_dictionary.py`
- Modify: `backend/services/field_mapping_template_service.py`

- [ ] **Step 1: Write the failing backend contract tests**

Cover these cases:

- `GET /field-mapping/templates/{template_id}/update-context?mode=core-only`
  - returns template metadata
  - returns `update_mode = "core-only"`
  - returns `template_header_columns`
  - returns `current_header_columns` equal to template `header_columns`
  - returns `added_fields = []`
  - returns `removed_fields = []`
  - returns `current_file = null`
  - returns `preview_data = []`
  - returns `existing_deduplication_fields_available`
  - returns `existing_deduplication_fields_missing`
  - returns `recommended_deduplication_fields`
- `GET /field-mapping/templates/{template_id}/update-context?mode=with-sample&file_id=<id>`
  - preserves the current sample-file-driven behavior

- [ ] **Step 2: Run the focused backend test and verify failure**

Run:

```bash
pytest backend/tests/test_template_manual_update_context_api.py -q
```

Expected: FAIL because `mode=core-only` is not implemented yet.

- [ ] **Step 3: Implement the minimal backend context extension**

In `backend/routers/field_mapping_dictionary.py`:

- add optional `mode` query parameter
- default to `with-sample` for backward compatibility
- branch behavior:
  - `core-only`
  - `with-sample`

In `backend/services/field_mapping_template_service.py`:

- add or expose helper logic needed to obtain template-owned `header_columns` and `deduplication_fields` cleanly for the router

Do not create a new write endpoint.
Do not change the versioning model.

- [ ] **Step 4: Re-run the focused backend test**

Run:

```bash
pytest backend/tests/test_template_manual_update_context_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_template_manual_update_context_api.py backend/routers/field_mapping_dictionary.py backend/services/field_mapping_template_service.py
git commit -m "feat: add core-only template update context"
```

## Task 2: Lock The Frontend Manual-Update Entry Contract

**Files:**
- Create: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Modify: `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
- Modify: `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`

- [ ] **Step 1: Write the failing frontend source-contract test**

Cover:

- `TemplateGovernancePanel.vue` exposes a covered-template `Manual Update` action
- `DataSyncTemplates.vue` exposes a template-list `Manual Update` action
- `DataSyncTemplates.vue` holds manual-update orchestration state
- `TemplateNeedsUpdateTable.vue` still exposes the update action after the refactor

- [ ] **Step 2: Run the frontend source-contract test and verify failure**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: FAIL because the new manual-update markers and actions do not exist yet.

- [ ] **Step 3: Implement the new entry points**

In `frontend/src/components/dataSync/TemplateGovernancePanel.vue`:

- add `Manual Update` to covered-template rows
- emit a dedicated event upward

In `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`:

- align the action label and emitted event with the new manual-update orchestration path without breaking current semantics

In `frontend/src/views/DataSyncTemplates.vue`:

- add a template-list `Manual Update` action
- add orchestration state:
  - pending template
  - dialog visible flag
  - selected mode

- [ ] **Step 4: Re-run the frontend source-contract test**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateGovernancePanel.vue frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue
git commit -m "feat: add manual update entry points for covered templates"
```

## Task 3: Add The Mode-Selection Dialog

**Files:**
- Create: `frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Test: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`

- [ ] **Step 1: Extend the failing source-contract test**

Cover:

- `TemplateManualUpdateModeDialog.vue` exists
- it contains both modes:
  - `Core Fields Only`
  - `Reset From Sample File`
- `DataSyncTemplates.vue` renders or imports the dialog

- [ ] **Step 2: Run the source-contract test and verify failure**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: FAIL until the dialog exists and is wired in.

- [ ] **Step 3: Implement the lightweight mode selector**

Create `frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue` with:

- template identity summary
- two explicit choices
- no business logic
- emits for:
  - close
  - choose `core-only`
  - choose `with-sample`

Wire it into `frontend/src/views/DataSyncTemplates.vue`.

- [ ] **Step 4: Re-run the source-contract test**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue frontend/src/views/DataSyncTemplates.vue frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
git commit -m "feat: add template manual update mode dialog"
```

## Task 4: Extend The Frontend API Wrapper For Both Modes

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Test: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`

- [ ] **Step 1: Extend the failing source-contract test**

Cover:

- `getTemplateUpdateContext` accepts mode-aware usage
- `DataSyncTemplates.vue` requests:
  - template-only context for `core-only`
  - sample-file context for `with-sample`

- [ ] **Step 2: Run the source-contract test and verify failure**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: FAIL until the wrapper and calling code support both modes.

- [ ] **Step 3: Implement the minimal API changes**

In `frontend/src/api/index.js`:

- allow `getTemplateUpdateContext(templateId, { mode, fileId })`
- keep backward compatibility with the current `fileId`-only path if already used elsewhere

In `frontend/src/views/DataSyncTemplates.vue`:

- route `core-only` into update-context with `mode=core-only`
- route `with-sample` into update-context with `mode=with-sample` and the chosen `file_id`

- [ ] **Step 4: Re-run the source-contract test**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/index.js frontend/src/views/DataSyncTemplates.vue frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
git commit -m "feat: add mode-aware template update context loading"
```

## Task 5: Teach The Update Workbench To Render Core-Only Context

**Files:**
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Possibly modify: `frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue`
- Test: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`

- [ ] **Step 1: Extend the failing source-contract test**

Cover:

- `TemplateUpdateWorkbenchDrawer.vue` supports a `core-only` context
- `core-only` mode uses template `header_columns` as the current field pool
- `core-only` mode does not require preview data
- save button remains disabled when no deduplication fields are selected

- [ ] **Step 2: Run the source-contract test and verify failure**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: FAIL until the drawer reacts to `update_mode`.

- [ ] **Step 3: Implement the minimal drawer changes**

In `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`:

- branch on `update_mode`
- when `core-only`:
  - treat template `header_columns` as the active field pool
  - keep deduplication review visible
  - hide or de-emphasize raw preview and diff areas when empty

In `frontend/src/views/DataSyncTemplates.vue`:

- ensure the loaded context is passed through unchanged

Keep the save payload shape unchanged:

- `platform`
- `data_domain`
- `sub_domain`
- `granularity`
- `header_row`
- `header_columns`
- `deduplication_fields`

- [ ] **Step 4: Re-run the source-contract test**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
git commit -m "feat: support core-only template updates in workbench"
```

## Task 6: Preserve The Sample-Driven Flow And Save Semantics

**Files:**
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Modify: `frontend/src/api/index.js`
- Modify: `backend/routers/field_mapping_dictionary.py`
- Test: `backend/tests/test_template_manual_update_context_api.py`
- Test: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`

- [ ] **Step 1: Add regression assertions before implementation**

Backend regression assertions:

- `with-sample` still returns file-specific header data
- current file preview fields are unchanged

Frontend regression assertions:

- `needs_update` rows still open the update workbench
- the save path still uses `api.saveTemplate`
- no new write endpoint is introduced

- [ ] **Step 2: Run focused regression tests and verify any failure**

Run:

```bash
pytest backend/tests/test_template_manual_update_context_api.py -q
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: any new regression assertions fail before the compatibility fixes are implemented.

- [ ] **Step 3: Implement compatibility fixes**

Ensure:

- existing `with-sample` entry points still work
- sample-file row IDs from the governance `needs_update` table still reach the update-context API
- save still posts to `POST /field-mapping/templates/save`
- old `published` version is archived and the new one becomes `published`

- [ ] **Step 4: Re-run the focused regression tests**

Run:

```bash
pytest backend/tests/test_template_manual_update_context_api.py -q
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DataSyncTemplates.vue frontend/src/api/index.js backend/routers/field_mapping_dictionary.py backend/tests/test_template_manual_update_context_api.py frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
git commit -m "feat: preserve sample-driven template update flow"
```

## Task 7: Full Verification

**Files:**
- Verify: `frontend/src/views/DataSyncTemplates.vue`
- Verify: `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
- Verify: `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`
- Verify: `frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue`
- Verify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Verify: `frontend/src/api/index.js`
- Verify: `backend/routers/field_mapping_dictionary.py`
- Verify: `backend/services/field_mapping_template_service.py`
- Verify: `backend/tests/test_template_manual_update_context_api.py`
- Verify: `frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest backend/tests/test_template_manual_update_context_api.py -q
```

Expected: PASS

- [ ] **Step 2: Run focused frontend source-contract tests**

Run:

```bash
node --test frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Run broader related regression tests if they exist**

Run:

```bash
node --test frontend/scripts/dataSyncTemplateManagementUi.test.mjs
pytest backend/tests -q -k "template and update_context"
```

Expected: PASS, or if the broader backend pattern is too expensive/noisy, record the exact skipped scope in the progress log before shipping.

- [ ] **Step 4: Manual verification checklist**

Verify in the UI:

- a covered template shows `Manual Update`
- a template-list row shows `Manual Update`
- clicking `Manual Update` opens the mode-selection dialog
- choosing `Core Fields Only` opens the workbench without requiring a sample file
- choosing `Reset From Sample File` keeps the existing sample-driven flow
- saving produces a new template version
- the old version becomes archived
- the template list immediately reflects the updated deduplication fields

- [ ] **Step 5: Final commit**

```bash
git add frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateGovernancePanel.vue frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/src/api/index.js backend/routers/field_mapping_dictionary.py backend/services/field_mapping_template_service.py backend/tests/test_template_manual_update_context_api.py frontend/scripts/dataSyncCoveredTemplateManualUpdateUi.test.mjs
git commit -m "feat: support manual updates for covered data sync templates"
```

## Implementation Notes

- Keep scope tightly focused on manual update for covered templates.
- Do not add a new template write endpoint in this phase.
- Do not add a route-level redesign or a separate full template editor.
- Preserve the existing versioned template save semantics.
- Keep terminal/log output emoji-free for Windows compatibility.
- If an existing canonical UI-contract or API-contract test file already covers this area, merge the new assertions there instead of introducing duplicate test files.
