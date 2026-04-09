# Snapshot Continuous Inventory Aging Design

**Date:** 2026-04-09

**Goal:** Replace the current ledger/FIFO-based runtime aging path with a company-level snapshot-continuous aging model derived from imported inventory snapshots, while preserving historical traceability and fast current-state queries.

## 1. Background

The repository currently contains two different inventory ideas:

1. A ledger-first inventory domain
   - `OpeningBalance`
   - `GRNHeader / GRNLine`
   - `InventoryLedger`
   - `InventoryAdjustment*`
   - `InventoryLayer / InventoryLayerConsumption`

2. A snapshot-first inventory analytics chain
   - `semantic.fact_inventory_snapshot`
   - `mart.inventory_snapshot_history`
   - `mart.inventory_snapshot_latest`
   - `mart.inventory_snapshot_change`
   - `mart.inventory_backlog_base`

The business has now clarified that the system is not the operational inventory system of record. Inventory operations remain in Miaoshou ERP. This repository only imports inventory snapshots and provides inventory viewing, reporting, and decision-support metrics.

That means the current FIFO layer model is not the correct primary runtime model for inventory aging. It assumes inbound and outbound inventory events are authored inside this system, which is not how the business actually works.

## 2. Problem Statement

The current inventory aging implementation is based on remaining inventory layers. That model is suitable for a transactional inventory system, but not for a read-only snapshot system.

The required future behavior is:

- If a SKU has positive inventory and the quantity does not increase, aging continues.
- If the quantity decreases, aging still continues because the business interprets this as selling old stock.
- If the quantity increases, aging resets to `0` because the business interprets this as a replenishment or a fresh stock event.
- If current quantity is `0`, aging is not calculated.

Example:

- Day 1: SKU-A quantity = 2, aging = 0
- Day 61: SKU-A quantity = 2, aging = 61
- Day 65: SKU-A quantity = 1, aging = 65
- Day 65: SKU-A quantity = 3, aging = 0

This is not physical batch aging. It is a "continuous positive-stock age since last replenishment" metric.

## 3. Design Goals

1. Make snapshot-continuous aging the official inventory aging runtime path.
2. Calculate aging from company-level inventory snapshots, not from internal ledger events.
3. Support incremental refresh so aging updates efficiently after each new snapshot import.
4. Keep a history of age changes so the result is explainable and auditable.
5. Keep current-state reads fast for dashboard and inventory list queries.
6. Preserve a clean extension path for future scope refinements such as shop-level or warehouse-level aging.

## 4. Non-Goals

1. Do not replace Miaoshou ERP as the operational inventory system.
2. Do not claim this metric is physical FIFO/LIFO batch age.
3. Do not require internal GRN, adjustment, or outbound posting to keep aging correct.
4. Do not make shop-level aging official until the source snapshots reliably include shop ownership.
5. Do not delete the existing ledger-first inventory domain in this phase; it simply stops being the primary runtime path for aging.

## 5. Official Domain Definitions

### 5.1 Official Scope

The official aging scope for this phase is:

- company-level inventory snapshot

The system does not currently have stable shop-level ownership for the imported inventory snapshots, so aging is not keyed by `shop_id`.

### 5.2 Official Identity Key

The official current key is:

- `platform_code + sku_key`

`sku_key` should be resolved by priority:

1. `platform_sku`
2. `product_sku`
3. `sku_id`
4. `product_id`

If all candidate identifiers are empty, the row is invalid for aging and should be excluded from the aging pipeline with an explicit anomaly log.

### 5.3 Official Quantity Field

The official aging quantity should use:

- `available_stock`

Rationale:

- It is the closest field to the inventory the business actually monitors for stale stock.
- The user explicitly said zero-stock products should not have aging.
- `reserved_stock` or `in_transit_stock` should not keep a positive age alive by themselves.

Secondary quantity fields such as `on_hand_stock` can still be preserved for display and analysis, but aging state is driven by `available_stock`.

### 5.4 Official Reset Rules

For a given `platform_code + sku_key`, ordered by `snapshot_date`:

- `current_qty <= 0`: aging is not calculated, current state row should not exist
- `previous_qty` is null and `current_qty > 0`: aging resets to `0`
- `previous_qty <= 0` and `current_qty > 0`: aging resets to `0`
- `current_qty > previous_qty`: aging resets to `0`
- `current_qty <= previous_qty` and `current_qty > 0`: aging continues from the previous anchor date

