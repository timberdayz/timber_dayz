# Data Sync Template Management Update Workbench Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign data-sync template management so operators can update large-header templates in a dedicated workbench, understand header changes clearly, and confirm deduplication fields safely before saving.

**Architecture:** Keep `/data-sync/templates` as the single route, but refactor the page from a long inline editor into a management dashboard plus an update workbench drawer. Add one focused backend update-context contract so the frontend can load existing template headers, existing deduplication fields, current file headers, and header-diff metadata in one place instead of assembling this context from scattered calls.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, existing `frontend/src/api/index.js` data-sync/field-mapping wrappers, existing `HEADER_CHANGED` diff signals

---

## File Structure

### Existing files to modify

- `frontend/src/views/DataSyncTemplates.vue`
  Responsibility: main template-management page; will be reduced to governance, missing/update queues, template list, and update-workbench entry state.
- `frontend/src/components/DeduplicationFieldsSelector.vue`
  Responsibility: current deduplication selection widget; may either be simplified for reuse or replaced by a workbench-specific deduplication review panel.
- `frontend/src/api/index.js`
  Responsibility: central data-sync / field-mapping API wrappers used by `DataSyncTemplates.vue`; will gain update-context and template-detail methods.
- `backend/routers/field_mapping_dictionary.py`
  Responsibility: template-related field-mapping endpoints; will gain the update-context API and any template detail contract cleanup needed by the workbench.
- `backend/services/field_mapping_template_service.py`
  Responsibility: template persistence and retrieval; will expose template header columns and deduplication fields in a workbench-friendly shape.
- `backend/schemas/data_sync.py`
  Responsibility: Pydantic contracts for data-sync-related request/response payloads; will gain typed response models for template update context if the router is upgraded to explicit schema returns.

### New files to create

- `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
  Responsibility: governance cards and tabs extracted from the current page shell.
- `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`
  Responsibility: focused `需要更新` table with update entry action and compact change summary.
- `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
  Responsibility: dedicated update workflow container, step shell, and save/cancel actions.
- `frontend/src/components/dataSync/TemplateChangeSummaryCard.vue`
  Responsibility: render match rate, added/removed counts, update reason, and old-core-field impact summary.
- `frontend/src/components/dataSync/HeaderDiffViewer.vue`
  Responsibility: render retained/added/removed/order-changed fields with filtering and search.
- `frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue`
  Responsibility: group existing available fields, missing old fields, recommended fields, and all current fields; render risky-save warnings.
- `frontend/src/components/dataSync/TemplateRawPreviewPanel.vue`
  Responsibility: secondary raw preview panel for row-level inspection without making it the primary decision surface.
- `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`
  Responsibility: static UI contract test for the template-management redesign and workbench entry points.
- `backend/tests/test_field_mapping_template_update_context_api.py`
  Responsibility: backend contract test for the update-context payload and risk-related field grouping.

### Existing tests to extend

- `frontend/scripts/pageStandards.test.mjs`
  Responsibility: keep the page consistent with existing page-level structure checks if the new component split affects route-level standards.
- `backend/tests/test_data_sync_schema_guardrails.py`
  Responsibility: extend only if new schema contracts need explicit registration/guardrail coverage.

---

## Task 1: Add Backend Template Update Context Contract

**Files:**
- Modify: `backend/routers/field_mapping_dictionary.py`
- Modify: `backend/services/field_mapping_template_service.py`
- Modify: `backend/schemas/data_sync.py`
- Test: `backend/tests/test_field_mapping_template_update_context_api.py`

- [ ] **Step 1: Write the failing backend contract test**

Add test cases covering:

- `GET /field-mapping/templates/{template_id}/update-context`
- response includes:
  - template metadata
  - template `header_columns`
  - template `deduplication_fields`
  - current file metadata when `file_id` is provided
  - current `header_columns`
  - `header_changes`
  - `match_rate`
  - `added_fields`
  - `removed_fields`
  - `existing_deduplication_fields_available`
  - `existing_deduplication_fields_missing`
  - `recommended_deduplication_fields`

