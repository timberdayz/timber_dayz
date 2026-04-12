# TikTok Export Download Boundary Design

**Date:** 2026-04-12

## Goal

Stabilize TikTok export completion detection by refactoring only the export-stage boundary, while preserving the current page navigation, shop switching, and date-picker behavior.

This design is intentionally narrower than a full TikTok export-family rewrite. The immediate target is the current failure mode:

- export click succeeds
- browser UI later shows download complete
- runtime returns failure because no valid `download` object or `file_path` was captured in time

## Problem Statement

Current TikTok export behavior is split incorrectly across the top-level domain components and the shared export helper:

- top-level components own page entry, shop normalization, and date preparation
- shared [`export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/export.py) still owns too much business behavior

This creates two specific stability problems:

1. `products` and `analytics` reach the shared exporter before the page is fully in an export-ready state.
2. the shared exporter assumes a single direct `page.expect_download(timeout=10000)` model, which is too narrow for real TikTok runtime timing

The result is a mismatch between browser reality and runtime reality:

- browser download manager says the file completed
- automation has already timed out and returned failure

## Constraints

- Do not redesign or replace TikTok navigation, shop switch, or date-picker behavior in this phase.
- Keep the current canonical top-level component names:
  - `tiktok/products_export`
  - `tiktok/analytics_export`
  - `tiktok/services_agent_export`
- Preserve the current repository gate contract for successful export:
  - `file_path` returned
  - file exists
  - file is non-empty
- Preserve the current valid no-data business outcome for `services_agent_export`.
- Do not restore `archive/` code wholesale. Reuse current canonical runtime and selectively recover proven boundary ideas only where needed.

## Observed Architectural Issue

TikTok already shows the same class of problem that Shopee is now addressing, but in a different shape.

Shopee's main risk is misleading inheritance.

TikTok's main risk is misleading shared orchestration.

Today:

- [`products_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/products_export.py) and [`analytics_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/analytics_export.py) are thin orchestrators that hand off export semantics almost entirely to shared [`export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/export.py)
- [`services_agent_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/services_agent_export.py) is more stable because it performs explicit readiness checks before export

This means TikTok has the same maintainability smell as Shopee:

- top-level components do not fully own their export-completion model
- shared code still carries business meaning that future agents can misread

## Options Considered

### Option A: Keep the current shared `TiktokExport` shape and only increase timeout

This is the smallest patch, but it does not correct the boundary problem.

Trade-offs:

- lowest immediate churn
- likely reduces some false failures
- still keeps services-specific and domain-sensitive logic inside the shared exporter
- future fixes will continue to pile into one misleading shared runtime

### Option B: Fully duplicate each TikTok export component into independent end-to-end implementations

This maximizes isolation, but it duplicates stable download-capture mechanics and output validation logic.

Trade-offs:

- strongest business isolation
- highest maintenance cost
- likely drift across TikTok domains
- unnecessary scope for the current problem, because page/date/shop boundaries are not the immediate root cause

### Option C: Keep current top-level components, standardize stage boundaries, and move shared export logic down to download primitives only

This preserves the current domain components and front-half flow while correcting the export-stage boundary.

Trade-offs:

- addresses the real failure mode directly
- does not disturb date-picker, shop-switch, or navigation semantics
- makes top-level components more explicit for future agents
- requires moderate refactor inside the export phase only

**Recommendation:** Option C.

## Design Summary

TikTok export components should adopt the same explicit stage contract as the proposed Shopee refactor, but this phase should only change the export-stage implementation details.

Every top-level TikTok export component should expose or clearly own these five stages:

1. `ensure_page_ready`
2. `ensure_shop_ready`
3. `ensure_date_ready`
4. `trigger_export`
5. `collect_download_result`

The important boundary rule is:

- existing page, shop, and date behavior may be reused as-is
- export trigger and download completion must no longer be hidden behind one shared high-level `TiktokExport.run()`

## Scope Boundary

This design changes only:

- export trigger ownership
- download capture ownership
- final file validation ownership
- export-related helper structure

This design does **not** change:

- TikTok deep-link target selection
- TikTok shop-region normalization logic
- TikTok date-option mapping
- TikTok date-picker selector strategy
- TikTok shop-switch selector strategy

That keeps risk concentrated in the exact problem area rather than reopening unrelated runtime surfaces.

## Target Architecture

## Top-Level Components

Keep the current top-level files and make each component explicitly own its export semantics:

- [`modules/platforms/tiktok/components/products_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/products_export.py)
- [`modules/platforms/tiktok/components/analytics_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/analytics_export.py)
- [`modules/platforms/tiktok/components/services_agent_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/services_agent_export.py)

Each component should call into shared helpers only for download primitives, not for domain-level export meaning.

## Shared Layer

Recommended new helper module:

- [`modules/platforms/tiktok/components/_download_helpers.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/_download_helpers.py)

Allowed shared primitives:

- adaptive download timeout resolution
- `page` plus `context` level download listener wiring
- listener cleanup
- `expect_download` wrapper
- save-to-target helper
- file existence and non-empty validation
- standard output root resolution
- optional manifest write helper
- common export diagnostic logging

Disallowed shared semantics:

- infer which domain-specific export button chain is correct
- infer whether service tab switching is required
- infer when a page is export-ready
- infer whether a retry should occur before or after page-specific confirmation
- hide the final success model inside one universal `run()` method

## Transitional Role Of `export.py`

[`modules/platforms/tiktok/components/export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/export.py) should stop acting as the shared business exporter.

Recommended transition:

