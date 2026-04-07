# PostgreSQL Dashboard post-grey decommission runbook

## Goal

After PostgreSQL Dashboard has become the only accepted runtime path, remove the remaining Metabase-first runtime assets in a controlled sequence.

## Preconditions

- production gray has completed successfully
- latest `python -m pytest backend/tests/data_pipeline -q` is green

## Phase 1: Retire the old dashboard runtime path

Target:

- `archive/metabase/backend/routers/dashboard_api.py`

Actions:

1. Confirm no environment still depends on the old dashboard compatibility router.
2. Remove its role from docs and release notes.
3. Archive or delete the old dashboard compatibility router.

## Phase 2: Retire retained Metabase fallback assets

Targets:

- `archive/metabase/backend/routers/metabase_proxy.py`
- `archive/metabase/backend/services/metabase_question_service.py`
- `archive/metabase/scripts/init_metabase.py`
- `archive/metabase/scripts/verify_deploy_phase35_local.py`
- `archive/metabase/scripts/verify_deploy_full_local.py`
- `archive/metabase/config/metabase_config.yaml`
- `archive/metabase/docker/docker-compose.metabase.yml`
- `archive/metabase/docker/docker-compose.metabase.dev.yml`
- `archive/metabase/docker/docker-compose.metabase.4c8g.yml`
- `archive/metabase/docker/docker-compose.metabase.lockdown.yml`

Actions:

1. Confirm these assets are no longer needed in active operations.
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

## Related Documents

- `docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md`
- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
- `docs/development/POSTGRESQL_DASHBOARD_PRODUCTION_GREY_RUNBOOK.md`
- `docs/development/POSTGRESQL_DASHBOARD_ROLLBACK_COMMANDS.md`
