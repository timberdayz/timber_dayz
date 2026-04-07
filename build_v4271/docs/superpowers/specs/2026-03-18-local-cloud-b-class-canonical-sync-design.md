# Local-to-Cloud B-Class Canonical Sync Design

**Date:** 2026-03-18

## Goal

Synchronize all local B-class business data to the cloud without requiring the cloud database to mirror local dynamic-column physical layout.

## Key Decision

Treat the canonical payload as the source of truth:
- fixed system fields
- `raw_data`
- `header_columns`
- `data_hash`

Dynamic columns remain query projections. They are useful locally, but they are not the sync contract.

## Why

The current B-class tables mix:
- stable metadata fields
- dynamic text columns
- canonical JSON payload

If we sync dynamic columns as part of the contract, the cloud schema becomes coupled to runtime header evolution. That creates unstable DDL behavior, poor governance, and unclear historical semantics.

If we sync canonical payload instead:
- all B-class data still reaches the cloud
- the cloud does not need the same dynamic-column order or physical layout
- historical rows remain interpretable through `raw_data + header_columns`
- future CDC adoption stays possible

## Scope

In scope:
- local `b_class` table enumeration
- canonical payload extraction
- cloud-side canonical mirror tables
- idempotent upsert
- per-table checkpoints
- run logging

Out of scope:
- bidirectional sync
- cloud runtime dynamic-column expansion
- historical payload rewriting
- immediate CDC rollout

## Data Contract

Each synchronized row should include:
- `platform_code`
- `shop_id`
- `data_domain`
- `granularity`
- `sub_domain`
- `metric_date`
- `period_start_date`
- `period_end_date`
- `period_start_time`
- `period_end_time`
- `file_id`
- `template_id`
- `data_hash`
- `ingest_timestamp`
- `currency_code`
- `raw_data`
- `header_columns`

## Write Semantics

Use cloud-side idempotent upsert with the same logical uniqueness semantics already used locally:
- non-`services`: `(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`
- `services`: `(data_domain, sub_domain, granularity, data_hash)`

## Reliability Model

Use scheduled micro-batch sync for now:
- enumerate local `b_class` tables
- read batches ordered by `(ingest_timestamp, id)`
- write to cloud canonical mirror tables
- advance checkpoint only after successful commit

This gives a reliable foundation now while keeping the door open for WAL-based CDC later.

## Why Not Immediate CDC

CDC is the long-term reliability upgrade, but not the right first move here because:
- the sync contract still needed cleanup
- the repo has no existing CDC infrastructure
- direct replication of current B-class physical tables would carry dynamic-column coupling into the cloud

The correct sequence is:
1. stabilize canonical sync contract
2. deploy canonical micro-batch sync
3. upgrade the transport layer to CDC later if needed

## Open Items For Implementation

- decide the cloud schema name for canonical mirror tables
- define local checkpoint and run-history tables
- build projection refresh as a separate concern, not part of sync
