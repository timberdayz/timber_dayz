# Store Analysis Redesign

## Goal

Rebuild the deprecated store analysis module as a PostgreSQL-first drill-down page for cross-border e-commerce operations, reusing the active dashboard chain instead of reviving the removed `/store-analytics/*` path.

The rebuilt page must answer one business question clearly:

```text
For a selected store and period, what happened, why did it happen, and what should the operator look at next?
```

## Architecture Baseline

The module must stay on the active runtime path:

`b_class raw -> semantic -> mart -> api -> backend router -> frontend`

Relevant anchors in the current repository:

- Raw ingest: `backend/services/data_ingestion_service.py`
- Raw JSONB persistence: `backend/services/raw_data_importer.py`
- Analytics semantic view: `sql/semantic/analytics_atomic.sql`
- Existing store-level mart: `sql/mart/shop_day_kpi.sql`, `sql/mart/shop_week_kpi.sql`, `sql/mart/shop_month_kpi.sql`
- Existing dashboard API modules: `sql/api_modules/business_overview_shop_racing_module.sql`, `sql/api_modules/business_overview_traffic_ranking_module.sql`, `sql/api_modules/business_overview_operational_metrics_module.sql`
- Router/service runtime: `backend/routers/dashboard_api_postgresql.py`, `backend/services/postgresql_dashboard_service.py`
- Current company dashboard page: `frontend/src/views/BusinessOverview.vue`

## Why Rebuild Instead Of Repair

The current store analysis implementation is not a viable production asset.

- The frontend points to `/store-analytics/*`, but those routes are not registered in the current FastAPI app.
- The page still contains mock shop lists, TODO placeholders, and local synthetic detail assembly.
- The current warehouse and dashboard architecture already moved to PostgreSQL-first dashboard modules; keeping a sidecar analytics route family would duplicate data contracts and create long-term drift.

Therefore the correct move is not “finish the old page,” but “replace it with a new dashboard-native module.”

## Product Positioning

The rebuilt module is not a company overview page and not a store management page.

- `BusinessOverview` remains the company-wide dashboard.
- `StoreAnalysis` becomes the single-store drill-down cockpit.

That means the page should focus on:

1. Store performance summary for the selected period
2. Traffic and conversion diagnostics
3. Profitability and target gap
4. Inventory or product contribution signals that explain outcomes

The page should not mix in:

- Shop configuration editing
- Data collection controls
- Legacy store management CRUD
- Opaque “health score” as the primary navigation concept

## V1 Scope

V1 should deliver a usable operator-facing store analysis page with platform-aware capability differences.

Included:

- Store selector and period selector
- Store summary KPIs
- Traffic trend analysis
- Traffic/conversion comparison
- Profit and target context reuse where available
- Shopee hourly traffic trend for daily view
- TikTok daily trend for daily view
- Capability-aware frontend behavior

Excluded:

- Legacy `/store-analytics/*` route revival
- Platform-agnostic hourly promise
- AI recommendation layer
- Manual override or editing on the analysis page
- Exposure/impression as a committed top-level metric in V1

## Platform Capability Decision

Current source facts confirm that platform capability is not symmetric.

### Shopee

- Daily traffic Excel exports contain hourly rows.
- Raw daily analytics already preserve `period_start_time` / `period_end_time`.
- This enables a true hourly daily traffic view, provided we resolve duplicate hourly rows before presenting them.

### TikTok

- Daily traffic Excel exports are daily summaries, not hourly line items.
- Raw daily analytics do not carry usable hourly timestamps.
- Therefore V1 cannot honestly provide hourly daily traffic for TikTok.

### Capability Matrix

| Platform | Daily view | Weekly view | Monthly view | Quarterly view | Yearly view |
|---|---|---|---|---|---|
| Shopee | `hourly` | `daily` | `daily` | `daily` | `monthly` |
| TikTok | `daily` | `daily` | `daily` | `daily` | `monthly` |

The frontend must reflect this matrix explicitly instead of pretending all platforms support the same granularity.

## Key Data Findings That Shape The Design

### 1. Shopee hourly data exists, but it is not yet presentation-safe