- [ ] **Step 2: Run the focused backend test and verify failure**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
```

Expected: FAIL because the endpoint does not exist yet.

- [ ] **Step 3: Implement the minimal backend contract**

Add:

- typed response models in `backend/schemas/data_sync.py`
- a router endpoint in `backend/routers/field_mapping_dictionary.py`
- service changes in `backend/services/field_mapping_template_service.py` so template detail retrieval includes:
  - header columns
  - deduplication fields
  - core metadata required by the workbench

Reuse existing header-diff logic instead of introducing a second diff algorithm.

- [ ] **Step 4: Re-run the focused backend test**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/field_mapping_dictionary.py backend/services/field_mapping_template_service.py backend/schemas/data_sync.py backend/tests/test_field_mapping_template_update_context_api.py
git commit -m "feat: add data sync template update context api"
```

## Task 2: Lock The Frontend API And Page-Level Contract

**Files:**
- Modify: `frontend/src/api/index.js`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Write the failing frontend UI contract test**

Cover:

- `DataSyncTemplates.vue` still exists as the route entry
- the page exposes a dedicated update-workbench concept
- `frontend/src/api/index.js` exposes:
  - `getTemplateUpdateContext`
  - any template-detail helper used by the workbench
- the workbench-related components exist under `frontend/src/components/dataSync/`

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL because the new API and component files do not exist yet.

- [ ] **Step 3: Implement the minimal API wrapper and empty component shells**

Add:

- `getTemplateUpdateContext(templateId, fileId)` in `frontend/src/api/index.js`
- placeholder component files for the workbench split

Do not wire full behavior in this task; only establish the contract boundary.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/index.js frontend/src/components/dataSync frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: scaffold template management workbench contracts"
```

## Task 3: Simplify The Main Template Management Page

**Files:**
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Create: `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
- Create: `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Extend the failing UI contract test for the new page structure**

Cover:

- main page renders governance panel component
- main page renders a focused `needs update` queue/table
- inline raw preview is no longer the primary editing surface
- `更新模板` entry point opens a dedicated workbench flow rather than relying only on the long page

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL until the page is structurally split.

- [ ] **Step 3: Implement the dashboard-oriented page shell**

Extract:

- governance cards and tabs into `TemplateGovernancePanel.vue`
- the `需要更新` table into `TemplateNeedsUpdateTable.vue`

Keep `DataSyncTemplates.vue` responsible for page-level state orchestration only:

- list loading
- selected template/file context
- workbench open/close state

Avoid broad unrelated cleanup of existing comments or labels.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateGovernancePanel.vue frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: simplify data sync template management dashboard"
```

## Task 4: Build The Update Workbench Shell And Change Summary

**Files:**
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Create: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Create: `frontend/src/components/dataSync/TemplateChangeSummaryCard.vue`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Extend the failing UI contract test for workbench summary behavior**

Cover:

- clicking `更新模板` opens `TemplateUpdateWorkbenchDrawer`
- the workbench renders:
  - template name
  - match rate
  - added field count
  - removed field count
  - update reason
  - old deduplication field summary

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL until the drawer and summary are wired.

- [ ] **Step 3: Implement the workbench shell and summary**

Add:

- drawer or near-full-screen dialog shell
- async loading from `getTemplateUpdateContext`
- left-side step shell
- top summary card via `TemplateChangeSummaryCard.vue`

At this stage, the workbench may still use placeholder panels for diff and dedup review, but the summary data must be real.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/src/components/dataSync/TemplateChangeSummaryCard.vue frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: add template update workbench shell"
```

## Task 5: Add Header Diff Viewer And Secondary Raw Preview

**Files:**
- Create: `frontend/src/components/dataSync/HeaderDiffViewer.vue`
- Create: `frontend/src/components/dataSync/TemplateRawPreviewPanel.vue`
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Extend the failing UI contract test for diff behavior**

Cover:

- diff viewer exposes:
  - retained fields
  - added fields
  - removed fields
  - order-changed indicator
- diff viewer exposes search or filter affordances
- raw preview exists as a secondary/collapsible panel, not the primary comparison surface

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL until diff and preview panels are present.

- [ ] **Step 3: Implement the diff and raw preview panels**

Add:

- `HeaderDiffViewer.vue` with grouped field state rendering
- `TemplateRawPreviewPanel.vue` behind a collapsible or tabbed secondary section
- filters such as:
  - only changed fields
  - only added fields
  - old-core-field-related fields

Do not reintroduce the long horizontal preview table as the primary workflow.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dataSync/HeaderDiffViewer.vue frontend/src/components/dataSync/TemplateRawPreviewPanel.vue frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: add template header diff viewer"
```

