# Account Management Frontend Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the account management page into a scalable “platform > main account” interface that keeps existing account operations intact while making large multi-shop datasets manageable.

**Architecture:** Keep the existing `accounts` store and API surface unchanged, but introduce a pure helper that derives grouped main-account view models from the existing account list. Update the page into a master-detail layout with a left-side grouped navigator and a right-side current-main-account workspace. Use existing lightweight `node:test` UI source checks to lock the new structure.

**Tech Stack:** Vue 3, Element Plus, Pinia, Vite, Node `node:test`, existing account management store/API

---

## File Structure

### Existing files to modify

- `frontend/src/views/AccountManagement.vue`
  Responsibility: replace the single global table layout with the new grouped master-detail UI while preserving dialogs, actions, filters, and discovery flow.
- `frontend/scripts/accountManagementMainAccountNameUi.test.mjs`
  Responsibility: keep existing account management UI expectations valid if affected by template refactoring.
- `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`
  Responsibility: ensure shop discovery entry points remain visible after the layout rewrite.

### New files to create

- `frontend/src/utils/accountManagementView.js`
  Responsibility: build grouped view models and summary stats for “platform > main account > shops”.
- `frontend/scripts/accountManagementGroupedViewUi.test.mjs`
  Responsibility: lock the grouped layout and navigator/detail structure in a focused failing test first.
- `frontend/scripts/accountManagementViewHelpers.test.mjs`
  Responsibility: verify grouping, counting, and selection fallback logic with deterministic inputs.

---

## Task 1: Lock The New Grouped UI With Failing Tests

**Files:**
- Create: `frontend/scripts/accountManagementGroupedViewUi.test.mjs`
- Create: `frontend/scripts/accountManagementViewHelpers.test.mjs`

- [ ] **Step 1: Write the failing grouped-layout UI test**

Assert that `AccountManagement.vue` exposes markers for:
- platform/main-account navigator
- current main-account summary
- current main-account shop table
- empty state for no selected/visible groups

- [ ] **Step 2: Write the failing helper test**

Create deterministic input rows that prove:
- accounts are grouped by platform, then main account
- main-account summaries compute total/active/inactive shop counts
- missing main-account metadata falls back sensibly
- selection fallback chooses the first visible main account when needed

- [ ] **Step 3: Run focused tests to verify failure**

Run:

```bash
node --test frontend/scripts/accountManagementGroupedViewUi.test.mjs frontend/scripts/accountManagementViewHelpers.test.mjs
```

Expected: FAIL because the grouped layout markers and helper implementation do not exist yet.

## Task 2: Implement Pure Grouping Helpers

**Files:**
- Create: `frontend/src/utils/accountManagementView.js`
- Modify: `frontend/scripts/accountManagementViewHelpers.test.mjs`

- [ ] **Step 1: Implement minimal helper functions**

Implement:
- grouped view model builder
- main-account summary calculator
- selected-main-account fallback resolver

Keep the API small and data-oriented.

- [ ] **Step 2: Re-run helper tests**

Run:

```bash
node --test frontend/scripts/accountManagementViewHelpers.test.mjs
```

Expected: PASS

## Task 3: Rebuild The Page Into Master-Detail Layout

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`
- Modify: `frontend/scripts/accountManagementGroupedViewUi.test.mjs`
- Modify: `frontend/scripts/accountManagementMainAccountNameUi.test.mjs`
- Modify: `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`

- [ ] **Step 1: Import the new helper and derive grouped computed state**

Add computed state for:
- grouped navigator data
- current selected main account
- current selected shops
- current empty state reason

- [ ] **Step 2: Replace the full-page global table with grouped layout**

Keep:
- page header
- unmatched alias alert
- stats cards
- filter and action toolbar
- dialogs

Add:
- left-side grouped main-account navigator
- right-side current main-account summary panel
- right-side current-shop table scoped to the selected main account

- [ ] **Step 3: Preserve existing actions in the new context**

Ensure the following still work without backend changes:
- refresh
- add/edit shop account
- batch add shop account
- discover current shop
- toggle enabled
- delete

- [ ] **Step 4: Re-run focused UI tests**

Run:

```bash
node --test frontend/scripts/accountManagementGroupedViewUi.test.mjs frontend/scripts/accountManagementMainAccountNameUi.test.mjs frontend/scripts/accountManagementShopDiscoveryUi.test.mjs
```

Expected: PASS

## Task 4: Tighten Styles And Empty States

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`

- [ ] **Step 1: Add admin-console layout styles**

Introduce styles for:
- two-column page body
- navigator list items and active state
- summary panel
- empty-state panel
- responsive fallback when width is narrow

- [ ] **Step 2: Keep density appropriate for admin workflows**

Avoid decorative redesign. Prioritize:
- scan efficiency
- stable panel boundaries
- readable counts and states
- predictable action placement

- [ ] **Step 3: Verify helper and UI tests still pass**

Run:

```bash
node --test frontend/scripts/accountManagementGroupedViewUi.test.mjs frontend/scripts/accountManagementViewHelpers.test.mjs frontend/scripts/accountManagementMainAccountNameUi.test.mjs frontend/scripts/accountManagementShopDiscoveryUi.test.mjs
```

Expected: PASS

## Task 5: Full Verification

**Files:**
- Verify: `frontend/src/views/AccountManagement.vue`
- Verify: `frontend/src/utils/accountManagementView.js`
- Verify: `frontend/scripts/accountManagementGroupedViewUi.test.mjs`
- Verify: `frontend/scripts/accountManagementViewHelpers.test.mjs`
- Verify: `frontend/scripts/accountManagementMainAccountNameUi.test.mjs`
- Verify: `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`

- [ ] **Step 1: Run all focused account management tests**

Run:

```bash
node --test frontend/scripts/accountManagementGroupedViewUi.test.mjs frontend/scripts/accountManagementViewHelpers.test.mjs frontend/scripts/accountManagementMainAccountNameUi.test.mjs frontend/scripts/accountManagementShopDiscoveryUi.test.mjs frontend/scripts/accountManagementLegacyVisibilityUi.test.mjs
```

Expected: PASS

- [ ] **Step 2: Run frontend type/build verification**

Run:

```bash
npm run type-check
npm run build
```

Expected: PASS

- [ ] **Step 3: Manual behavior checklist**

Verify:
- filters affect grouped navigator and current table consistently
- selected main account remains stable across harmless filter changes
- selection falls back correctly when the current group disappears
- dialogs still open from the rebuilt page
- no-result states are understandable

## Implementation Notes

- Keep this change scoped to account management only.
- Do not redesign store contracts or account API endpoints.
- Prefer minimal state additions over rewriting the page into many new components.
- If template size grows too much, split only after the grouped helper is stable and tested.
