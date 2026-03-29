# Shopee Business Analysis Common Flow Design

**Date:** 2026-03-29

## Goal

Define a single reusable Shopee business-analysis flow for `products_export`, `services_export`, and `analytics_export` so that later component work reuses the same navigation, shop switch, and date selection logic instead of re-recording ad hoc page-specific scripts.

## Business Flow

Shopee business-analysis exports follow this runtime order:

1. Reach the Shopee seller homepage.
2. Enter the `商业分析` area.
3. Select the target shop.
4. Enter one of the business-analysis data-domain pages:
   - `商品`
   - `服务`
   - `流量`
5. Select time:
   - preset shortcuts:
     - `今日实时`
     - `昨天`
     - `过去7天`
     - `过去30天`
   - granularity-based selection:
     - `按日`
     - `按周`
     - `按月`
6. Click `导出数据`.
7. Treat automatic file download completion as the export success signal.

## Domain Differences

### Products

- Uses the standard business-analysis path.
- Supports preset shortcuts and day/week/month granularity choices.
- Export is a direct automatic-download path after clicking `导出数据`.

### Services

- Reuses the same business-analysis container flow.
- Expected to share the same shop-switch and date-picker behavior unless later evidence shows otherwise.

### Analytics

- Reuses the same business-analysis container flow.
- Does **not** support `今日实时`.
- Must restrict allowed presets to:
  - `昨天`
  - `过去7天`
  - `过去30天`

## Component Boundaries

### navigation

Responsibility:
- enter `商业分析`
- move from the business-analysis landing page into the target domain page

Must not own:
- shop selection
- date selection
- export clicking

Recommended API shape:
- input: `data_domain`
- success signal: URL and page title/features match the target domain page

### shop_switch

Responsibility:
- open the shop selector
- select the target shop
- verify the selected shop is now active

Success signal:
- current shop label changes to target shop
- page context refreshes under the same business-analysis workspace

### date_picker

Responsibility:
- open the business-analysis date picker
- select either:
  - a preset shortcut, or
  - a day/week/month granularity option
- verify the page reflects the requested time range

Must support:
- `preset`
- `granularity`
- domain-specific preset restrictions

Special rule:
- `analytics` must reject `today_realtime`

### domain export component

Responsibility:
- ensure target domain page is active
- call reusable `shop_switch`
- call reusable `date_picker`
- click `导出数据`
- wait for automatic download completion
- handle throttling/too-fast warnings if they appear

Must not duplicate:
- generic shop-switch logic
- generic date-picker logic

## Shared Runtime Parameters

Recommended shared runtime inputs:

- `data_domain`
  - `products`
  - `services`
  - `analytics`
- `time_mode`
  - `preset`
  - `granularity`
- `preset`
  - `today_realtime`
  - `yesterday`
  - `last_7_days`
  - `last_30_days`
- `granularity`
  - `daily`
  - `weekly`
  - `monthly`

## Detection Helpers

### navigation helpers

- `detect_business_analysis_entry(page)`
- `ensure_business_analysis_home(page)`
- `ensure_business_domain_page(page, data_domain)`

### shop switch helpers

- `detect_shop_switch_trigger(page)`
- `wait_shop_switch_panel_open(page)`
- `detect_current_shop(page)`
- `ensure_shop_selected(page, target_shop)`

### date picker helpers

- `detect_date_picker_trigger(page)`
- `wait_date_picker_open(page)`
- `select_date_preset(page, preset, data_domain)`
- `select_date_granularity(page, granularity)`
- `ensure_date_range_selected(page, expected_mode, expected_value, data_domain)`

### export helpers

- `detect_export_button_ready(page)`
- `trigger_export(page)`
- `detect_export_throttled(page)`
- `wait_export_retry_ready(page)`
- `wait_download_complete(page)`

## Rules For Later Component Work

- Do not treat Shopee `products_export`, `services_export`, and `analytics_export` as unrelated scripts.
- Reuse the same common flow and only move domain-specific differences into config/helper branches.
- Keep `shop_switch` and `date_picker` reusable first; if needed, keep them as internal helpers before promoting them into independent top-level components.
- Treat file download completion as the primary success criterion, not the click itself.
