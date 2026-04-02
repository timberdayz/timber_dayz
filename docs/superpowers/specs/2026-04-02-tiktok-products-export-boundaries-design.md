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
- optionally apply a quick date option
- trigger shared export

That is useful, but it is not yet equivalent to the mature Shopee products flow. For long-term component stability, the TikTok products component needs stronger runtime boundaries and confirmation signals.

## Evidence Baseline

This design is based on the recorded TikTok evidence under:

- `output/playwright/work/tiktok/login-2store/`

Relevant product-domain artifacts:

- `32-products-data-picker-before.md`
- `33-products-data-picker-open.md`
- `34-products-data-picker-near7day-open.md`
- `35-products-data-picker-near7day-after.md`
- `35-products-data-picker-near28day-open.md`
- `35-products-data-picker-near28day-after.md`
- `36-products-data-picker-custom-open.md`
- `37-products-data-picker-custom-after.md`
- `38-products-export-before.md`
- `39-products-export-after.md`

These artifacts support the following facts:

- TikTok products page target is `/compass/product-analysis`
- the page exposes a visible shop-region context
- the page exposes a date control and quick date options
- the page exposes an export action
- export is expected to produce a real downloaded file

## Scope

This version should cover:

1. entry-state detection
2. products-page normalization
3. shop-context normalization
4. quick-date execution with confirmation
5. export trigger with real download result
6. failure classification and diagnostics

This version should not implement custom-date selection logic, but it must reserve a clear interface for it.

## Recommended Architecture

Keep TikTok as a platform-specific implementation, but apply Shopee-grade runtime discipline.

Recommended component roles:

- `modules/platforms/tiktok/components/products_export.py`
  - canonical products-domain orchestrator
  - owns stage ordering, readiness checks, confirmation checks, and stage-specific failure messages
- `modules/platforms/tiktok/components/date_picker.py`
  - shared TikTok date picker
  - upgraded from click helper to confirmed quick-date operator
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
4. Resolve requested date behavior
5. Apply quick date if needed
6. Confirm target date state
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

## Date Picker Design

This first mature TikTok version supports quick date options only.

Supported mappings:

- `weekly -> LAST_7_DAYS`
- `monthly -> LAST_28_DAYS`

For `daily` or explicit custom requests:

- do not attempt unsupported custom-date selection
- expose a clear interface and state path for later implementation

The date picker should separate four responsibilities:

1. identify whether the shared TikTok products date control exists
2. open the date panel
3. execute the target quick option
4. confirm the page has reached the target date state

The last step is the key Shopee-derived discipline.

## Date Confirmation Signals

The date action is not complete when the click succeeds. It is complete only when the resulting page state is confirmed.

Preferred confirmation signals, in order:

1. summary text or trigger text matches the target quick date state
2. quick option shows active or selected state
3. panel closes and the visible trigger settles on the expected range text

If the click succeeds but no confirmation signal appears within the allowed wait window, the operation should fail as `date state not confirmed`.

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
- `date option apply failed`
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
- already-satisfied quick date skips redundant execution
- quick-date execution waits for confirmation
- missing confirmation prevents export
- export returns real `file_path`
- missing export button or missing download returns explicit failure

### Date Picker Tests

- products page date control can be found and opened
- `LAST_7_DAYS` applies successfully
- `LAST_28_DAYS` applies successfully
- already-active target option can be recognized and skipped
- click without confirmation fails clearly
- custom-date requests remain unsupported but explicit

### Shop Switch Tests

- URL rewrite preserves path and unrelated query params
- target region is confirmed from page state, not only URL
- normalized context is written back into `ctx.config`
- inconsistent page region signals fail clearly instead of succeeding silently

## Non-Goals

This redesign does not include:

- TikTok custom-date selection automation
- premature extraction of a cross-platform shared products export base
- copying Shopee selectors or UI widgets into TikTok

## Engineering Conclusion

TikTok products export should be rebuilt as a mature TikTok-specific orchestrator that reuses Shopee's operational logic but not Shopee's page assumptions.

The first implementation focus should be:

- stronger entry-state handling
- stronger shop-context confirmation
- quick-date execution with explicit confirmation
- real download-based export success
- future-ready hooks for custom-date support
