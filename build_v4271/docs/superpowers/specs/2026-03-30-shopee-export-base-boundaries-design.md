# Shopee Export Base Boundaries Design

**Date:** 2026-03-30

## Goal

Define what the current canonical `products_export.py` can legitimately serve as a Shopee export base for, and what must remain data-domain-specific when later building `services`, `analytics`, `orders`, or `finance` exports.

This document prevents two failure modes:

1. treating `archive/` implementations as runtime components
2. over-generalizing `products_export.py` into a fake "universal Shopee exporter"

## Current Canonical Entry

The only active Shopee export component in the new system is:

- `modules/platforms/shopee/components/products_export.py`

`archive/` files are reference-only and must not be restored into `components/` as runtime entries.

## Evidence Baseline

The current boundary decisions are based on the captured `pwcli` evidence under:

- `output/playwright/work/shopee/products-export/`

Key evidence files:

- `3-shop-switch-open.md`
- `4-shop-switch-step2-open.md`
- `5-shop-switch-after.md`
- `8-date-picker-before.md`
- `9-date-picker-open.md`
- `13-date-picker-after.md`
- `14-export-before.md`
- `15-export-after.md`
- `16-export-too-fast-open.md`
- `16-export-too-fast-after.md`

## What Is Reusable Across Shopee Data Domains

These behaviors are stable enough to be treated as Shopee-wide export base behavior.

### 1. Region + Shop Selection Semantics

Shop selection is not just "pick a shop name".

The runtime must model:

1. current region/shop display
2. opening the shop selector
3. selecting the expected region when required
4. selecting the expected shop
5. waiting until the top display value actually changes to the expected region/shop

This semantic is reusable, even if individual selectors later differ by page.

### 2. Summary-Bar-Driven Time Validation

The most stable date success signal is not the internal date panel DOM.

The reusable success signal is the visible summary bar value near `统计时间`.

This means later Shopee exports should prefer:

- detect current visible date summary
- only open the date control if the current value is wrong
- verify success by the updated summary text

### 3. Export Post-Action State Skeleton

After clicking export, Shopee pages cannot be assumed to immediately produce a download.

The base state machine should always allow at least:

- `download_started`
- `throttled`
- `unknown`

Later data domains may extend this with task-list or dialog states, but they should not remove these base states.

### 4. Final Success Criterion

Formal export success remains:

- file actually lands on disk
- file is non-empty

This is reusable across all Shopee export components.

## What Must Stay Data-Domain-Specific

These parts must not be prematurely abstracted into a shared generic exporter.

### 1. Page Ready Detection

Each data domain has its own:

- URL pattern
- title or tab structure
- primary ready probes
- empty/unsupported/404 states

`products_export.py` page-ready logic cannot be copied verbatim into `services`, `analytics`, `orders`, or `finance`.

### 2. Navigation Path

Even inside Shopee `商业分析`, the actual click path into each data domain may differ.

The base may provide the idea of "enter domain page", but not one fixed domain navigation implementation.

### 3. Date Mapping Semantics

The current `products_export.py` now maps:

- `daily -> 昨天`
- `weekly -> 过去7天`
- `monthly -> 过去30天`

This mapping is validated only against the current products-page evidence.

Other domains must prove their own mapping by evidence before reusing it.

### 4. Export Trigger Structure

Different Shopee data domains may use different export mechanics:

- direct visible export button
- more-menu entry
- confirmation dialog
- export task generation
- latest-row download
- unsupported/SIP/permission-denied branch

These must stay domain-specific until evidence proves convergence.

### 5. Throttling And Retry Behavior

`products_export.py` currently models a minimal throttling retry path.

Other domains may:

- throttle differently
- require longer task waits
- produce retryable task rows instead of direct download

Do not assume one retry implementation fits all Shopee domains.

## Practical Rule For Future Shopee Components

When building a new Shopee export domain:

1. start from the canonical structure of `products_export.py`
2. reuse only these stable concepts:
   - region + shop semantics
   - summary-bar-driven date verification
   - export post-action state skeleton
   - file-on-disk success rule
3. replace these per domain:
   - page ready detection
   - domain navigation
   - date label mapping if evidence differs
   - export trigger and completion branches

## Explicit Non-Goals

This design does not introduce:

- a shared `ShopeeBaseExport` class
- a generic unified Shopee exporter
- restoration of `archive/` code into active runtime

If such abstraction is attempted later, it must be justified by evidence from at least two active Shopee data domains, not by archive similarity.

## Current Engineering Conclusion

`products_export.py` should be treated as:

- the current canonical Shopee export sample
- a source of reusable behavior patterns
- not a universal Shopee exporter

Future Shopee export work should evolve from this file by evidence-driven adaptation, not by archive restoration and not by premature generalization.
