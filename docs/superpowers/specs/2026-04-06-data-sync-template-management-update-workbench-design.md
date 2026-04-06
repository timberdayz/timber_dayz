# Data Sync Template Management Update Workbench Design

**Date:** 2026-04-06

**Goal:** Redesign the data-sync template management page so operators can update templates with large header sets efficiently, see why a template needs update, and make safe deduplication-field decisions with clear guidance from the existing template and current file differences.

## 1. Background

The current template management page already contains the core functions:

- governance overview
- missing-template and needs-update lists
- file selection
- preview by header row
- raw header list
- deduplication field selection
- existing template list

However, the current interaction model has two concrete operator problems:

1. When the detected header set is large, the page becomes too wide and too long. Operators must scroll horizontally in the preview table while also scrolling vertically through the page to finish the update.
2. When a template needs update, the page does not clearly tell the operator:
   - what changed relative to the existing template
   - which old deduplication fields are still valid
   - which old deduplication fields disappeared
   - which recommended fields should be considered now

This leads to blind updates, and blind updates are risky because deduplication fields directly affect later upsert and data-isolation behavior.

## 2. Existing Evidence

The current codebase already contains most of the required signals:

- `frontend/src/views/DataSyncTemplates.vue`
  - already renders `needs_update`
  - already renders `update_reason`
  - already saves `deduplication_fields`
- `frontend/src/components/DeduplicationFieldsSelector.vue`
  - already supports recommended deduplication fields
  - already supports initial selected fields
- `frontend/src/views/DataSyncFiles.vue`
  - already handles `HEADER_CHANGED`
  - already opens a dedicated header-change comparison flow
- `backend/routers/data_sync.py`
  - already exposes `/data-sync/governance/detailed-coverage`
  - already decides `needs_update` from header change detection and match rate
- `backend/services/field_mapping_template_service.py`
  - already returns template `deduplication_fields`
- `backend/services/deduplication_fields_config.py`
  - already defines default deduplication strategies by domain

This means the redesign should focus on information architecture and explicit operator guidance, not on inventing a new detection algorithm.

## 3. Design Goals

This redesign should achieve the following:

1. Keep the main template management page readable when headers are large.
2. Turn template update into a guided workflow instead of a long-page manual edit.
3. Make old deduplication fields visible and actionable during update.
4. Show field differences before the operator decides what to save.
5. Keep the implementation inside the current Vue 3 + Element Plus + Pinia structure.
6. Avoid a full workflow rewrite of the wider data-sync module.

## 4. Options Considered

### 4.1 Option A: Minimal In-Place Cleanup

Keep the current long page and add only:

- a narrower preview
- a sticky toolbar
- a text hint for old deduplication fields

Pros:

- smallest implementation cost
- lowest code churn

Cons:

- the page remains structurally overloaded
- field-difference understanding is still weak
- operators still update templates inside a long mixed-purpose page

### 4.2 Option B: Recommended

Keep the main page for governance and listing, but move template update into a dedicated update workbench opened from `更新模板`.

The workbench should be a full-height drawer or near-full-screen dialog with three explicit steps:

1. change summary
2. field comparison
3. deduplication field confirmation

Pros:

- solves the width and decision-making problems together
- preserves the current page as a management entry point
- fits the current frontend architecture with moderate refactoring

Cons:

- requires extracting the current page into smaller components
- needs one additional context API or assembled frontend context payload

### 4.3 Option C: Full Page Split

Split the module into separate pages:

- governance page
- template editor page
- template detail page

Pros:

- cleanest long-term separation

Cons:

- highest implementation cost for this phase
- more route and navigation changes than necessary

### 4.4 Recommendation

Choose **Option B**.

It fixes the actual operator pain without forcing a large route-level redesign.

## 5. Recommended Information Architecture

The template management page should become a management dashboard, not an editing canvas.

### 5.1 Main Page Responsibilities

Keep only these responsibilities on the main page:

- governance summary
- missing-template list
- needs-update list
- existing template list
- entry points into create/update/detail actions

The main page should no longer host the full editing workflow inline.

### 5.2 Update Workbench Responsibilities

The update workbench should own all update-specific decisions:

- why update is needed
- what fields changed
- what old deduplication fields exist
- what default recommendation exists now
- what will be saved

## 6. Update Workbench UX

## 6.1 Entry Trigger

From the `需要更新` list, clicking `更新模板` should open a dedicated workbench.

The workbench should preload:

- target platform / domain / sub-domain / granularity
- current template metadata
- current template deduplication fields
- latest candidate file
- detected header changes

## 6.2 Layout

Use a two-column workbench inside a full-height drawer or near-full-screen dialog.

Left side:

- step navigation
- summary card
- save area

Right side:

- change summary
- field diff panel
- deduplication field panel

This keeps the operator in one task-focused view and avoids the long-page scroll problem.

## 6.3 Three-Step Workflow

### Step 1: Change Summary

Show a compact summary before any editing:

- current template name
- current template version
- current template deduplication fields
- match rate
- added field count
- removed field count
- order-changed indicator
- affected file count
- update reason

Suggested callouts:

- `新增字段 8 个`
- `删除字段 1 个`
- `匹配率 82%`
- `旧核心字段 2 个仍可用，1 个已失效`

### Step 2: Field Comparison

Do not render a wide all-column preview table as the primary decision surface.

Instead, render a structured comparison view:

- left: old template fields
- right: current file fields
- status badges:
  - retained
  - added
  - removed
  - order changed

Add filtering tools:

- only changed fields
- only fields related to old deduplication fields
- only added fields
- search by field name

If the operator still needs raw preview rows, keep that as a secondary collapsible panel, not the main mode.

### Step 3: Deduplication Field Confirmation