### 5.5 Official Aging Definition

- `age_anchor_date`: the latest snapshot date where aging reset to `0`
- `age_days`: `snapshot_date - age_anchor_date`

If any snapshot resets aging to `0`, all later positive-quantity snapshots must age forward from that new anchor date.

## 6. Architecture

The recommended design is a mixed model:

- keep snapshot history as source truth
- compute aging incrementally into dedicated mart tables
- expose current and summary read models through `api` layer modules and backend routers

This fits the repository's primary runtime path:

- `b_class raw -> semantic -> mart -> api -> backend -> frontend`

### 6.1 Why Not Pure Query-Time SQL

Pure query-time SQL is attractive for low implementation effort, but it becomes expensive and harder to reason about as snapshot history grows. Every aging query would need to re-scan historical snapshots and reconstruct reset points.

### 6.2 Why Not State Table Only

A state-table-only model would be fast, but it would make backfills and explanation harder. The system still needs a recoverable history and deterministic re-build path.

### 6.3 Recommended Runtime Shape

Use:

- historical snapshot view/table as source truth
- aging history table for explainability
- aging current table for fast reads
- full rebuild command plus incremental refresh command

## 7. Data Model

### 7.1 Reused Existing Objects

- `semantic.fact_inventory_snapshot`
- `mart.inventory_snapshot_history`
- `mart.inventory_snapshot_latest`

These remain valid and should not be removed.

### 7.2 New Mart Object: `mart.inventory_snapshot_company_daily`

Purpose:

- normalize daily company-level quantity per SKU
- deduplicate multiple imports on the same day
- aggregate the full-company inventory to the official aging scope

Suggested fields:

- `snapshot_date`
- `platform_code`
- `sku_key`
- `platform_sku`
- `product_sku`
- `sku_id`
- `product_id`
- `product_name`
- `available_qty`
- `on_hand_qty`
- `inventory_value`
- `warehouse_count`
- `last_ingest_timestamp`

Rules:

- if multiple imports exist on the same day, keep the latest effective snapshot for that day before aggregation
- aggregate all rows for the same `platform_code + sku_key`
- ignore `shop_id` as an official partition key in this phase

### 7.3 New Mart Table: `mart.inventory_age_history`

Purpose:

- store the per-snapshot aging result for each official key
- support explainability and backtracking

Suggested fields:

- `snapshot_date`
- `platform_code`
- `sku_key`
- `platform_sku`
- `product_sku`
- `sku_id`
- `product_id`
- `product_name`
- `current_qty`
- `previous_qty`
- `qty_delta`
- `age_anchor_date`
- `age_days`
- `reset_reason`
- `inventory_value`
- `last_ingest_timestamp`
- `created_at`
- `updated_at`

Suggested `reset_reason` values:

- `first_positive`
- `reappeared_after_zero`
- `stock_increase`
- `continued`
- `zero_stock`

### 7.4 New Mart Table: `mart.inventory_age_current`

Purpose:

- store the latest positive-inventory aging state per key
- back the primary inventory aging APIs

Suggested fields:

- `platform_code`
- `sku_key`
- `platform_sku`
- `product_sku`
- `sku_id`
- `product_id`
- `product_name`
- `snapshot_date`
- `current_qty`
- `age_anchor_date`
- `age_days`
- `reset_reason`
- `inventory_value`
- `bucket`
- `last_ingest_timestamp`
- `updated_at`

Only positive-quantity rows should exist here.

## 8. Aging Algorithm

### 8.1 Input Sequence

For each `platform_code + sku_key`, read `mart.inventory_snapshot_company_daily` ordered by:

1. `snapshot_date asc`
2. `last_ingest_timestamp asc`

### 8.2 Per-Snapshot Transition

Pseudo-code:

```text
if current_qty <= 0:
    age_anchor_date = null
    age_days = null
    reset_reason = "zero_stock"
    do not keep this row in inventory_age_current

elif previous_qty is null:
    age_anchor_date = snapshot_date
    age_days = 0
    reset_reason = "first_positive"

elif previous_qty <= 0:
    age_anchor_date = snapshot_date
    age_days = 0
    reset_reason = "reappeared_after_zero"

elif current_qty > previous_qty:
    age_anchor_date = snapshot_date
    age_days = 0
    reset_reason = "stock_increase"

else:
    age_anchor_date = previous_age_anchor_date
    age_days = snapshot_date - age_anchor_date
    reset_reason = "continued"
```

### 8.3 Bucket Mapping

