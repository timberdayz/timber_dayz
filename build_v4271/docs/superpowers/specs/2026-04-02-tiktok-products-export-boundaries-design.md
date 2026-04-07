# TikTok Products Export Boundaries Design

**Date:** 2026-04-02

## Goal

Redesign the TikTok products-domain export component with Shopee-grade operational boundaries while keeping TikTok page structure and control flow platform-specific.

The objective is not to copy Shopee selectors or UI assumptions. The objective is to reuse the mature execution logic:

- explicit entry-state detection
- page normalization before action
- shop-context normalization with confirmation
- date action separated from date confirmation
- export success defined by real download completion
- failure reasons classified by stage

## Why Redesign Instead Of Thin Reuse

The current TikTok `products_export` flow already exists, but it is still a thin orchestrator:

- deep-link to `/compass/product-analysis`
- rewrite `shop_region`
- optionally apply a simple date action
- trigger shared export

That is useful, but it is not yet equivalent to the mature Shopee products flow. For long-term component stability, the TikTok products component needs stronger runtime boundaries and a stricter date model.

## Evidence Baseline

This design is based on the recorded TikTok evidence under:

- `output/playwright/work/tiktok/login-2store/`
- `output/playwright/work/tiktok/tiktok-products-date/`

Relevant product-domain artifacts show:

- TikTok products page target is `/compass/product-analysis`
- the page exposes a visible shop-region context
- the page exposes a dual-page custom range picker
- the page exposes shortcut labels such as recent 7 / recent 28 days, but the same page also supports full custom range selection
- the picker remains usable as a day-grid range calendar without entering the year panel
- export is expected to produce a real downloaded file

## Scope

This version should cover:

1. entry-state detection
2. products-page normalization
3. shop-context normalization
4. unified time-semantic normalization into explicit date ranges
5. TikTok custom range execution for products pages
6. export trigger with real download result
7. failure classification and diagnostics

This version should not rely on TikTok shortcut buttons as the primary model.

## Recommended Architecture

Keep TikTok as a platform-specific implementation, but apply Shopee-grade runtime discipline.

Recommended component roles:

- `modules/platforms/tiktok/components/products_export.py`
  - canonical products-domain orchestrator
  - owns stage ordering, readiness checks, confirmation checks, and stage-specific failure messages
- `modules/platforms/tiktok/components/date_picker.py`
  - shared TikTok product date picker
  - upgraded from click helper to confirmed custom-range operator
- `modules/platforms/tiktok/components/shop_switch.py`
  - shared TikTok shop-context normalizer
  - upgraded from URL rewrite helper to context confirmation component
- `modules/platforms/tiktok/components/export.py`
  - shared TikTok export executor
  - remains responsible for export click and real download handling

## Runtime Flow

`TiktokProductsExport.run()` should execute in explicit stages:

1. Detect entry state
2. Normalize to products page
3. Normalize shop context
4. Normalize requested time semantics into `start_date` / `end_date`
5. Apply the custom range on the TikTok product picker
6. Confirm the top summary now matches the requested range
7. Trigger export
8. Confirm download and return `file_path`

Each stage must have its own success condition and failure message. A later stage must not run if an earlier stage has not been confirmed.

## Entry-State Design

TikTok should not branch only on URL. It should detect four practical entry states:

- `products`
- `homepage`
- `login`
- `unknown`

The decision should combine URL shape with visible page evidence:

- product page indicators
- real login inputs or stable login surface
- shop-region header signals

This is important because transient TikTok states may briefly look like login or blank-loading shells while the page is still recovering.

## Products-Page Normalization

Canonical destination:

- `https://seller.tiktokshopglobalselling.com/compass/product-analysis?shop_region=<region>`

If the current page is not already the products page:

- deep-link to the products page
- prefer carrying `shop_region` when known
- otherwise deep-link generically and recover region from account/page context afterward

Navigation completion should not be treated as sufficient by itself. The products page must also pass readiness checks before later stages proceed.

## Shop-Context Design

TikTok shop switching should remain TikTok-specific.

The stable strategy is still URL-based `shop_region` normalization, not Shopee-style shop-dropdown automation. But the component should no longer treat URL rewrite as success by itself.

Success requires:

- current URL contains the target `shop_region`
- page-level store or region display is consistent with that region
- `ctx.config` is updated with:
  - `shop_region`
  - `shop_name`
  - `shop_display_name` when available

This makes shop switching a context-confirmation step rather than only a transport step.

## Unified Time Semantics

TikTok product pages should use the same business time semantics as Shopee:

