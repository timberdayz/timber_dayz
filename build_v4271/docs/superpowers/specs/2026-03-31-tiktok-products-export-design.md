# TikTok Products Export Design

**Date:** 2026-03-31

## Goal

Define a canonical TikTok products-domain export component that uses the recorded `pwcli` evidence and current V2 helper components to export product-analysis data with a real downloaded file path.

## Current Canonical Position

The new formal entry should be:

- `modules/platforms/tiktok/components/products_export.py`

This file should be the products-domain export entry rather than extending the shared `export.py` forever.

## Evidence Baseline

This design is based on the captured TikTok evidence under:

- `output/playwright/work/tiktok/login-2store/`

Key products evidence:

- `32-products-data-picker-before.md`
- `33-products-data-picker-open.md`
- `35-products-data-picker-near28day-after.md`
- `38-products-export-before.md`
- `39-products-export-after.md`

These files confirm:

- the target page is `/compass/product-analysis`
- the page has a stable date control
- the page has a direct visible `导出` button
- the products page follows TikTok auto-download behavior after clicking export

## Scope

The new component should do four things only:

1. ensure the page is the TikTok products-analysis page
2. ensure the target `shop_region` is applied
3. optionally apply a supported quick-range date option
4. trigger export and return the real downloaded file path

## Reuse Strategy

Do not re-implement everything.

Reuse existing helpers:

- `modules/platforms/tiktok/components/shop_switch.py`
- `modules/platforms/tiktok/components/date_picker.py`
- `modules/platforms/tiktok/components/export.py`

The new file should be a thin canonical orchestrator for the `products` domain.

## Navigation Rule

`products_export.py` should treat `/compass/product-analysis?shop_region=<region>` as the canonical target page.

If the current page is not already the products page, the component should deep-link to that page first, then run `shop_switch` to normalize runtime context and `shop_name`.

## Date Rule

This first version should only use the quick-range options already supported by current evidence and current helper code:

- `LAST_7_DAYS`
- `LAST_28_DAYS`

Suggested mapping:

- `weekly` -> `LAST_7_DAYS`
- `monthly` -> `LAST_28_DAYS`

For `daily` or unknown values, do not invent unsupported custom-calendar behavior. Leave the current date untouched unless an explicit supported quick option is requested.

## Export Rule

Final success must mean:

- export click succeeded
- Playwright download event was observed
- file was saved to the standard output root
- returned result includes `file_path`

This component must not downgrade success to only `export triggered` when the page object supports downloads.

## Non-Goals

This design does not introduce:

- TikTok products custom-date calendar automation
- a new shared TikTok export base class
- archive restoration into active runtime

## Engineering Conclusion

`products_export.py` should be implemented now as a canonical orchestrator over the existing TikTok helpers, with real file-download success semantics and only evidence-backed date behavior.
