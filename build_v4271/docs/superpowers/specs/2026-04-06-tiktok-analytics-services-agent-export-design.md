# TikTok Analytics And Services Agent Export Design

**Date:** 2026-04-06

**Goal:** Add canonical TikTok `analytics` and `services/agent` export components by reusing the proven `products_export` runtime skeleton, while constraining both new flows to the custom-range date path and preserving clean downstream data-domain semantics.

## 1. Background

The current TikTok canonical export implementation already has one stable reference path:

- [products_export.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/products_export.py)

That component already solves the highest-risk runtime boundaries:

- entry-state detection
- page navigation
- main-account-owned shop switching
- custom date-range execution through the shared TikTok date picker
- final export handoff

New `pwcli` evidence has now been recorded for two additional TikTok flows:

- [analytics-export/evidence-pack.json](/F:/Vscode/python_programme/AI_code/xihong_erp/output/playwright/work/tiktok/analytics-export/evidence-pack.json)
- [services-export/evidence-pack.json](/F:/Vscode/python_programme/AI_code/xihong_erp/output/playwright/work/tiktok/services-export/evidence-pack.json)

The new work should not create a parallel TikTok export architecture. It should extend the existing canonical one.

## 2. Final Scope

This phase adds two canonical TikTok export components only:

- `tiktok/analytics_export`
- `tiktok/services_agent_export`

This phase explicitly does **not** add:

- a new generic `tiktok/services_export` canonical component
- a new standalone TikTok shop-switch implementation
- a new standalone TikTok export-helper family
- a second date-picker architecture for analytics or services pages

## 3. Domain And Naming Rules

## 3.1 Analytics

The analytics component uses:

- `data_domain = "analytics"`
- canonical component name: `tiktok/analytics_export`

This aligns with the current TikTok adapter capability model, where the former page-level "traffic" concept is normalized to `analytics`.

## 3.2 Services Agent

The service-side component must **not** be modeled as a generic `services_export`.

The final canonical semantics are:

- `data_domain = "services"`
- `sub_domain = "agent"`
- canonical component name: `tiktok/services_agent_export`

### Why

This avoids future downstream ambiguity such as:

- some platforms storing service exports under `services`
- other platforms storing the same logical data under `agent`

The system should preserve one stable hierarchy:

- domain says which business area the data belongs to
- sub-domain says which concrete branch inside that area was exported

## 4. Reuse Strategy

## 4.1 Products Export Is The Runtime Template

Both new components should reuse the same high-level orchestration shape as `TiktokProductsExport`:

1. detect entry state
2. block if still on login
3. navigate to the target page if needed
4. confirm / normalize `shop_region`
5. run shared shop switch
6. resolve date option from context
7. confirm or set date state
8. run export
9. validate export result

This keeps TikTok export components behaviorally aligned and easier to debug.

## 4.2 Shared Components To Reuse

The new components should continue reusing:

- [date_picker.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/date_picker.py)
- [shop_switch.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/shop_switch.py)
- [export.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/export.py)

No new TikTok-specific navigation or export base layer should be introduced unless current evidence proves that reuse is impossible.

## 5. Page Targets

## 5.1 Analytics

Analytics target page:

- `https://seller.tiktokshopglobalselling.com/compass/data-overview?shop_region=<REGION>`

Entry-state detection should treat `/compass/data-overview` as the ready state for this component.

## 5.2 Services Agent

Services agent target page:

- `https://seller.tiktokshopglobalselling.com/compass/service-analytics?shop_region=<REGION>`

Entry-state detection should treat `/compass/service-analytics` as the ready state for this component.

The recorded evidence indicates the exportable branch is the service page's `agent` path. The component should enter or confirm that branch before export.

## 6. Date Picker Strategy

## 6.1 Business Rule

Although both analytics and services pages show:

- daily
- weekly
- monthly
- custom

the canonical runtime should **not** use the daily / weekly / monthly shortcuts.

Both components should use:

- custom tab only
- explicit start date selection
- explicit end date selection

This is the intentional alignment with the already-mature products custom-range model.

## 6.2 Why Custom Only

The products flow already established the most complete and testable date model:

- start boundary and end boundary are explicit
- range confirmation is directly observable
- the executor can represent arbitrary date ranges without page-specific shortcut assumptions

Using custom-only behavior across TikTok exports reduces:

- page-specific branching
- preset-specific selector drift
- ambiguity between UI shortcut names and business granularity names

## 6.3 Expected Date-Picker Changes

The shared TikTok date-picker should gain or clarify one page-family branch:

- products page keeps its current custom-range behavior
- analytics page opens the picker, switches to `custom`, then uses start/end controls
- services page opens the picker, switches to `custom`, then uses start/end controls

The new analytics/services branch should still reuse the same final date-range confirmation contract:

- current visible range matches requested start / end dates

## 7. Export Semantics

## 7.1 Analytics Export

Analytics export should follow the standard TikTok export contract:

- export button must be found
- actual download should happen when the page has exportable data
- result should include `file_path`

Output metadata must preserve:

- `data_type = "analytics"`
- normalized granularity
- existing account / shop / region metadata

## 7.2 Services Agent Export

Services agent export must support two valid business outcomes:

1. **Exportable data exists**
   - export proceeds
   - file downloads successfully
   - result includes `file_path`

2. **No exportable data exists for the selected range**
   - export button appears disabled / grey
   - component returns a success-style business result indicating "no data to export"
   - this does **not** count as runtime failure

### Critical Rule

For `services_agent_export`, a disabled export button due to no data is a valid completed outcome, not an error.

This behavior must be encoded explicitly in the component rather than left as an accidental side effect of missing download handling.

## 7.3 Service Branch Preparation

The current TikTok shared export helper already contains service-page logic that enters the chat-detail branch before clicking export.

That branch-selection behavior should be preserved for the new `services_agent_export`, but the component itself must own the final semantic meaning:

- service domain
- agent sub-domain
- no-data-is-valid outcome

## 8. Output And Companion Metadata

All output paths and companion metadata must continue following the current export-base rules from:

- [base.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/components/export/base.py)

This means:

- no ad hoc output directory layout
- no one-off metadata sidecar format
- no platform-specific file naming divergence without a strong runtime reason

For the new components:

- `analytics_export` writes with `data_type="analytics"`
- `services_agent_export` writes with `data_type="services"` and explicit `subtype="agent"` when building standardized output roots or companion metadata

The final manifest / companion metadata must make the sub-domain explicit so downstream processing never has to infer whether a TikTok services export actually means the agent branch.

## 9. Error Handling

## 9.1 Shared Hard Failures

Both new components should fail when:

- runtime is still on login page
- target page cannot be reached
- target shop region cannot be confirmed
- requested date range cannot be confirmed
- export button should be available but cannot be found
- a real export path claims success but does not produce a file when one is expected

## 9.2 Services Agent Soft Success

Only `services_agent_export` gets this special business-success branch:

- disabled export button because the current range has no data

This branch should produce a clear non-error message, for example:

- `no exportable agent service data for selected range`

The exact message can be finalized during implementation, but the semantics must be stable.

## 10. Testing Strategy

Implementation must be test-first.

## 10.1 Analytics Export Tests

Add focused regression coverage for:

- entry-state detection on `/compass/data-overview`
- target navigation to analytics page
- shop switch reuse
- custom date path invocation
- successful export result propagation

## 10.2 Services Agent Export Tests

Add focused regression coverage for:

- entry-state detection on `/compass/service-analytics`
- agent-branch preparation
- custom date path invocation
- disabled export button returns valid non-failure outcome
- enabled export button triggers download and returns file path

## 10.3 Shared Date-Picker Tests

Extend TikTok date-picker tests to lock in:

- analytics page custom-tab entry
- services page custom-tab entry
- start-date then end-date selection path for these two pages

This must not regress the existing products-page date model.

## 11. Implementation Order

Recommended order:

1. add analytics and services-agent failing tests
2. add shared date-picker tests for analytics/services custom path
3. implement analytics export component
4. extend shared export / component logic for services-agent no-data handling
5. implement services-agent export component
6. run targeted TikTok export, date-picker, and shop-switch verification

## 12. Final Recommendation

The system should evolve TikTok exports as a single canonical family:

- one shared shop-switch model
- one shared date-picker model with page-family branches
- one shared export helper where possible
- thin domain-specific canonical export entries

The immediate deliverables should therefore be:

- `tiktok/analytics_export`
- `tiktok/services_agent_export`

And the system should intentionally avoid introducing a generic canonical `tiktok/services_export` entry in this phase.