- `today`
- `yesterday`
- `last_7_days`
- `last_30_days`
- `daily`
- `weekly`
- `monthly`

TikTok does not need a separate business concept for `last_28_days`, even if the UI exposes that label. The external semantic model stays aligned with Shopee, and TikTok implements it through custom date ranges.

Examples for `2026-04-02`:

- `today` -> `2026-04-02 ~ 2026-04-02`
- `yesterday` -> `2026-04-01 ~ 2026-04-01`
- `last_7_days` -> `2026-03-27 ~ 2026-04-02`
- `last_30_days` -> `2026-03-04 ~ 2026-04-02`

## Date Picker Design

TikTok product pages should not be modeled around shortcut-button clicks. They should be modeled as a dual-page custom range picker that executes normalized time ranges.

The product date picker should separate these responsibilities:

1. identify whether the TikTok product range picker exists
2. open the range picker
3. read the currently visible left and right calendar months
4. navigate the left page to the start-date month using `< >` only
5. navigate the right page to the end-date month using `< >` only
6. select the start date on the left page
7. select the end date on the right page
8. confirm the collapsed page summary now matches the requested range

## Date Navigation Constraints

To reduce ambiguity and avoid fallback-heavy logic, the date model should enforce:

- start date must always be selected on the left page
- end date must always be selected on the right page
- left-page navigation uses `< >` month navigation only
- right-page navigation uses `< >` month navigation only
- the implementation must not click the header text to enter the year panel
- the implementation must not use `<< >>` year navigation in the primary implementation

This mirrors the Shopee principle of using a narrow, explicit model rather than broad fallback heuristics. If the strict model cannot reach the target state, the operation should fail clearly instead of guessing.

## Date Confirmation Signals

The date action is not complete when the clicks succeed. It is complete only when the resulting page state is confirmed.

Preferred confirmation signals, in order:

1. collapsed top summary text matches the normalized `start_date` / `end_date`
2. panel closes after the second date is selected
3. reopened panel visually highlights the same range

If the date clicks complete but the collapsed summary does not match the requested range within the allowed wait window, the operation should fail as `date state not confirmed`.

## Export Design

Export success must be defined by real download completion.

Valid success requires:

- export control found
- click succeeds
- Playwright download event is observed
- file is written to the standard output root
- result contains a real `file_path`

The products orchestrator should not downgrade success to only `export triggered` when download-capable page objects are available.

## Failure Classification

Failures should be explicit and stage-scoped. At minimum:

- `login required before products export`
- `products page not ready`
- `shop switch failed`
- `date picker open failed`
- `date range apply failed`
- `date state not confirmed`
- `export button not found`
- `download not observed`

This is valuable both for test clarity and for later `pwcli + agent` debugging loops.

## Testing Design

The redesign should be driven by tests that verify boundaries, not only delegation.

### Products Export Tests

- entry-state detection does not misclassify transient login shells
- non-products entry deep-links to canonical products page
- shop normalization failure stops the flow before export
- current range already satisfied causes the date stage to skip
- custom range execution waits for confirmation
- missing confirmation prevents export
- export returns real `file_path`
- missing export button or missing download returns explicit failure

### Date Picker Tests

- normalized `today / yesterday / last_7_days / last_30_days` resolve to explicit date ranges
- the product picker opens into a dual-page day-grid calendar
- left-page month can be read accurately
- right-page month can be read accurately
- left-page month can be navigated to the start month using `< >` only
- right-page month can be navigated to the end month using `< >` only
- start date is selected only on the left page
- end date is selected only on the right page
- summary confirmation matches the requested range
- no logic depends on clicking the header text to enter the year panel

### Shop Switch Tests

- URL rewrite preserves path and unrelated query params
- target region is confirmed from page state, not only URL
- normalized context is written back into `ctx.config`
- inconsistent page region signals fail clearly instead of succeeding silently

## Non-Goals

This redesign does not include:

- shortcut-button-first TikTok date modeling
- header-click year-panel navigation in the primary implementation
- `<< >>` year navigation in the primary implementation
- premature extraction of a cross-platform shared products export base
- copying Shopee selectors or UI widgets into TikTok

## Engineering Conclusion

TikTok products export should be rebuilt as a mature TikTok-specific orchestrator that reuses Shopee's operational logic but not Shopee's page assumptions.

The first implementation focus should be:

- stronger entry-state handling
- stronger shop-context confirmation
- shared time-semantic normalization into explicit ranges
- dual-page custom-range execution with left-start / right-end discipline
- summary-based confirmation after range selection
- real download-based export success
