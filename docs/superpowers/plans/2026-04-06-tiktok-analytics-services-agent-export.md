# TikTok Analytics And Services Agent Export Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement canonical TikTok `analytics_export` and `services_agent_export` components by reusing the stable `products_export` flow, adding analytics/services custom-date handling, and preserving clean services-agent output semantics.

**Architecture:** Keep TikTok exports as one canonical family. Add two thin domain-specific export entry components, extend the shared TikTok date-picker with analytics/services custom-tab behavior, and extend shared export behavior only where the service-agent no-data branch requires it. Do not add a generic `services_export` entry in this phase.

**Tech Stack:** Python async components, Playwright async runtime, existing TikTok canonical components, pytest, component-registration discovery by canonical filename

---

## File Structure

### New files to create

- `modules/platforms/tiktok/components/analytics_export.py`
  Responsibility: canonical TikTok analytics export entry that mirrors the products export skeleton but targets `data-overview`.
- `modules/platforms/tiktok/components/services_agent_export.py`
  Responsibility: canonical TikTok services-agent export entry that targets `service-analytics`, preserves `data_domain=services`, and fixes the branch to `sub_domain=agent`.
- `backend/tests/test_tiktok_analytics_export_component.py`
  Responsibility: lock analytics entry detection, navigation, date handling, and export behavior.
- `backend/tests/test_tiktok_services_agent_export_component.py`
  Responsibility: lock services-agent entry detection, custom-date handling, no-data success semantics, and export behavior.

### Existing files to modify

- `modules/platforms/tiktok/components/date_picker.py`
  Responsibility: add or clarify analytics/services page-family custom-tab handling while preserving the current products-page state machine.
- `modules/platforms/tiktok/components/export.py`
  Responsibility: support any shared analytics/services export adjustments that are truly common, including service-page branch preparation and optional no-data detection if shared handling is justified.
- `backend/tests/test_tiktok_date_picker_component.py`
  Responsibility: add regression coverage for analytics/services custom-tab entry and explicit start/end range selection.
- `backend/tests/test_tiktok_export_component.py`
  Responsibility: lock shared TikTok export-helper behavior, especially service-page branch preparation and any no-data-result contract that is implemented at the helper layer.
- `backend/tests/test_component_versions_canonical_registration.py`
  Responsibility: verify canonical discovery and registration include the new TikTok export entry filenames.

### Existing files to inspect during implementation

- `modules/platforms/tiktok/components/products_export.py`
- `modules/platforms/tiktok/components/shop_switch.py`
- `modules/components/export/base.py`
- `tools/test_component.py`
- `modules/apps/collection_center/executor_v2.py`

The last two files should only be modified if tests prove that a successful no-data services-agent result needs explicit runtime handling when `file_path` is absent.

---

## Task 1: Lock Component Contracts With Failing Tests

**Files:**
- Create: `backend/tests/test_tiktok_analytics_export_component.py`
- Create: `backend/tests/test_tiktok_services_agent_export_component.py`
- Modify: `backend/tests/test_component_versions_canonical_registration.py`

- [ ] **Step 1: Write the failing analytics export tests**

Cover:

- entry-state detection on `/compass/data-overview`
- navigation from homepage to analytics page
- shop-switch reuse
- custom-range date flow invocation
- successful export result propagation

- [ ] **Step 2: Write the failing services-agent export tests**

Cover:

- entry-state detection on `/compass/service-analytics`
- fixed services-agent semantics (`data_domain=services`, agent branch)
- custom-range date flow invocation
- disabled export button due to no data returns a valid completed outcome
- enabled export button still returns a real downloaded file

- [ ] **Step 3: Extend canonical registration coverage**

Add a focused registration/discovery assertion that canonical TikTok export filenames include:

- `tiktok/analytics_export`
- `tiktok/services_agent_export`

- [ ] **Step 4: Run the focused tests and verify failure**

Run:

```powershell
pytest backend/tests/test_tiktok_analytics_export_component.py backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_component_versions_canonical_registration.py -q
```

Expected:

- FAIL because the new component files do not exist yet
- FAIL because registration coverage does not yet include the new entries

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/test_tiktok_analytics_export_component.py backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_component_versions_canonical_registration.py
git commit -m "test: add tiktok analytics and services agent export contracts"
```

## Task 2: Extend Shared Date Picker For Analytics And Services Custom Path

**Files:**
- Modify: `modules/platforms/tiktok/components/date_picker.py`
- Modify: `backend/tests/test_tiktok_date_picker_component.py`

- [ ] **Step 1: Write the failing date-picker tests**

Cover:

- analytics page opens the date picker and moves to the custom tab
- services page opens the date picker and moves to the custom tab
- analytics/services start and end range selection uses explicit boundary flow
- products-page behavior remains unchanged

- [ ] **Step 2: Run the focused date-picker tests and verify failure**

Run:

```powershell
pytest backend/tests/test_tiktok_date_picker_component.py -q
```

Expected: FAIL on the new analytics/services custom-path assertions.

- [ ] **Step 3: Implement the minimal date-picker extension**

Add or refactor only what is needed so:

- `_page_kind()`-driven analytics/services logic is explicit
- daily / weekly / monthly tabs are observable but not used as runtime selection targets
- custom-tab entry is required before start/end date interaction
- confirmation still relies on visible applied start/end state

Do not rewrite the products-page dual-calendar state machine unless the new tests force a shared refactor.

- [ ] **Step 4: Re-run the focused date-picker tests**

Run:

```powershell
pytest backend/tests/test_tiktok_date_picker_component.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add modules/platforms/tiktok/components/date_picker.py backend/tests/test_tiktok_date_picker_component.py
git commit -m "feat: support analytics and services custom date path"
```

## Task 3: Implement Analytics Export As A Thin Canonical Entry

**Files:**
- Create: `modules/platforms/tiktok/components/analytics_export.py`
- Modify: `backend/tests/test_tiktok_analytics_export_component.py`

- [ ] **Step 1: Implement the minimal analytics export component**

Mirror `products_export.py`, but change only the domain-specific parts:

- target page URL -> `/compass/data-overview`
- ready-state detection -> analytics page
- canonical `data_domain = "analytics"`
- output semantics -> analytics

Preserve:

- login-required failure
- shared shop-switch reuse
- shared date-picker reuse
- shared export reuse

- [ ] **Step 2: Run the focused analytics tests**

Run:

```powershell
pytest backend/tests/test_tiktok_analytics_export_component.py -q
```

Expected: PASS

- [ ] **Step 3: Commit**

```powershell
git add modules/platforms/tiktok/components/analytics_export.py backend/tests/test_tiktok_analytics_export_component.py
git commit -m "feat: add tiktok analytics export component"
```

## Task 4: Implement Services Agent Export And No-Data Success Semantics

**Files:**
- Create: `modules/platforms/tiktok/components/services_agent_export.py`
- Modify: `modules/platforms/tiktok/components/export.py`
- Modify: `backend/tests/test_tiktok_services_agent_export_component.py`
- Modify: `backend/tests/test_tiktok_export_component.py`

- [ ] **Step 1: Write or extend failing shared-export tests**

Lock whichever shared behavior is actually needed:

- service-page branch preparation before export
- disabled export button detection when the service-agent page has no exportable data
- subtype-aware standardized output handling if implemented in the shared helper

- [ ] **Step 2: Run the focused services/export tests and verify failure**

Run:

```powershell
pytest backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_tiktok_export_component.py -q
```

Expected: FAIL until no-data success handling and services-agent semantics exist.

- [ ] **Step 3: Implement the minimal shared export/helper changes**

Only add shared behavior if it is truly common. Preferred split:

- `services_agent_export.py` owns domain/sub-domain semantics and business result interpretation
- `export.py` owns only page-level export interaction helpers that are genuinely shared

If no-data detection must live in the shared helper, keep it opt-in or service-specific rather than changing analytics/products semantics.

- [ ] **Step 4: Implement the services-agent component**

Required behavior:

- target page `/compass/service-analytics`
- canonical `data_domain = "services"`
- canonical `sub_domain = "agent"`
- service-agent branch preparation before export
- no-data disabled export button returns a valid non-failure result
- real export still returns `file_path` when data exists

- [ ] **Step 5: Re-run the focused services/export tests**

Run:

```powershell
pytest backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_tiktok_export_component.py -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```powershell
git add modules/platforms/tiktok/components/services_agent_export.py modules/platforms/tiktok/components/export.py backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_tiktok_export_component.py
git commit -m "feat: add tiktok services agent export component"
```

## Task 5: Verify Runtime Compatibility For Success Without File Output

**Files:**
- Inspect: `tools/test_component.py`
- Inspect: `modules/apps/collection_center/executor_v2.py`
- Modify only if required by tests

- [ ] **Step 1: Add a focused regression test only if needed**

If the current runtime assumes every successful export must return a `file_path`, add the narrowest failing test that proves `services_agent_export` no-data completion should not be treated as a component failure.

- [ ] **Step 2: Run the narrow runtime test if one is added**

Run the exact focused pytest target you added.

Expected: FAIL only if the current runtime contract is too strict.

- [ ] **Step 3: Implement the minimal compatibility fix only if required**

Possible acceptable fix directions:

- treat a successful export result with a domain-specific no-data message as a completed no-file outcome
- preserve current behavior for all other export components

Do not broaden export semantics across the whole platform family unnecessarily.

- [ ] **Step 4: Re-run the runtime compatibility test**

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add tools/test_component.py modules/apps/collection_center/executor_v2.py <new-runtime-test-if-added>
git commit -m "fix: allow tiktok services agent no-data export completion"
```

## Task 6: Full TikTok Verification

**Files:**
- Verify only

- [ ] **Step 1: Run TikTok targeted pytest suite**

Run:

```powershell
pytest backend/tests/test_tiktok_analytics_export_component.py backend/tests/test_tiktok_services_agent_export_component.py backend/tests/test_tiktok_export_component.py backend/tests/test_tiktok_date_picker_component.py backend/tests/test_tiktok_shop_switch_component.py backend/tests/test_tiktok_products_export_component.py backend/tests/test_component_versions_canonical_registration.py -q
```

Expected: PASS

- [ ] **Step 2: Run Python compile verification**

Run:

```powershell
python -m py_compile modules/platforms/tiktok/components/analytics_export.py modules/platforms/tiktok/components/services_agent_export.py modules/platforms/tiktok/components/export.py modules/platforms/tiktok/components/date_picker.py
```

Expected: no output, exit 0

- [ ] **Step 3: Review discovery surface**

Run:

```powershell
python - <<'PY'
from backend.services.active_collection_components import list_active_component_names
print([n for n in list_active_component_names() if n.startswith("tiktok/")])
PY
```

Expected: output includes:

- `tiktok/analytics_export`
- `tiktok/services_agent_export`

- [ ] **Step 4: Commit final verification-only follow-up if needed**

If no code changed in this step, do not create an empty commit.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-06-tiktok-analytics-services-agent-export.md`. Ready to execute?
