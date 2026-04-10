# Schema Alignment Program Design

**Date:** 2026-04-10

**Goal:** Establish a repeatable, evidence-driven program to align ORM definitions, migration history, and the actual PostgreSQL runtime schema across the repository, while prioritizing the first repair wave around tables that directly affect collection execution, task observability, and data-file lifecycle flows.

## 1. Background

The repository has accumulated multiple generations of database evolution:

- early `public`-first tables
- later domain schema placement such as `core`, `a_class`, `b_class`, `c_class`, and `finance`
- historical one-off repair scripts
- ORM definitions consolidated into `modules/core/db/schema.py`
- migrations that were applied against environments with different starting states

This has produced a recurring class of problems:

1. ORM definitions express one intended shape.
2. Migrations express another historical sequence.
3. The actual runtime PostgreSQL database may expose a third shape.

The resulting drift is not purely theoretical. It has already affected:

- collection task diagnostics
- task-center projection assumptions
- script-based database verification
- collection/component-test reasoning about where runtime tables actually live

## 2. Why This Needs To Happen Now

Waiting until "all feature development is done" would raise the cost of repair:

- new features would continue encoding wrong table-placement assumptions
- drift would spread into more routers, services, scripts, and tests
- final cleanup would become broader, riskier, and harder to validate

At the same time, a big-bang full-database rewrite is too risky.

The correct strategy is:

- start the audit now
- define the full target now
- execute the repairs in controlled waves

## 3. Problem Statement

The system currently lacks one authoritative, continuously verified answer to all three questions:

1. What does the ORM say the table should look like?
2. What do migrations say the table history and target shape should be?
3. What does the actual runtime PostgreSQL instance contain today?

Without that, the repository will continue to suffer from:

- runtime/schema misunderstanding
- false-positive diagnostics
- migration uncertainty
- fragile scripts
- future feature work landing on unstable assumptions

## 4. Design Goals

1. Produce a full-schema audit, not just local ad hoc fixes.
2. Classify all drift into severity-based buckets.
3. Define a first repair wave focused on collection/runtime-critical tables.
4. Make the repair waves incremental and testable.
5. Ensure every repaired table has three aligned sources of truth:
   - ORM definition
   - migration contract
   - actual database verification
6. Preserve runtime stability while cleanup is in progress.

## 5. Non-Goals

1. Do not attempt one giant migration that rewrites the entire database in one pass.
2. Do not delete historical tables solely because they look unused without proof.
3. Do not change business semantics as part of schema alignment.
4. Do not block all feature work until all drift is gone.

## 6. Full-Audit Scope

The audit target is full-repository coverage for all ORM-defined tables and all active runtime tables discovered in PostgreSQL.

The audit must include:

- table schema placement
- column names
- column types
- nullability
- defaults / server defaults
- indexes
- unique constraints
- foreign keys
- table names that exist in runtime but are not represented by ORM
- ORM tables that are not present in runtime

## 7. Drift Classification Model

Every discrepancy should be classified into one of four categories.

### 7.1 `P0 runtime_blocker`

Definition:

- drift that can directly block collection, component testing, task status projection, file deletion, ingestion, or active UI flows

Examples:

- missing critical columns used by runtime code
- wrong table schema causing actual query failures
- foreign-key targets pointing at the wrong runtime table

### 7.2 `P1 runtime_misleading`

Definition:

- drift that does not always block runtime, but causes scripts, diagnostics, or operators to misread system state

Examples:

- scripts hardcoding the wrong schema
- freshness checks assuming the wrong timestamp column
- verification utilities querying the wrong table placement

### 7.3 `P2 migration_divergence`

Definition:

- ORM and migration target shape differ, but current runtime may still work

Examples:

- ORM expects a server default while migration historically did not create one
- ORM and migration differ on schema placement conventions

### 7.4 `P3 historical_or_unclear`

Definition:

- drift or extra tables with unclear runtime importance that require investigation before repair

Examples:

- historical duplicate support tables
- extra runtime-only legacy tables not clearly tied to current features

## 8. Audit Output Structure

The first deliverable should be one combined document with two layers.

### 8.1 Layer A: Full Drift Audit

For every table in scope:

- ORM location and shape
- migration-derived target or historical shape
- actual runtime location and shape
- drift category
- operational notes