Default aging buckets:

- `0-30`
- `31-60`
- `61-90`
- `91-180`
- `180+`

Zero-stock rows do not enter buckets.

## 9. Refresh Strategy

### 9.1 Full Rebuild

Provide a full rebuild command that:

1. rebuilds `mart.inventory_snapshot_company_daily`
2. truncates or overwrites `mart.inventory_age_history`
3. recomputes aging in snapshot order
4. rebuilds `mart.inventory_age_current`

This is the recovery path for:

- first deployment
- historical backfill
- algorithm changes
- data repair

### 9.2 Incremental Refresh

After each new inventory snapshot import:

1. refresh `semantic.fact_inventory_snapshot`
2. refresh `mart.inventory_snapshot_history`
3. refresh `mart.inventory_snapshot_company_daily`
4. identify affected `platform_code + sku_key`
5. for each affected key, rebuild aging rows from the earliest changed snapshot date forward
6. upsert the latest positive row into `mart.inventory_age_current`

The system must not attempt row-by-row in-place mutation without replay support. Replay from the earliest affected snapshot keeps the model deterministic and repairable.

## 10. API Design

### 10.1 Current Aging List

Keep the current route family under:

- `/api/inventory/aging`
- `/api/inventory/aging/buckets`

But change the source from FIFO layer aging to snapshot-continuous aging.

Suggested current list response fields:

- `platform_code`
- `sku_key`
- `platform_sku`
- `product_sku`
- `product_name`
- `current_qty`
- `age_anchor_date`
- `age_days`
- `reset_reason`
- `inventory_value`
- `bucket`
- `snapshot_date`

### 10.2 Current Summary

Summary should expose:

- total positive-qty SKU count
- total positive quantity
- total inventory value
- bucket summary rows

### 10.3 Optional Explainability API

Add a future-friendly route:

- `/api/inventory/aging/{sku_key}/history`

This allows operations users to understand why an age reset occurred and is the main defense against confusion over "stock increase means age reset."

## 11. Frontend Design

The inventory aging page should stop presenting FIFO-style fields such as:

- oldest layer age
- youngest layer age
- weighted average layer age

Those fields belong to the old layer model, not the new official model.

The new primary columns should be:

- SKU
- current quantity
- age days
- anchor date
- reset reason
- inventory value
- snapshot date

The summary panel should show:

- total positive SKU count
- total positive quantity
- total inventory value
- bucket distribution

## 12. Migration and Compatibility

### 12.1 Runtime Priority

The new snapshot-continuous aging path becomes the official runtime path for aging pages and aging APIs.

### 12.2 Existing Ledger-First Objects

The following objects remain in the repository:

- `InventoryLedger`
- `InventoryLayer`
- `InventoryLayerConsumption`
- old aging services

They may still be useful for historical experiments or future operational inventory work, but they are no longer the business-approved source for official inventory aging.

### 12.3 Documentation Update

Documentation must explicitly say:

- official inventory aging is snapshot-continuous aging
- the system does not manage inbound or outbound inventory transactions for the official aging metric
- age reset on quantity increase is expected behavior, not a data bug

## 13. Error Handling

The pipeline should explicitly detect and surface:

- missing `sku_key`
- invalid snapshot dates
- duplicate same-day snapshots that cannot be ordered
- negative quantities after normalization
- sudden extreme jumps that may indicate source mapping errors

These should not silently poison current aging state.

## 14. Testing Strategy

Minimum required test coverage:

1. first positive quantity sets age to `0`
2. equal quantity increments age by snapshot-day difference
3. decreasing quantity does not reset age
4. increasing quantity resets age to `0`
5. zero quantity removes the row from current aging state
6. positive quantity after zero resets age to `0`
7. same-day repeated imports keep only the final daily snapshot
8. backfill rebuild produces the same current state as incremental replay

## 15. Future Extension Path

When the source later provides stable shop ownership, extend the engine with:

- `scope_type`
- `scope_key`

The current phase hardcodes:

- `scope_type = company`

Later phases can support:

- `scope_type = shop`
- `scope_type = warehouse`

without changing the core reset algorithm.

## 16. Decision

The system should adopt company-level snapshot-continuous aging as the official inventory aging model.

This design matches the actual operating model:

- Miaoshou ERP remains the transactional inventory system
- this repository remains a snapshot-driven analytics and decision-support system
- aging is derived from inventory snapshot continuity, not from internal stock movement bookkeeping