Raw `b_class.fact_shopee_analytics_daily` contains hourly timestamps, but current samples show duplicate rows for the same store/date/hour combination. These duplicates appear as distinct payloads and distinct `data_hash` values.

Conclusion:

- We can build Shopee hourly analytics
- We should not expose raw hourly rows directly
- V1 needs a derived hourly aggregation layer that resolves duplicates before serving charts

### 2. Store identity in current analytics data is not reliable enough

Current analytics rows in the investigated dataset frequently carry `shop_id = 'none'`. That means the existing semantic chain is not sufficient for store analysis if consumed blindly.

Conclusion:

- V1 should not mutate the sync pipeline first
- V1 should introduce a derived resolution step in semantic or mart for store-facing analytics
- Sync-pipeline repair can follow as a separate hardening step

### 3. Exposure/impressions are not a stable cross-platform store metric yet

Although the semantic analytics model defines `impressions`, the currently inspected Shopee and TikTok analytics chain does not provide a stable, trustworthy store-level impression signal across both platforms.

Conclusion:

- V1 traffic analytics should be built around `visitor_count`, `page_views`, and `conversion_rate`
- Impressions should remain optional and hidden unless data quality is proven

## Page Design

### 1. Header And Filters

Required controls:

- Platform
- Store
- View granularity
- Time period
- Compare mode

Rules:

- Granularity options are filtered by platform capability
- If a Shopee store is selected, the daily view exposes hourly trend mode
- If a TikTok store is selected, hourly is hidden or disabled with a clear explanation

### 2. KPI Summary

The top summary block should show a compact store snapshot:

- GMV
- Orders
- Visitors
- Page views
- Conversion rate
- Profit
- Target achievement rate
- Time gap against month progress where available

These KPI cards should reuse existing dashboard styling language from `BusinessOverview.vue`, but the payload must come from store-scoped APIs rather than company totals.

### 3. Traffic Module

The V1 traffic module is the priority block.

It should provide:

- Traffic trend line
- Visitors vs page views
- Conversion rate overlay
- Current vs previous period comparison

Behavior by period:

- Daily:
  - Shopee uses hourly points
  - TikTok uses one point per day
- Weekly / Monthly / Quarterly:
  - both platforms use day-level points
- Yearly:
  - both platforms use month-level points

### 4. Secondary Diagnostic Blocks

V1 may reuse existing dashboard inputs for:

- Target and operating result context
- Shop racing or ranking context
- Inventory risk or product contribution in later slices

These should be placed below traffic, not above it.

## Data Model Strategy

### Principle

Prefer additive derived assets over mutating existing raw persistence or sync contracts.

### Objects To Reuse

- `semantic.fact_analytics_atomic`
- `mart.shop_day_kpi`
- `mart.shop_week_kpi`
- `mart.shop_month_kpi`
- `api.business_overview_shop_racing_module`
- `api.business_overview_traffic_ranking_module`
- `api.business_overview_operational_metrics_module`

### New Derived Objects

#### 1. `mart.shop_hour_traffic_kpi`

Purpose:

- Shopee-only hourly traffic aggregation for store-level daily analysis

Inputs:

- `semantic.fact_analytics_atomic`

Output fields:

- `platform_code`
- `shop_id`
- `metric_date`
- `period_hour`
- `visitor_count`
- `page_views`
- `conversion_rate`
- `source_row_count`

Rules:

- Only rows with non-null hourly timestamps participate
- Duplicate hourly rows are resolved here
- TikTok is allowed to produce zero rows in this mart

#### 2. `api.store_analysis_capability_module`

Purpose:

- Return platform and store capability metadata to the frontend

Output:

- `platform_code`
- `shop_id`
- `supports_hourly_daily`
- `supported_daily_mode`
- `supported_long_range_mode`

#### 3. `api.store_analysis_traffic_summary_module`

Purpose:

- Return KPI-level traffic summary for a selected store and period

Output:

- `platform_code`
- `shop_id`
- `period_start`
- `period_end`
- `visitor_count`
- `page_views`
- `conversion_rate`
- `page_views_per_visitor`

#### 4. `api.store_analysis_traffic_trend_module`

Purpose:

