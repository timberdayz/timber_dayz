# Schema Cleanup Inventory

**Date:** 2026-03-28
**Scope:** Local DB reality, production DB reality, ORM canonical schema expectations

## Goal

Provide the first authoritative inventory of duplicated, misplaced, and extra tables so schema cleanup can proceed in small, evidence-driven waves instead of direct production table deletion.

## Sources

- ORM metadata from `modules/core/db/schema.py`
- local DB inspection via `scripts/analyze_schema_cleanup_candidates.py`
- production DB inspection gathered during deploy/migration audit

## High-Level Summary

### Local DB

`scripts/analyze_schema_cleanup_candidates.py` reported:
- expected tables: `120`
- actual table names: `186`
- duplicate groups: `0`
- misplaced tables: `64`
- missing tables: `3`
- extra-only tables: `69`

Important note:
- local DB is not a reliable “final canonical” environment
- it reflects a mixed historical state and should be used only as one input to the cleanup plan

### Production DB

Production remains the most important runtime source of truth.

Observed during live inspection:
- duplicated table groups still exist across target schema and `public`
- task-center tables are now live runtime tables in `public`
- production app is healthy, so cleanup must avoid breaking active reads/writes

## Canonical Keep Groups

These are not cleanup candidates in wave 1:

- `public.task_center_tasks`
- `public.task_center_logs`
- `public.task_center_links`
- `public.cloud_b_class_sync_tasks`
- `public.cloud_b_class_sync_runs`
- `public.cloud_b_class_sync_checkpoints`
- dynamic `b_class.fact_*` tables
- `cloud_b_class.fact_*` mirror tables

Reason:
- these are active runtime or operational control-plane assets

## Likely Cleanup Candidates

These are the first candidates to prove and then remove from `public` if the target schema copy is authoritative:

- `performance_config`
- `sales_campaigns`
- `sales_campaign_shops`
- `target_breakdown`
- `entity_aliases`
- `staging_raw_data`
- `dim_shops`

Recommended action:
- prove target schema usage with tests and runtime checks first
- do not drop directly from production by hand

## Misplaced-But-Not-Duplicate Tables

The inventory tool flagged many tables whose ORM canonical schema is still effectively `public`, while the actual table lives in:
- `core`
- `a_class`
- `c_class`
- `finance`
- `b_class`

Examples:
- `accounts -> core`
- `collection_tasks -> core`
- `collection_task_logs -> core`
- `component_versions -> core`
- `sync_progress_tasks -> core`
- many finance-domain tables -> `finance`
- performance and campaign tables -> `a_class` / `c_class`

Interpretation:
- this is primarily a schema-alignment issue
- not an immediate table-drop issue

## Production-Specific Duplicate Groups

Observed on production:

- `performance_config` in `a_class` and `public`
- `sales_campaigns` in `a_class` and `public`
- `sales_campaign_shops` in `a_class` and `public`
- `target_breakdown` in `a_class` and `public`
- `entity_aliases` in `b_class` and `public`
- `staging_raw_data` in `b_class` and `public`
- `dim_shops` in `core` and `public`

These are the most important cleanup targets because they are:
- visible in live production
- conceptually duplicated
- likely products of historical migration phases

## Extra-Only Tables Requiring Manual Review

The local audit also shows many extra-only tables not directly represented by current ORM expectations.

Examples:
- `campaign_targets`
- `dim_date`
- `fact_sales_orders`
- `pipeline_run_log`
- `pipeline_step_log`
- `data_freshness_log`

These should not enter wave 1.

Recommended action:
- classify them separately as legacy support, ops tables, or dead leftovers

## Wave Recommendations

### Wave 0: Inventory only

Completed in this report.

### Wave 1: Low-risk public duplicate cleanup

Target after proof:
- `public.performance_config`
- `public.sales_campaigns`
- `public.sales_campaign_shops`
- `public.target_breakdown`

Preconditions:
- target schema rows are current
- no active runtime code reads public copies
- feature smoke tests pass

### Wave 2: Higher-risk operational duplicates

Do not execute until after wave 1 is proven.

Candidates:
- `public.entity_aliases`
- `public.staging_raw_data`
- `public.dim_shops`

These need additional runtime/read-path proof.

### Wave 3: Extra-only historical tables

Separate project after the duplicate cleanup waves.

## Immediate Next Steps

1. Add proof tests for low-risk duplicate candidates
2. Write a first cleanup migration wave for approved `public` duplicates
3. Rehearse cleanup on a temporary PostgreSQL database
4. Only then decide whether to schedule production cleanup

## Proof Audit Update

Focused proof coverage was added for the nominal wave-1 set:

- `target_breakdown`
- `performance_config`
- `sales_campaigns`
- `sales_campaign_shops`

Current conclusion:

- `target_breakdown` is the only candidate that currently has authoritative `a_class` runtime proof.
- `performance_config`, `sales_campaigns`, and `sales_campaign_shops` are not ready for cleanup yet.

Why the other three are blocked:

- their current ORM model schema is still `public`
- the audited runtime files do not explicitly reference `a_class.<table>`
- dropping the `public` copy now would risk breaking active ORM-backed reads and writes

Wave-1 recommendation must therefore be narrowed:

- keep `target_breakdown` as the only currently proven low-risk duplicate
- move `performance_config`, `sales_campaigns`, and `sales_campaign_shops` behind a schema-alignment prerequisite

## Wave 1 Reset

The wave-1 preplan is now fixed to this scope:

- approved: `public.target_breakdown`
- blocked:
  - `public.performance_config`
  - `public.sales_campaigns`
  - `public.sales_campaign_shops`

Planned first-step operation for the approved table:

- `archive_rename`

Reason for choosing archive/rename first:

- it preserves rollback space
- it is safer than direct drop for a production-visible duplicate
- it allows rehearsal validation before any destructive cleanup decision

## Related Documents

- `docs/superpowers/specs/2026-03-28-database-schema-cleanup-design.md`
- `docs/superpowers/plans/2026-03-28-database-schema-cleanup.md`
- `docs/deployment/2026-03-28-production-deploy-and-migration-report.md`
