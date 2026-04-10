# Shopee Latest Report Row Binding Design

**Date:** 2026-04-10

## Goal

Fix the Shopee `products` and `services/agent` export flow so that after an export action completes, the runtime clicks the download button for the report row produced by the current export, not an older undownloaded row already present in the dialog.

## Evidence Baseline

The design is based on recorded `pwcli` / screenshot evidence:

- `output/playwright/work/shopee/product-export/14-product-download-open.png`
- `output/playwright/work/shopee/product-export/15-product-download-click-before.png`
- `output/playwright/work/shopee/services-export/18-services-agent-download-cklick-before.png`

Observed structure from the real pages:

1. The export icon opens a `latest report` dialog.
2. Historical undownloaded reports and the current export report can coexist in the same list.
3. Each row has the same right-side orange `download` button.
4. The badge count only signals undownloaded files exist; it does not identify the row belonging to the current export.
5. Report filenames visibly include both a business prefix and a date-range signature, for example:
   - `parentskudetail.20260101_20260131.xlsx`
   - `chat_20260401_20260401.xlsx`

## Root Cause

The active canonical components do not bind the chosen download button to a report row identity created by the current export action.

Current behavior in active runtime code:

- locate the visible `latest report` panel
- scan the panel for the first action text that looks like `download` or `processing`
- click the first matching download button when it appears

That strategy only proves the button is currently clickable. It does not prove the button belongs to the current export record.

When an older undownloaded row already exists, this abstraction is unsafe and can download the wrong time range.

## Non-Goals

This design does not:

- restore `archive/` runtime code
- build a universal Shopee exporter
- change export trigger behavior outside the post-export report-selection step
- depend on notification badge counts as a source of truth

## Design Summary

Replace `top report button` selection with `target report row` selection.

The runtime should:

1. capture a baseline snapshot of report rows before triggering export when the panel is available
2. trigger export
3. reopen or poll the `latest report` dialog
4. identify the row that belongs to the current export by row identity rather than button position
5. click the download button inside that specific row

## Row Identity Strategy

### Primary signal: filename signature

The preferred row identity is the visible report filename text.

For the current export request, derive expected signatures from:

- data-domain prefix
- configured date range

Examples:

- `products`: expect a row containing a products filename prefix and `YYYYMMDD_YYYYMMDD`
- `services/agent`: expect a row containing an agent/chat filename prefix and `YYYYMMDD_YYYYMMDD`

If a row filename matches the expected signature and exposes a visible `download` button, that row should win even if older undownloaded rows remain above or below it.

### Secondary signal: new row relative to baseline

If the exact filename prefix is not available or differs slightly across locales, compare the post-export row texts against the pre-export baseline snapshot.

Preferred ordering:

1. new row text not present in baseline
2. row that changed from `processing` to `download`
3. fallback to first visible row only if no stronger signal is available

### Tertiary signal: processing-to-download transition

If the current export first appears as `processing`, keep polling the same matching row until its status becomes `download`.

This preserves row identity across the generation window instead of rescanning globally and accidentally switching to an older row.

## Runtime Shape

### Products component

Modify `modules/platforms/shopee/components/products_export.py` so that it owns:

- report-row text normalization
- expected report signature building from current config
- baseline row snapshot capture
- target row selection and polling

The existing `_wait_top_report_download_button()` helper should be replaced or redirected to a row-based helper:

- wait for panel
- enumerate rows
- resolve target row
- return the download button within that row only

### Services agent component

`modules/platforms/shopee/components/services_export_base.py` should reuse the same row-based idea, with subtype-specific filename prefix matching.

`modules/platforms/shopee/components/services_agent_export.py` should continue to rely on the shared base logic rather than implementing another ad-hoc button scan.

## Row Matching Rules

### Shared rules

- ignore rows with empty text
- normalize whitespace
- normalize filename separators conservatively
- detect `download`, `processing`, and `downloaded` states from row text
- only click buttons inside the chosen row

### Products rules

- prefer rows whose text contains a product-export filename prefix
- require the configured date signature when available

### Services agent rules

- prefer rows whose text matches the `agent` subtype signature
- require the configured date signature when available
- do not treat any random downloadable row as valid merely because it is visible

## Error Handling

If no target row can be identified confidently:

- continue polling while timeout budget remains
- keep the panel open if possible
- do not click a generic global download button as an early fallback

If timeout expires:

- fail with an explicit message that no current-export report row was identified
- let the higher-level file-system or API fallback logic remain unchanged

## Testing Strategy

Regression coverage must prove the original bug.

Add tests that simulate:

1. one old undownloaded row plus one new processing row that later becomes downloadable
2. one old undownloaded row plus one new downloadable row with the current date signature
3. only old undownloaded rows and no current-export row

Assertions must verify:

- the selected button belongs to the intended row
- the old row is not clicked
- timeout behavior is explicit when no matching row appears

## Engineering Conclusion

The correct abstraction boundary is:

- not `first downloadable action in latest-report panel`
- but `download action inside the report row bound to the current export`

That boundary matches the real Shopee page structure and addresses the exact class of bug seen in live testing.