## Task 6: Add Deduplication Review Groups And Risk Warnings

**Files:**
- Create: `frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue`
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Modify: `frontend/src/components/DeduplicationFieldsSelector.vue`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Extend the failing UI contract test for deduplication guidance**

Cover:

- the workbench shows grouped sections for:
  - available old deduplication fields
  - missing old deduplication fields
  - recommended fields
  - all current fields
- old deduplication fields still present are preselected
- missing old deduplication fields produce a visible warning block
- save flow renders a plain-language consequence summary

- [ ] **Step 2: Run the UI contract test and verify failure**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL until deduplication review guidance is implemented.

- [ ] **Step 3: Implement deduplication review logic**

Add:

- grouped rendering in `TemplateDeduplicationReviewPanel.vue`
- default selection from available old deduplication fields
- warning state when old fields disappear
- risky-save confirmation when the operator removes all old deduplication fields

Reuse `DeduplicationFieldsSelector.vue` internals only where that reduces duplication cleanly; otherwise keep the workbench-specific panel separate.

- [ ] **Step 4: Re-run the UI contract test**

Run:

```bash
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/src/components/DeduplicationFieldsSelector.vue frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: add template deduplication review warnings"
```

## Task 7: Wire Save Flow And Final Verification

**Files:**
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Modify: `frontend/src/api/index.js`
- Test: `backend/tests/test_field_mapping_template_update_context_api.py`
- Test: `frontend/scripts/dataSyncTemplateManagementUi.test.mjs`

- [ ] **Step 1: Add or extend failing assertions for end-to-end workbench save flow**

Cover:

- workbench save uses the existing template save API
- selected header row, current header columns, and confirmed deduplication fields are passed
- save success closes the workbench and refreshes:
  - template list
  - governance summary
  - file/template state

- [ ] **Step 2: Run the focused backend and frontend tests and verify failure**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: FAIL until the final save wiring is complete.

- [ ] **Step 3: Implement final save wiring**

Add:

- workbench save action
- success/error handling
- post-save refresh with the current page data loaders

Do not add version history or multi-file comparison in this task.

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
node frontend/scripts/dataSyncTemplateManagementUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Run frontend static verification**

Run:

```bash
npm --prefix frontend run lint
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Expected: PASS

- [ ] **Step 6: Run backend syntax verification**

Run:

```bash
python -m py_compile backend/routers/field_mapping_dictionary.py backend/services/field_mapping_template_service.py backend/schemas/data_sync.py
```

Expected: no output, exit code 0

- [ ] **Step 7: Manual smoke check**

Verify in the browser:

- open `/data-sync/templates`
- confirm the main page no longer forces inline long-page editing
- click `更新模板`
- verify change summary renders real diff metadata
- verify field comparison is usable without relying on horizontal full-table scrolling
- verify missing old deduplication fields are explicitly warned
- verify saving refreshes governance and template state

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync frontend/src/api/index.js backend/routers/field_mapping_dictionary.py backend/services/field_mapping_template_service.py backend/schemas/data_sync.py backend/tests/test_field_mapping_template_update_context_api.py frontend/scripts/dataSyncTemplateManagementUi.test.mjs
git commit -m "feat: add data sync template update workbench"
```

## Implementation Notes

- Keep the route path `/data-sync/templates` unchanged.
- Keep the existing template save API as the MVP persistence path.
- Treat raw row preview as secondary. Do not let the redesign regress into another wide inline table editor.
- Avoid broad unrelated cleanup of existing garbled comments or labels unless the touched area requires it.
- If the backend update-context endpoint becomes too complex inside `field_mapping_dictionary.py`, extract helper logic into `field_mapping_template_service.py` rather than bloating the router.
- If `backend/schemas/data_sync.py` becomes too crowded, split the new workbench contracts into a dedicated schema module in a follow-up refactor, but do not block MVP on that refactor.