- Return chart-ready trend rows by effective grain

Output:

- `platform_code`
- `shop_id`
- `requested_granularity`
- `effective_granularity`
- `period_key`
- `visitor_count`
- `page_views`
- `conversion_rate`

Rules:

- For Shopee daily requests, `effective_granularity = hourly`
- For TikTok daily requests, `effective_granularity = daily`
- For yearly requests, `effective_granularity = monthly`

## Backend API Design

All new endpoints stay under `/api/dashboard/` to remain consistent with the active PostgreSQL router.

Recommended endpoints:

- `GET /api/dashboard/store-analysis/capabilities`
- `GET /api/dashboard/store-analysis/traffic-summary`
- `GET /api/dashboard/store-analysis/traffic-trend`

Parameters:

- `platform`
- `shop_id`
- `granularity`
- `date`
- optional compare parameters later

Backend responsibilities:

- validate supported granularity by platform
- normalize requested date window
- return both requested and effective granularity
- never fabricate hourly TikTok rows

## Frontend Behavior

The frontend must be capability-driven, not hardcoded by assumption.

### Required behavior

- Query capability metadata after shop selection
- Limit grain controls to supported values
- Render explanatory empty states instead of broken charts
- Keep the same page shell for Shopee and TikTok, but vary available controls

### UX rule

If a platform does not support hourly daily traffic, show that as a data capability constraint, not as an application error.

## Impact On Existing Sync And Storage

### V1 Intentional Non-Changes

These should remain untouched in V1:

- `DataIngestionService` contract
- `RawDataImporter` contract
- existing `b_class.fact_*_analytics_*` table schemas
- raw-table conflict rules and unique index strategy

### Why

Changing raw ingestion contracts would introduce unnecessary risk into active data sync just to deliver a read-only analytics page. The safer path is to build derived marts and API views on top of the current persisted shape.

### Acceptable Existing-Object Changes

Low-risk modifications allowed in V1:

- extend `refresh_registry.py` to include new mart/api targets
- extend `postgresql_dashboard_service.py`
- extend `dashboard_api_postgresql.py`
- optionally add a new semantic helper view if needed for store resolution or hourly dedupe

## Risks

### 1. Hourly duplicates in Shopee

Risk:

- inflated or unstable hourly charts

Mitigation:

- dedupe in derived hourly mart
- add tests with duplicate-hour fixture rows

### 2. Analytics rows with `shop_id = 'none'`

Risk:

- store analysis cannot filter correctly

Mitigation:

- derive store identity in a helper layer where possible
- treat unresolved rows as ineligible for store-scoped payloads
- schedule sync-side repair as a follow-up task, not a V1 blocker

### 3. Exposure metric inconsistency

Risk:

- misleading cross-platform charting

Mitigation:

- keep impressions out of V1 committed scope

## Testing Requirements

### SQL / Data Pipeline

Add tests for:

- Shopee hourly mart creation
- hourly duplicate-row collapse
- TikTok daily request falling back to daily grain
- yearly request returning month grain
- capability module returning platform-aware support flags

### Backend

Add tests for:

- invalid granularity rejection
- effective granularity response contract
- empty result handling per platform

### Frontend

Add tests for:

- Shopee shows hourly daily option
- TikTok hides or disables hourly daily option
- charts render correct labels by effective granularity
- capability-driven empty states

## Rollout Plan

### Phase 1

- Build new mart/api/store-analysis traffic path
- Rebuild frontend store analysis traffic module
- Enable Shopee hourly daily view
- Keep TikTok daily-only for daily mode

### Phase 2

- Repair analytics store identity at the sync or semantic level
- backfill historical store-linked analytics rows where feasible

### Phase 3

- Extend TikTok if upstream starts exporting hourly daily traffic
- consider impressions once platform-stable

## Final Recommendation

Rebuild store analysis as a dashboard-native module with explicit platform capability differences.

V1 should:

- deliver a real store traffic analysis page
- keep the current sync pipeline stable
- support Shopee hourly daily traffic immediately
- reserve TikTok hourly support for future source improvements

This is the lowest-risk path that produces a useful store analysis module without reintroducing legacy route families or destabilizing active data sync.