This section is the most important part of the update flow.

Fields should be shown in explicit groups:

- old deduplication fields still available
- old deduplication fields missing
- system recommended fields
- all current fields

Interaction rules:

- old deduplication fields that still exist should be preselected
- missing old deduplication fields should be shown in a warning block, not silently dropped
- recommended fields should be highlighted but not auto-overwrite operator choices
- if the operator removes all old deduplication fields, require a confirmation

## 7. Deduplication Guidance Rules

The page should explain consequences, not only validation.

### 7.1 Information-Level Guidance

Show:

- current template deduplication fields
- currently available recommended fields
- which old fields are still present in the new header

### 7.2 Risk-Level Guidance

Show warnings when:

- an old deduplication field disappeared
- none of the old deduplication fields remain
- the operator chooses fields that are not in the current header

### 7.3 Outcome-Level Guidance

Before save, show the resulting deduplication rule in plain language, for example:

> 保存后系统将按 `订单号 + 店铺ID` 判定同一条数据，这会影响后续同步的去重与覆盖。

This should make the save decision operationally clear.

## 8. Preview And Large-Header Handling

The current page uses a wide table as the main preview surface. That is the wrong default when headers are numerous.

Recommended handling:

1. Raw row preview becomes secondary.
2. Field-diff view becomes primary.
3. Large field lists use searchable grouped lists rather than relying only on horizontal table scroll.
4. Show only a limited number of sample columns in default mode.
5. Provide `查看全部字段` and `仅看变化字段` toggles.

This preserves full information while preventing the update experience from collapsing into spreadsheet-style scrolling.

## 9. Main Page Redesign

The main page should be simplified into three stacked areas:

### 9.1 Governance Overview

Keep summary cards and tabs, but make the `需要更新` tab action-oriented.

Recommended columns for `需要更新`:

- platform
- domain
- sub-domain
- granularity
- template name
- affected file count
- change summary
- old deduplication field count
- action

`change summary` should replace a generic long text reason where possible.

### 9.2 Pending Update Queue

This should become the operational heart of the page.

Each row should clearly answer:

- why it needs update
- how severe it is
- whether old core fields are impacted

### 9.3 Existing Template List

Keep the current list, but it becomes a reference and detail entry, not the main editing area.

## 10. Suggested Frontend Component Split

The current `DataSyncTemplates.vue` is too large for the new workflow.

Recommended split:

- `TemplateGovernancePanel.vue`
- `TemplateNeedsUpdateTable.vue`
- `TemplateUpdateWorkbenchDrawer.vue`
- `TemplateChangeSummaryCard.vue`
- `HeaderDiffViewer.vue`
- `TemplateDeduplicationReviewPanel.vue`
- `TemplateRawPreviewPanel.vue`
- `TemplateListTable.vue`

This keeps responsibilities focused and fits the repository's Vue 3 component patterns.

## 11. Data Contract Recommendations

## 11.1 Existing Contracts To Reuse

Reuse where possible:

- `/data-sync/governance/detailed-coverage`
- template list data with `deduplication_fields`
- default deduplication field recommendation API
- existing header change detection result shape

## 11.2 Recommended New Update Context API

Add one dedicated context endpoint for the workbench if the current frontend cannot assemble all needed data cleanly.

Suggested shape:

- `GET /field-mapping/templates/{id}/update-context?file_id=...`

Suggested response fields:

- template metadata
- template `header_columns`
- template `deduplication_fields`
- current file metadata
- current `header_columns`
- `header_changes`
- `match_rate`
- `added_fields`
- `removed_fields`
- `existing_deduplication_fields_available`
- `existing_deduplication_fields_missing`
- `recommended_deduplication_fields`

This avoids scattering update logic across multiple frontend calls.

## 11.3 Save Contract

The save contract can continue to use the existing template save API in phase 1, as long as the workbench passes:

- selected header row
- current header columns
- confirmed deduplication fields

No backend rewrite is required to start.

## 12. Error Handling And Validation

The workbench should explicitly handle:

- no candidate file found
- preview failed
- header row changed but no header detected
- old deduplication field missing
- selected deduplication field not in current header
- save conflict or stale update

Validation should not rely only on `至少选择 1 个核心字段`.

It should also distinguish:

- safe
- risky but allowed
- blocked

## 13. MVP Scope

Phase 1 should focus on the smallest change set that solves the operator pain.

### 13.1 Included In MVP

- simplify the main page structure
- open `更新模板` in a dedicated workbench drawer/dialog
- show change summary
- show old deduplication fields and whether they still exist
- support grouped deduplication confirmation
- move raw preview behind a secondary panel
- keep existing save API

### 13.2 Not Included In MVP

- template version history browser
- multi-file comparison in one workbench
- template diff audit trail
- automatic deduplication-field migration rules by platform
- cross-page route redesign

## 14. Rollout Order

Recommended implementation order:

1. frontend component split
2. update workbench shell
3. change summary and deduplication guidance
4. header diff viewer
5. optional backend update-context endpoint
6. verification with large-header sample files

## 15. Success Criteria

The redesign is successful when:

1. Operators can update a large-header template without relying on long horizontal scrolling as the main workflow.
2. Operators can see old deduplication fields before saving.
3. Operators are warned when old deduplication fields disappear.
4. Operators can understand the difference between old and new headers within one focused update flow.
5. The main template page remains readable and action-oriented.

## 16. Conclusion

The right fix is not another scroll container. The right fix is to separate management from editing and turn template update into a guided workbench.

The repository already has the core backend and frontend signals needed for this:

- template update detection
- header change details
- saved deduplication fields
- default deduplication recommendations

The next step should therefore be a focused frontend redesign with a small supporting context API only if needed.
