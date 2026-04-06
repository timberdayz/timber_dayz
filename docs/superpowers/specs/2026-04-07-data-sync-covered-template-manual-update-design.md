# Data Sync Covered Template Manual Update Design

**Date:** 2026-04-07

**Goal:** Allow operators to manually update already-covered templates from the frontend without waiting for the system to classify them as `needs_update`, while keeping the existing versioned template workflow and the current update workbench as the primary execution surface.

## 1. Background

The current data-sync template module already supports:

- template governance overview
- covered / missing / needs-update grouping
- template list and detail viewing
- deduplication field selection during template creation
- a dedicated update workbench for `needs_update` cases

However, there is still a clear operator gap:

1. A covered template in normal state cannot be proactively corrected from the frontend.
2. Operators can inspect current `deduplication_fields`, but cannot manually revise them unless the template enters the `needs_update` path or the operator recreates the template through the generic builder workflow.
3. The real operator intent is not always "this template structurally changed". Sometimes the intent is only "the core deduplication fields were configured incorrectly and need to be fixed now".

This creates avoidable friction in a place where configuration correctness matters, because template `deduplication_fields` directly affect later `data_hash` calculation during sync and ingest.

## 2. Existing Evidence

The current codebase already has most of the pieces needed for a manual-update flow:

- `frontend/src/views/DataSyncTemplates.vue`
  - renders the template list
  - renders covered / missing / needs-update governance panels
  - already shows template `deduplication_fields`
  - already saves templates through `api.saveTemplate`
