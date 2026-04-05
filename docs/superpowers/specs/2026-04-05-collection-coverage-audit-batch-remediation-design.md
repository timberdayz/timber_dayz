# Collection Coverage Audit And Batch Remediation Design

**Date:** 2026-04-05

**Goal:** Add a dedicated collection coverage audit page plus batch remediation workflow so operators can quickly find shops missing daily, weekly, or monthly collection configs and create the missing configs in bulk without changing the existing shop-account-based execution model.

## 1. Background

The current collection configuration flow is already usable:

- collection configs are now managed by shop account
- daily, weekly, and monthly config views exist
- coverage can already be derived per granularity
- manual config creation, manual execution, and headed debugging remain available

However, the current UI still requires the operator to discover gaps from the config page itself. That creates two problems once the number of shops grows:

1. Missing daily, weekly, or monthly configs are still too easy to overlook.
2. Fixing missing coverage across many shops is still too manual.

The next phase should improve auditability and batch remediation without redesigning the whole collection system.

## 2. Scope

This phase adds two features only:

1. A dedicated `Collection Coverage Audit` page.
2. A `Batch Remediation` flow that creates missing configs in bulk.

This phase explicitly does **not** include:

- config templates
- main-account inheritance
- a new persistence model for collection configs
- changes to the existing task execution chain

## 3. Business Rules

### 3.1 Coverage Object

The final configuration object remains the **shop account**.

Main accounts remain management dimensions only:

- grouping
- filtering
- batch operation scope

### 3.2 Granularity Rules

Coverage continues to be judged independently for:

- `daily`
- `weekly`
- `monthly`

Time preset mapping remains:

- `today`, `yesterday`, and day-custom presets -> `daily`
- `last_7_days` and week-custom presets -> `weekly`
- `last_30_days` and month-custom presets -> `monthly`

### 3.3 Coverage Rules

For one shop account and one granularity:

- if any enabled config exists, that granularity is considered covered
- headed enabled configs also count as covered
- multiple enabled configs under the same granularity are allowed

The audit view should therefore answer a simple question:

> Does this shop currently have at least one enabled config for this granularity?

### 3.4 Batch Remediation Defaults

When batch remediation creates missing configs:

- each selected shop gets its own independent config record
- the default execution mode is `headless`
- the default config state is `enabled`
- the default domains come from the shop account capability definition
- if the shop has no saved capability rows, fallback to shop-type default capability rules
- if a selected domain has sub-domains, sub-domains are auto-selected by default

## 4. Recommended UX

## 4.1 New Page

Add a dedicated page: `Collection Coverage Audit`.

This page is separate from the existing config page because the operator intent is different:

- config page = create, edit, execute
- audit page = detect missing coverage and remediate it

## 4.2 Page Structure

The page should have four areas:

1. Summary cards
2. Filter bar
3. Coverage table
4. Batch action bar

### Summary Cards

Show:

- total shops
- daily covered / daily missing
- weekly covered / weekly missing
- monthly covered / monthly missing
- partially covered shops

### Filter Bar

Support:

- platform
- main account
- region
- shop type
- coverage status

Coverage status filters should include:

- missing daily
- missing weekly
- missing monthly
- partially covered
- fully covered

### Coverage Table

Each row represents one shop account.

Suggested columns:

- platform
- main account
- shop account
- region
- shop type
- daily coverage status
- weekly coverage status
- monthly coverage status
- recommended domains summary
- actions

Row-level actions:

- `Go To Config`
- `Remediate Daily`
- `Remediate Weekly`
- `Remediate Monthly`

### Batch Action Bar

When multiple rows are selected, allow:

- `Batch Remediate Daily`
- `Batch Remediate Weekly`
- `Batch Remediate Monthly`

## 5. Batch Remediation Flow

Recommended flow:

1. User opens `Collection Coverage Audit`.
2. User filters down to a platform, main account, region, or missing status.
3. User selects one or more shop accounts.
4. User clicks `Batch Remediate Daily`, `Weekly`, or `Monthly`.
5. System opens a confirmation dialog.
6. The dialog shows:
   - how many configs will be created
   - target granularity
   - default execution mode: `headless`
   - default state: `enabled`
   - default domains source: shop capability
7. User confirms.
8. Backend creates one config per selected shop.
9. Page refreshes coverage state.
10. User can jump to the config page to inspect the new configs.

## 6. Backend Design

## 6.1 Coverage Audit API

Reuse the existing coverage aggregation model and extend it for direct UI consumption.

Recommended endpoint:

- `GET /api/collection/config-coverage`

Each item should expose at least:

- `platform`
- `main_account_id`
- `main_account_name`
- `shop_account_id`
- `shop_account_name`
- `shop_region`
- `shop_type`
- `daily_covered`
- `weekly_covered`
- `monthly_covered`
- `missing_granularities`
- `is_partially_covered`
- `recommended_domains`

### Summary Payload

The same endpoint response should also include summary counts so the frontend does not need to recompute everything.

## 6.2 Batch Remediation API

Add a dedicated batch remediation endpoint rather than overloading config create.

Recommended endpoint:

- `POST /api/collection/configs/batch-remediate`

Request fields:

- `shop_account_ids`
- `granularity`
- optional `platform` validation hint

Backend behavior:

- validate target shops exist and are active
- derive recommended domains from shop capability
- derive sub-domains automatically
- skip shops already covered for the target granularity
- create one enabled headless config per uncovered shop

Response fields:

- `created_configs`
- `skipped_shops`
- `skipped_reasons`

## 7. Frontend Design

## 7.1 New View

Add a new view, recommended path:

- `frontend/src/views/collection/CollectionCoverageAudit.vue`

This keeps the current config page focused and avoids overloading one screen with both editing and auditing concerns.

## 7.2 Reuse Existing Data Contracts

The new page should reuse the current collection constants and domain-label helpers.

The remediation dialog should show recommended domains in a read-friendly summary, but it should not expose the full config editor in this phase.

This phase is intentionally optimized for:

- find missing coverage
- fill the gap quickly

Not for:

- advanced config customization
- template authoring
- per-main-account inheritance

## 8. Error Handling

The audit and batch remediation flow should surface these cases clearly:

- selected shops already covered for target granularity
- selected shops missing capability metadata and using fallback defaults
- partial success in one batch request
- stale rows caused by another operator creating configs first

The UI should keep partial success visible instead of collapsing all outcomes into one generic success message.

## 9. Testing Strategy

### Backend

Add coverage for:

- per-granularity coverage summary
- partially covered classification
- batch remediation creates one config per shop
- covered shops are skipped, not duplicated
- capability fallback behavior

### Frontend

Add coverage for:

- audit page filters
- coverage badges per row
- batch remediation dialog summary
- successful refresh after remediation
- partial success rendering

## 10. Rollout Strategy

This phase should be implemented in order:

1. backend batch remediation contract
2. audit page data contract
3. frontend audit page
4. navigation entry
5. verification and operator walkthrough

This keeps the rollout incremental and avoids disrupting the existing config page.

## 11. Future Work

After this phase is stable, the next logical phase is:

1. config templates
2. main-account-level batch operations
3. one-click apply-template-to-selection
4. stronger remediation presets by platform and business type

Those should build on the audit/remediation flow, not replace it.
