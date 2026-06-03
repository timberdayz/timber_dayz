# Local Dashboard Asset Recovery

This runbook defines the standard local recovery path when PostgreSQL-backed dashboard pages report asset drift, missing objects, or bootstrap failures.

Use this before changing dashboard SQL.

## Goal

Recover local dashboard assets in a stable, repeatable order without guessing:

1. Inspect actual state
2. Classify the failure
3. Apply the smallest valid recovery action
4. Re-check
5. Only then open the page for manual validation

## Standard Check Command

Always start here:

```bash
python scripts/bootstrap_postgresql_dashboard.py --module business_overview --check --json
```

Read these fields first:

- `ready`
- `modules.business_overview.status`
- `missing_objects`
- `modules.business_overview.core_missing_objects`
- `modules.business_overview.refresh_missing_objects`
- `asset_fingerprint_expected`
- `asset_fingerprint_applied`
- `refresh_fingerprint_expected`
- `refresh_fingerprint_applied`

## Problem Categories

### 1. `missing_objects`

Definition:

- One or more required `semantic` / `mart` / `api` objects do not exist.

Typical symptom:

- `core_missing_objects` or `refresh_missing_objects` is non-empty.

Action:

1. Identify whether the missing object is:
   - `api`
   - `mart`
   - `semantic`
2. Recover the smallest valid dependency chain:
   - `api` object missing but `mart` dependencies exist: recover the `api` object first
   - `mart` object missing: recover required `mart` target and its prerequisites
   - `semantic` object missing: move one layer lower and recover semantic prerequisites first
3. Re-run `--check --json`

### 2. `fingerprint_drift`

Definition:

- Objects exist, but applied asset fingerprint does not match current code expectations.

Typical symptom:

- `missing_objects = []`
- `status = drift`
- expected fingerprint != applied fingerprint

Action:

1. Do not assume frontend bug
2. Check recent SQL asset changes
3. Decide whether local recovery should be:
   - targeted object rebuild, or
   - full module bootstrap
4. Re-run `--check --json`

### 3. `refresh_timeout`

Definition:

- A refresh target exists in the dependency chain but is too slow to rebuild inside current limits.

Typical symptom:

- `pipeline_step_log.error_message` contains timeout / `QueryCanceledError`
- bootstrap hangs for a long time or times out

Action:

1. Inspect `ops.pipeline_run_log`
2. Inspect `ops.pipeline_step_log`
3. Identify the exact target and SQL path from diagnostics
4. Switch from “rebuild everything” to performance analysis for that target
5. Do not repeatedly retry full bootstrap without understanding the hot path

### 4. `state_desync`

Definition:

- `ops.dashboard_asset_state` suggests `ready`, but real objects are missing or drifted.

Typical symptom:

- old `run_id` and `status = ready`
- current `inspect_dashboard_assets()` still reports `drift`

Action:

1. Trust object existence + fingerprint checks over stored status
2. Use diagnostics to identify which target must be rebuilt
3. Re-run `--check --json` after recovery

## Recovery Order

Use this order for `business_overview`:

1. Check asset state with `--check --json`
2. If `missing_objects` is non-empty:
   - recover the smallest missing target set first
3. If no missing objects but fingerprints drift:
   - decide whether targeted rebuild is sufficient
4. If refresh timeout occurs:
   - stop full bootstrap retries
   - inspect target-level diagnostics
   - move to performance analysis

## Preferred Recovery Strategy

### Prefer targeted recovery when:

- only a few `api` / `mart` objects are missing
- dependencies are already present
- drift is localized

### Prefer full module bootstrap when:

- many targets are missing
- fingerprints drift across multiple layers
- there is no confidence that local objects are coherent

### Prefer performance investigation instead of rebuild when:

- bootstrap repeatedly hangs
- `pipeline_step_log` shows timeout on the same refresh target
- source row counts are modest but the SQL is computation-heavy

## Required Diagnostics

When recovery fails, capture:

- latest `ops.pipeline_run_log` rows for dashboard bootstrap
- latest `ops.pipeline_step_log` rows
- target name
- `sql_path`
- `attempts`
- `last_success_target`
- `error_summary`

These fields now come from `refresh_runner` diagnostics and should be the first place you look.

## Manual Validation Gate

Only open Business Overview after:

1. `python scripts/bootstrap_postgresql_dashboard.py --module business_overview --check --json`
2. Result shows:
   - `ready = true`
   - `missing_objects = []`
   - `assets_drift = false`

If these are not true, do not treat page errors as frontend issues.

## Current Known Hot Path

As of the current repository state, the main local rebuild hotspot is:

- `semantic.fact_orders_monthly_atomic_mv`

Do not treat this as a generic bootstrap problem.
Treat it as a target-specific performance problem once diagnostics confirm timeout there.