1. keep the file temporarily for compatibility
2. move primitive download helpers out of it into `_download_helpers.py`
3. reduce `export.py` to a compatibility shim or retire it once all top-level components stop depending on its high-level `run()` behavior

This avoids a risky all-at-once file deletion while still changing the architecture in the right direction.

## Stage Contract

## `ensure_page_ready`

Responsibility:

- confirm the component is on the correct TikTok business page
- navigate if needed
- verify page-family readiness using existing current logic

Implementation rule:

- reuse current `products`, `analytics`, and `services_agent` page-entry logic
- do not change navigation semantics in this phase

## `ensure_shop_ready`

Responsibility:

- confirm `shop_region`
- run existing TikTok shop switch
- stop if shop normalization fails

Implementation rule:

- reuse current `_run_shop_switch()` flow
- do not redesign shop-switch heuristics in this phase

## `ensure_date_ready`

Responsibility:

- resolve date option from existing config semantics
- skip if current range already matches
- otherwise run existing date-picker and confirmation logic

Implementation rule:

- reuse current `_date_selection_already_satisfied`, `_run_date_picker`, and `_confirm_date_selection`
- do not redesign TikTok date-picker behavior in this phase

## `trigger_export`

Responsibility:

- perform only the domain-specific export click chain
- prepare any page-specific prerequisites needed immediately before export

Examples:

- `services_agent` may still need its agent-detail readiness flow before export
- `products` and `analytics` may require a domain-specific button readiness wait before clicking export
- if a domain uses a confirm dialog after clicking export, that click belongs here

This stage must not claim success. It only triggers the export path.

## `collect_download_result`

Responsibility:

- arm download listeners before the trigger
- await the correct browser download signal
- use fallback capture where needed
- save file into the standard output root
- validate file existence and non-empty size
- return final `file_path`

This stage owns the final success decision for export completion.

## Download Completion Model

TikTok should not currently be modeled as multiple Shopee-style completion modes such as `TASK_ROW_DOWNLOAD`.

Based on current evidence, all three active TikTok domains still converge on the same browser-level completion family:

- a browser download event should occur
- the runtime may need stronger listener and timeout handling to capture it reliably

So the immediate TikTok problem is not multiple completion families. It is one under-specified completion family.

Recommended explicit model for this phase:

- `BROWSER_DOWNLOAD_CAPTURE`

Applied to:

- `products`
- `analytics`
- `services_agent`

The domains differ in how export is triggered, not in how final file download should be validated.

## Specific Root Cause To Correct

Current shared export logic uses a fixed timeout:

- [`page.expect_download(timeout=10000)` in `export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/export.py#L142)

But collection entry points already pass larger export budgets such as `90000` or `240000` ms.

This mismatch means:

1. component times out first
2. browser finishes later
3. automation returns failure without `file_path`

The new shared primitive layer must therefore:

- consume `ctx.config["export_timeout_ms"]` when available
- default to a longer TikTok-safe timeout if no explicit config is present
- arm listeners before export click
- prefer captured valid file output over premature retry or failure

## Domain Responsibilities

### `products_export`

- own products-page readiness
- own products export-button readiness before click
- own products export trigger sequence
- use shared download capture primitives for final file resolution
- stop depending on `TiktokExport.run()` as the semantic export implementation

### `analytics_export`

- own analytics-page readiness
- own analytics export-button readiness before click
- own analytics export trigger sequence
- use shared download capture primitives for final file resolution
- stop depending on `TiktokExport.run()` as the semantic export implementation

### `services_agent_export`

- keep current stronger business readiness checks
- keep current valid no-data business outcome
- move final browser download capture onto shared primitives
- stop depending on `TiktokExport.run()` as the semantic export implementation

## Success Rules

## Hard Success

Export is successful only when:

- `file_path` is returned
- file exists
- file size is greater than zero

Browser event capture is a mechanism, not the source of truth.

## Soft Success

Only `services_agent_export` keeps this branch:

- page proves there is no exportable data
- component returns a successful business outcome with no file

This behavior remains domain-specific and must stay in the top-level component, not in the shared download helper layer.

## Retry Rule

Retry must be constrained.

A retry is allowed only when:

1. no valid `download` object was captured
2. no valid new file appeared in the expected output location or reconciliation window

If a valid file is already present, the component must stop and return success.

This prevents the browser-completed-but-runtime-failed mismatch from repeating.

## Testing Strategy

Required regression coverage:

1. `products` succeeds when download event arrives after a longer delay but within configured `export_timeout_ms`
2. `analytics` succeeds under the same delayed-download scenario
3. `services_agent` still succeeds with current no-data business path
4. `services_agent` still succeeds when exportable data produces a real file
5. `page` listener miss plus `context` listener hit still returns success
6. saved file must exist and be non-empty before success is returned
7. missing valid file still returns explicit export failure
8. current page/shop/date tests remain unchanged and continue to pass

## Migration Order

Recommended order:

1. add focused download-boundary tests for delayed download and context-listener fallback
2. introduce `_download_helpers.py`
3. migrate `services_agent_export` first to the new download primitives without changing its business rules
4. migrate `products_export` to explicit `trigger_export` plus `collect_download_result`
5. migrate `analytics_export` to the same boundary shape
6. reduce or retire `TiktokExport.run()` as a shared semantic exporter
7. run targeted TikTok component verification

## Final Recommendation

Do not widen this work into a TikTok-wide redesign.

For the current problem, the correct optimization is:

- preserve current page, shop, and date behavior
- make each top-level TikTok export component own the five explicit stages
- move shared logic down to download primitives only
- remove high-level export meaning from shared `TiktokExport`

This is the smallest change that directly fixes the browser-download-recognition problem without destabilizing unrelated component surfaces.