- `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
  - already provides a dedicated save flow for template updates
  - already accepts a unified context object
- `frontend/src/components/dataSync/TemplateDeduplicationReviewPanel.vue`
  - already renders:
    - old deduplication fields still available
    - old deduplication fields missing
    - recommended deduplication fields
    - current field pool
- `frontend/src/api/index.js`
  - already exposes:
    - `getTemplateUpdateContext`
    - `saveTemplate`
- `backend/routers/field_mapping_dictionary.py`
  - already exposes:
    - `GET /field-mapping/templates/{template_id}/update-context`
    - `POST /field-mapping/templates/save`
- `backend/services/field_mapping_template_service.py`
  - already implements versioned template saving
  - already archives the previous `published` template in the same dimension and publishes a new version

This means the gap is primarily workflow and entry-point design, not missing core domain logic.

## 3. Problem Statement

The current module mixes two different operator intents under one narrow update path:

- correcting only the deduplication rule
- rebuilding template assumptions from a new sample file

Those are related, but they are not the same operation.

If the UI forces both through the same sample-file-driven update path:

- small fixes become unnecessarily expensive
- operators may avoid correcting bad deduplication settings
- users are blocked when they do not immediately have the right sample file

If the UI only supports in-place core-field edits:

- operators lose the stronger change-review flow needed when header structure has actually shifted

The design should therefore expose both actions explicitly and route them through the same workbench family with different context sources.

## 4. Design Goals

This redesign should achieve the following:

1. Allow proactive manual update for already-covered templates.
2. Separate "fix deduplication fields" from "rebuild from sample file".
3. Reuse the current update workbench and versioning model instead of creating a second full editor.
4. Keep operator decision cost low for simple fixes.
5. Preserve the stronger field-difference workflow for structural template changes.
6. Avoid introducing a route-heavy or editor-heavy redesign in this phase.

## 5. Options Considered

### 5.1 Option A: Core-Fields-Only Manual Edit

Expose manual update only as a lightweight deduplication-field editor.

Pros:

- smallest implementation cost
- fastest path to fix the current pain point

Cons:

- cannot handle cases where the template header baseline also needs reset
- would create a second, weaker update path beside the existing workbench

### 5.2 Option B: Recommended

Expose manual update from covered templates and template list, then ask the operator to choose one of two modes:

- `core-only`
- `with-sample`

Both modes should still route into the existing update workbench family.

Pros:

- solves the immediate operator gap
- keeps lightweight fixes lightweight
- keeps structural updates guided
- maximizes reuse of current frontend and backend code

Cons:

- requires one extra mode-selection step
- requires the update-context API to support a template-only mode

### 5.3 Option C: Full Template Editor

Create a separate editor page or drawer for all template editing actions:

- deduplication fields
- header row
- sample file
- header baseline
- version note

Pros:

- most complete long-term editor

Cons:

- highest implementation cost
- duplicates existing update-workbench concepts
- not required to solve the current problem

### 5.4 Recommendation

Choose **Option B**.

It directly solves the user's real workflow problem without forcing a larger route-level redesign or fragmenting template update behavior into unrelated editors.

## 6. Recommended UX

## 6.1 Entry Points

Add `Manual Update` in two places:

- covered template list in the governance panel
- template list in the main template table

Keep the existing `needs_update` update action, but align its label to the same concept where helpful.

This creates one mental model:

- templates can always be updated manually
- `needs_update` is system guidance, not the only permission to edit

## 6.2 First Interaction: Mode Selection

Clicking `Manual Update` should not immediately enter a file-driven flow.

Instead, show a lightweight mode-selection dialog with two choices:

- `Core Fields Only (Recommended)`
  - for cases where the template baseline is still valid and only `deduplication_fields` need correction
- `Reset From Sample File`
  - for cases where the operator wants to validate changes against a current file and possibly reset the field baseline

There should be no forced default auto-entry.

The dialog should recommend `Core Fields Only`, but still require explicit user selection.

This is important because:

- auto-defaulting to `core-only` can hide actual structural change
- auto-defaulting to `with-sample` makes simple fixes too heavy

## 6.3 Mode A: Core-Only Update

In `core-only` mode:

- no sample file is required
- the field pool comes directly from the template's stored `header_columns`
- the operator edits only `deduplication_fields`
- the save action creates a new template version with the same template baseline and a new deduplication configuration

The UI should still show:

- current template name and version
- current deduplication fields
- recommended deduplication fields derived from domain + sub-domain
- validation warnings if selected fields are weak or missing from the field pool

The UI does not need to show:

- field added/removed diff
- row preview
- sample file preview

This path should be short and task-focused.

## 6.4 Mode B: Update With Sample File

In `with-sample` mode:

- the operator selects or confirms a candidate sample file
- the system loads header differences between template and file
- the existing update workbench remains the main execution surface

The UI should continue showing:

- added fields
- removed fields
- old deduplication fields still available
- old deduplication fields missing
- recommended deduplication fields
- preview data if available

This mode is the correct path when the operator suspects the template baseline itself may need reset.

## 7. Frontend Design

## 7.1 Components To Add

Add a lightweight mode-selection component, for example:

- `frontend/src/components/dataSync/TemplateManualUpdateModeDialog.vue`

Responsibilities:

- show basic template identity
- explain the two manual-update modes
- emit:
  - `core-only`
  - `with-sample`

This component should not own any business logic or saving logic.

## 7.2 Components To Update

Update:

- `frontend/src/views/DataSyncTemplates.vue`
- `frontend/src/components/dataSync/TemplateGovernancePanel.vue`
- `frontend/src/components/dataSync/TemplateNeedsUpdateTable.vue`
- `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`

### `DataSyncTemplates.vue`

Should become the orchestration layer for:

- opening the mode-selection dialog
- tracking the selected template
- resolving the requested update mode
- loading update context
- opening the update workbench

Recommended new state:

- `manualUpdateModeDialogVisible`
- `pendingManualUpdateTemplate`
- `manualUpdateMode`

### `TemplateGovernancePanel.vue`

In the covered-template table, add `手动更新`.

This should emit the covered-template row upward exactly like other governance actions.

### `TemplateNeedsUpdateTable.vue`

Keep the existing update action, but align the entry path with the new orchestration flow.

The row already contains:

- `template_id`
- `sample_file_id`
- `sample_file_name`
- `update_reason`

That means this table can directly route into `with-sample` mode without extra discovery.

### `TemplateUpdateWorkbenchDrawer.vue`

Keep this as the main execution surface.

Extend it so the same drawer can render both context types:

- template-only context
- sample-file comparison context

Rendering rules:

- if `update_mode === "core-only"`:
  - hide or collapse the raw preview panel
  - hide added/removed field emphasis if empty
  - focus the drawer on deduplication-field review and save
- if `update_mode === "with-sample"`:
  - keep the current diff-oriented behavior

## 8. Backend Design

## 8.1 Reuse The Existing Update-Context Endpoint

Do not create a new editor-specific API in this phase.

Extend the existing endpoint:

- `GET /field-mapping/templates/{template_id}/update-context`

Add support for:

- `mode=core-only`
- `mode=with-sample`

Parameter behavior:

- `template_id` is always required
- `mode` defaults to `with-sample` for backward compatibility
- `file_id` is only used for `with-sample`

## 8.2 Core-Only Context Shape

In `core-only` mode, the endpoint should return a context payload that matches the workbench contract but uses template-owned data as the current field source.

Recommended semantics:

- `template_header_columns = template.header_columns`
- `current_header_columns = template.header_columns`
- `match_rate = 100`
- `added_fields = []`
- `removed_fields = []`
- `current_file = null`
- `preview_data = []`
- `update_mode = "core-only"`
- `header_source = "template"`

Deduplication review fields:

- `existing_deduplication_fields_available`
  - template `deduplication_fields` intersected with template `header_columns`
- `existing_deduplication_fields_missing`
  - template `deduplication_fields` not found in template `header_columns`
- `recommended_deduplication_fields`
  - default deduplication fields intersected with template `header_columns`

This keeps the frontend workbench API-stable while supporting a lighter operator path.

## 8.3 With-Sample Context Shape

Keep the current `with-sample` flow largely unchanged:

- resolve current file preview
- detect header changes
- split old deduplication fields into available / missing
- compute recommended fields from defaults

This preserves the stronger guided update flow for structural changes.

## 8.4 Save Path

Continue using:

- `POST /field-mapping/templates/save`

Do not create a separate "update template" write API in this phase.

Reasons:

- the current save path already validates `deduplication_fields`
- the service layer already archives the previous `published` template and creates a new version
- this keeps write semantics consistent across template create and template update flows

Save rules by mode:

- `core-only`
  - save the existing template baseline
  - pass template `header_columns` unchanged
  - pass the newly selected `deduplication_fields`
- `with-sample`
  - save the current sample-derived `header_columns`
  - pass the newly selected `deduplication_fields`

## 9. Versioning And Safety Rules

Keep versioned template publishing behavior unchanged.

For the same dimension:

- `platform`
- `data_domain`
- `sub_domain`
- `granularity`
- `account`

Saving a new template version should:

1. archive the old `published` template
2. create a new `published` template

Do not perform in-place updates on the existing template row.

This preserves traceability and keeps rollback reasoning straightforward.

## 10. Validation And Operator Guidance

The UI should apply three layers of operator guidance:

### 10.1 Hard Validation

Do not allow save when:

- `deduplication_fields` is empty

### 10.2 Strong Warning

Warn prominently when selected deduplication fields are not in the active field pool.

This should be visible in the frontend, not only logged in the backend.

### 10.3 Soft Warning

Warn when the selected deduplication field set appears too weak to uniquely identify rows.

This should not block save, but should remind the operator to prefer stable identifiers such as:

- order id
- product sku
- product id
- date
- platform
- shop

depending on domain.

## 11. Minimal Delivery Scope

Phase 1 should include only the minimum end-to-end workflow:

- add `手动更新` to covered templates
- add `手动更新` to the template list
- add a mode-selection dialog
- support:
  - `core-only`
  - `with-sample`
- extend the existing update-context endpoint
- reuse the existing save endpoint
- reuse the existing update workbench drawer

Phase 1 should not include:

- a separate full template editor page
- batch update across multiple templates
- in-place historical version editing
- approval workflows
- route-level redesign of the module

## 12. Acceptance Criteria

1. An already-covered template in normal state can be manually updated from the frontend.
2. A user can update only `deduplication_fields` without selecting a sample file.
3. The existing sample-file-driven update flow still works for `needs_update` cases.
4. Saving a manual update creates a new `published` template version and archives the old one.
5. Sync and ingest continue to consume the new template version's `deduplication_fields`.
6. The frontend clearly warns when selected deduplication fields are empty, missing from the field pool, or likely too weak.
7. Existing template-creation and missing-template flows remain unchanged.

## 13. Implementation Notes

- Keep the module in Vue 3 + Element Plus + Pinia + Vite.
- Reuse the current workbench as much as possible rather than creating a second editor.
- Prefer extending the existing context API over introducing new endpoints.
- Keep logs and terminal output emoji-free.
- Preserve the current repository's template versioning semantics and tag-driven release assumptions.
