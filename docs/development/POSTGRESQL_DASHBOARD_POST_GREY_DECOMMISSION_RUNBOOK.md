# PostgreSQL Dashboard post-grey decommission runbook

## Goal

After PostgreSQL Dashboard production gray is stable and rollback is no longer required as the default operating strategy, remove the remaining Metabase-first runtime path in a controlled sequence.

## Preconditions

- production gray has completed successfully
- no active rollback decision is pending
- `USE_POSTGRESQL_DASHBOARD_ROUTER=true` has been stable in production
- `ENABLE_METABASE_PROXY=false` remains stable
- latest `python -m pytest backend/tests/data_pipeline -q` is green

## Phase 1: Retire the old dashboard runtime path

Target:

- `backend/routers/dashboard_api.py`

Actions:

1. Confirm no environment still depends on the old dashboard compatibility router as the default path.
2. Keep the file available for one final rollback window if required by release policy.
3. Remove its role as the default operational dashboard path in docs and release notes.
4. If production remains stable through the agreed rollback window, archive or delete the old dashboard compatibility router.

## Phase 2: Retire retained Metabase fallback assets

Targets:

- `backend/routers/metabase_proxy.py`
- `backend/services/metabase_question_service.py`
- `config/metabase_config.yaml`
- `docker-compose.metabase.yml`
- `docker-compose.metabase.dev.yml`

Actions:

1. Confirm these assets are no longer needed for rollback/debug in active operations.
2. Move them into an explicit legacy/archive location or remove them entirely.
3. Remove any remaining environment references or startup hints that imply they are normal runtime dependencies.
4. Update legacy/retirement docs after the move.

## Verification

Run after each retirement phase:

```bash
python -m pytest backend/tests/data_pipeline -q
```

Recommended additional checks:

```bash
python scripts/smoke_postgresql_dashboard_routes.py --base-url <base_url>
python scripts/check_postgresql_dashboard_ops.py
```

Confirm:

- PostgreSQL dashboard routes still return expected results
- no docs or startup scripts claim Metabase is the primary path
- no `ops` freshness or lineage regressions appear

## Rollback

If decommission work introduces regression risk:

1. restore the removed legacy file(s) from git
2. keep `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
3. only re-enable `ENABLE_METABASE_PROXY=true` if rollback/debug access is truly required
4. rerun verification before attempting retirement again

## Related Documents

- `docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md`
- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
- `docs/development/POSTGRESQL_DASHBOARD_PRODUCTION_GREY_RUNBOOK.md`
- `docs/development/POSTGRESQL_DASHBOARD_ROLLBACK_COMMANDS.md`
