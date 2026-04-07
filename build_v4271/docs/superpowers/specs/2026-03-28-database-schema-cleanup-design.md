# Database Schema Cleanup Design

**Date:** 2026-03-28
**Last Updated:** 2026-03-28

## Goal

Define a safe cleanup strategy for duplicate tables, misplaced tables, and historical compatibility tables across `public`, `core`, `a_class`, `b_class`, `c_class`, and `finance`, without breaking production runtime paths.

## Non-Goals

Out of scope for the first cleanup wave:
- deleting any table only because its name appears duplicated
- moving dynamic `b_class` fact tables or `cloud_b_class` mirror tables
- changing production data models and cleanup logic in the same release
- bulk-dropping legacy public tables without a read/write audit
- rewriting all ORM schema declarations in one pass

## Current Reality Check

The repository and the live environments do not have a single clean “one table -> one schema” state yet.

Three different truths coexist:
- ORM SSOT in `modules/core/db/schema.py`
- historical migrations and schema moves already applied to some environments
- actual live database state, which still contains public-schema duplicates and compatibility leftovers

This means cleanup must be driven by:
1. actual runtime usage
2. actual migrated target schema
3. environment-specific table presence

Not by model definitions alone.

## What We Know

### 1. Production is functionally healthy

Production is currently:
- running the latest task-center migration chain
- passing schema completeness checks for the deployed code
- serving task-center read APIs correctly
- successfully writing cloud-sync task-center mirror rows

So cleanup is now an architecture-hardening task, not a production-outage recovery task.

### 2. Production still contains duplicated or split-location tables

Observed examples in production:
- `performance_config` in both `a_class` and `public`
- `sales_campaigns` in both `a_class` and `public`
- `sales_campaign_shops` in both `a_class` and `public`
- `target_breakdown` in both `a_class` and `public`
- `entity_aliases` in both `b_class` and `public`
- `staging_raw_data` in both `b_class` and `public`
- `dim_shops` in both `core` and `public`

### 3. Some “mismatches” are not cleanup targets

Examples:
- `cloud_b_class.*` tables mirror cloud sync state and should not be merged into local schemas
- dynamic `b_class.fact_*` tables and `b_class_canonical` tables are runtime assets, not accidental duplicates
- `public.task_center_*` are now real production tables and must be treated as canonical until a deliberate schema move is planned

## Cleanup Principles

### 1. Runtime truth beats naming aesthetics

If a table is the active runtime source of truth, it is not a cleanup candidate just because a cleaner schema would be preferable.

### 2. Delete only after proving zero active readers and zero active writers

Every candidate table must pass:
- code-reference audit
- runtime-path audit
- data freshness / row-count audit
- migration lineage audit

### 3. Public duplicates are not automatically safe to drop

Many public-schema tables are compatibility leftovers from phased migrations.
They should be removed only after:
- the target schema copy is confirmed complete
- no routers/services/scripts still read the public copy
- monitoring or smoke tests confirm the migrated path is active

### 4. Cleanup must be phased by risk

Use risk waves:
- Wave 0: inventory and classification only
- Wave 1: dead obvious documentation/metadata cleanup
- Wave 2: tables with duplicated target schema and no active reads
- Wave 3: complex operational tables with transitional behavior

## Classification Model

## Class A: Canonical and keep

These should not be touched in the cleanup wave except for documentation:
- `public.catalog_files`
- `public.cloud_b_class_sync_*`
- `public.task_center_*`
- active `b_class.fact_*`
- `cloud_b_class.fact_*`

Reason:
- they are active runtime storage today
- they are already aligned with deployed code

## Class B: Duplicated and likely cleanup candidates

These appear in both target business schema and `public`, and the target schema should be the long-term authority:
- `a_class.performance_config` vs `public.performance_config`
- `a_class.sales_campaigns` vs `public.sales_campaigns`
- `a_class.sales_campaign_shops` vs `public.sales_campaign_shops`
- `a_class.target_breakdown` vs `public.target_breakdown`
- `b_class.entity_aliases` vs `public.entity_aliases`
- `b_class.staging_raw_data` vs `public.staging_raw_data`
- `core.dim_shops` vs `public.dim_shops`

These are the primary cleanup focus, but only after reference audits.

## Class C: Target-schema tables missing model/schema alignment

Some tables physically live in `core` / `finance` / `a_class` / `c_class`, while ORM definitions may still look effectively public.

This is not a drop-table problem first.
This is an alignment problem:
- document the intended target schema
- ensure migrations are the authority
- then clean duplicates

## Class D: Historical or archived compatibility tables

These need table-by-table analysis.
Examples from older cleanup docs:
- ad hoc backup tables
- old report tables
- old key-value helper tables

Do not include them in the first schema-dup cleanup wave unless they pass a zero-usage audit.

## Recommended Strategy

## Phase 1: Build an authoritative inventory

For every duplicated table:
- expected canonical schema
- actual schemas present
- row counts per schema
- latest row timestamps where available
- routers/services/scripts that reference it
- whether production actually exercises the target schema

Deliverable:
- a machine-readable inventory report plus a reviewed markdown summary

## Phase 2: Prove schema authority before dropping duplicates

For each Class B table:
- confirm target schema table structure matches business expectations
- confirm migrated table contains current data
- confirm public copy is stale or unused
- add targeted smoke test if the runtime path is not already covered

Only then mark the public duplicate as droppable.

## Phase 3: Drop low-risk duplicates first

Recommended early candidates:
- `public.performance_config`
- `public.sales_campaigns`
- `public.sales_campaign_shops`
- `public.target_breakdown`

But only after the Phase 2 proof exists for each one.

## Phase 4: Handle operational duplicates separately

Higher-risk examples:
- `public.entity_aliases`
- `public.staging_raw_data`
- `public.dim_shops`

These have wider blast radius and should be cleaned only after dedicated runtime audits.

## Phase 5: Reconcile model/schema metadata

After duplicate cleanup:
- align ORM schema declarations where needed
- regenerate schema audit expectations
- rerun environment validation

## Required Checks Before Dropping Any Table

For each candidate table:
- code grep shows no active references to the to-be-dropped schema location
- production row count of the target table is non-zero if the feature is active
- the public duplicate is not fresher than the target copy
- smoke tests for affected feature pass
- rollback path exists

## Rollback Requirements

Every cleanup migration must be reversible enough for emergency response:
- take backup before drop
- record row counts
- record table definitions
- prefer rename/archive over hard drop for the first risky wave when feasible

## Production-Specific Recommendation

Do **not** start cleanup by dropping tables in production manually.

Instead:
1. produce the inventory
2. classify candidates
3. land one migration wave per risk group
4. run smoke verification after each wave

## Proposed Deliverables

1. Inventory report
   - duplicated tables by schema
   - canonical target schema per table
   - usage evidence

2. Cleanup plan
   - wave-by-wave execution order
   - exact migrations to write
   - exact tests to run

3. Cleanup migrations
   - one small migration file per low-risk wave

## Recommendation

The right next step is not “clean everything”.

The right next step is:
- create an authoritative duplicate-table inventory
- classify by risk
- execute low-risk public-duplicate removal in small migration waves

This minimizes production risk while steadily converging the database toward the intended schema layout.