### 8.2 Layer B: First Repair Wave

For the approved first-wave tables:

- priority
- repair strategy
- required tests
- migration requirements
- rollback/verification notes

This preserves complete context while still giving an actionable first repair slice.

## 9. Recommended First Repair Wave

The first wave should focus on the collection/runtime-critical table family.

### 9.1 Wave 1 Table Set

- `catalog_files`
- `collection_tasks`
- `collection_task_logs`
- `task_center_tasks`
- `task_center_logs`
- `task_center_links`

### 9.2 Why These Tables

These tables sit directly on the hot path for:

- formal collection
- component-test diagnostics
- task-center observability
- file registration and lifecycle management
- cleanup and verification scripts

Drift here creates immediate operational cost and repeated debugging noise.

## 10. Recommended First-Wave Priorities

### 10.1 `P0`

- anything that can break collection runtime or data-file lifecycle execution
- wrong FK targets on active file/task tables
- missing columns directly read/written by runtime code

### 10.2 `P1`

- scripts and diagnostics using the wrong schema or wrong timestamp column
- mismatch between runtime reality and operator/debug tooling

### 10.3 `P2`

- migration-vs-ORM mismatches that are not yet blocking runtime but will cause future fragility

### 10.4 `P3`

- remaining historical or extra tables outside the wave-1 family

## 11. First-Wave Repair Strategy

Every wave-1 table should be repaired using the same sequence.

### 11.1 Step 1: Lock the Drift With Tests

Add tests that prove:

- runtime schema placement
- expected timestamp/freshness column
- critical columns/defaults/constraints
- ORM-migration-runtime compatibility expectations

### 11.2 Step 2: Repair Scripts and Diagnostics

Update helper functions and scripts first where possible.

Rationale:

- this is lower-risk than immediate DB surgery
- it reduces operator confusion immediately
- it creates a stable base for deeper schema repair

### 11.3 Step 3: Repair Migration Contracts

Add or update migration contract tests so the approved target shape is explicit.

### 11.4 Step 4: Apply DB Repair Migrations

Only after tests and helper alignment are in place:

- add narrowly-scoped migrations
- prefer additive repair over destructive cleanup in early waves

### 11.5 Step 5: Re-verify Runtime Paths

Run:

- focused backend tests
- collection/task-center tests
- file lifecycle tests
- relevant component-test diagnostics

## 12. What Counts As "Aligned"

A table is considered aligned only when all of the following are true:

1. ORM definition matches the approved target shape.
2. Migration path can produce or repair the target shape.
3. Runtime verification confirms the actual DB matches that target.
4. Scripts and diagnostics query the correct schema and time columns.

If any one of those is missing, the table is not done.

## 13. Risks

### 13.1 Big-Bang Cleanup Risk

Trying to repair too much at once can:

- break active runtime flows
- hide which change caused regressions
- make rollback harder

Mitigation:

- wave-based repair only

### 13.2 False Canonical Assumptions

The ORM is not automatically the truth if production/runtime proves otherwise.

Mitigation:

- always compare ORM, migrations, and actual runtime together

### 13.3 Script Drift Reintroduction

Even if DB structure is repaired, old scripts can reintroduce bad assumptions.

Mitigation:

- central runtime schema/time-column helpers
- tests that forbid hardcoded wrong schema references for repaired tables

## 14. Recommendation

Proceed with:

1. a full-schema drift audit
2. a first-wave repair plan covering the collection/runtime-critical table family
3. wave-based implementation thereafter

This is the preferred approach because it:

- starts reducing risk now
- avoids delaying cleanup until the end of all development
- avoids an unsafe full-database rewrite
- gives the team one authoritative roadmap for ORM/migration/runtime alignment

## 15. First-Wave Acceptance Criteria

The first repair wave should be considered complete only when:

- the six wave-1 tables have explicit drift classification
- their runtime schema placement is locked by tests
- their critical timestamp/default assumptions are locked by tests
- wrong-schema script references are removed or routed through helpers
- migration contract gaps for the first wave are identified
- focused regression tests pass

## 16. Next Step

After this spec is approved, the implementation plan should produce:

- one audit/report artifact covering the full known table set
- one actionable wave-1 plan for the six collection/runtime-critical tables
- a repair backlog for later waves
