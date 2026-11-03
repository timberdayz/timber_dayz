# Release Checklist

## Release Source Of Truth

- Production release is triggered by `git push origin vX.Y.Z`
- Deployment truth comes from the release tag, not `origin/main`
- Push `main` to `origin` only when you intentionally want GitHub branch history to match local history
- Local `origin` has two push URLs: GitHub and CNB Git. `main` keeps the existing GitHub `origin/main` upstream so normal Cursor/VS Code pull behavior remains unchanged. Use `powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync` before publishing a completed `main` change; it checks the CNB mirror before writing either remote.
- CNB registry is used as the preferred production image pull source in China; CNB Git is only a code mirror.

## Production Compose Combination (Source Of Truth)

The effective production compose combination is decided by
`scripts/deploy_remote_production.sh` — **not** by any hand-written document:

```bash
docker-compose -f docker-compose.yml \
                -f docker-compose.prod.yml \
                [-f docker-compose.cloud.yml] \
                [-f docker-compose.cloud-4c8g.yml] \   # only when CLOUD_PROFILE=4c8g
                --profile production \
                --env-file ${PRODUCTION_PATH}/.env.cleaned \
                -f docker-compose.deploy.yml
```

- Infrastructure (PostgreSQL / Redis) stays owned by the original `xihong_erp`
  compose project (`up -d --no-build postgres redis`).
- The application layer is the temporary `docker-compose.deploy.yml` generated at
  deploy time (backend-api / frontend / nginx), attached to the existing
  `xihong_erp_erp_network`.
- **Not in effect in production**: `docker-compose.collection*.yml` (local collector
  machine only), `docker-compose.dev.yml`, `docker-compose.verify-local.yml`, and
  `docker-compose.prod.lockdown.yml`.
- `scripts/production_lockdown_deployment_guide.md`, `scripts/production_lockdown_summary.md`
  and `scripts/metabase_nginx_deployment_summary.md` describe a **different, hand-written**
  combination (one that includes `docker-compose.prod.lockdown.yml`) that the deploy
  script never references. Treat them as historical manual notes, not the release path.

### Mirroring `main` When GitHub HTTPS Is Unreachable

`sync_main_mirrors.ps1 -Sync` fetches `origin` and pushes **GitHub first**, then CNB,
and refuses to run when the two mirrors disagree. On networks where
`https://github.com` is unreachable (DNS resolves, TCP/443 times out), the sync
fails at its very first `git fetch --prune origin`.

GitHub's SSH endpoint on **port 443** usually stays reachable in that case:

```powershell
$env:GIT_SSH_COMMAND = 'ssh -i C:/Users/18689/.ssh/github_actions_deploy -o IdentitiesOnly=yes'
# Temporarily route origin's fetch channel over SSH-443 ...
git remote set-url origin "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync `
    -GitHubUrl "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
# ... then restore the documented HTTPS form
git remote set-url origin "https://github.com/timberdayz/timber_dayz.git"
```

The two-mirror contract is unchanged (both remotes still receive the same commit);
only the transport to GitHub differs. Verified 2026-11-03: both mirrors ended at the
same SHA.

### Redis Authentication

- **Production** (`docker-compose.prod.yml`):
  `redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}` — **no default value**.
  The server `.env` must therefore carry a non-empty `REDIS_PASSWORD`. If it is empty,
  Redis ends up with **no password** while the application connects with
  `redis://:${REDIS_PASSWORD}@redis:6379/0` → empty-password AUTH → rejected by Redis 6+ →
  the account session lock goes fail-closed → **all collection is refused**. The Redis
  health check fails first, so the deploy aborts instead of silently shipping.
- **Collector machine** (`docker-compose.collection.yml`): `REDIS_URL` carries **no
  password**; `backend.services.main_account_session_lock.inject_redis_password()`
  injects `REDIS_PASSWORD` on the application side (a password already present in the URL
  wins; a URL whose scheme is not `redis`/`rediss`/`unix` is returned unchanged).
- The collector machine's `REDIS_PORT` must point at the **host** Redis port
  (on this workstation: **16379**), not the container default `6379`.

### Dependency Version Drift (v7.12.7 incident)

`Dockerfile.backend` installs dependencies in **two** steps:

```dockerfile
pip install -r requirements.txt        # = backend/requirements.txt  (mostly pinned)
pip install -r requirements_base.txt   # = root requirements.txt     (mostly floating)
```

The second step wins. Whatever is left floating there is re-resolved on **every
build**, so two builds of nearby commits can end up with different transitive
dependency versions. That is exactly what broke v7.12.7:

| package | v7.12.6 (good) | v7.12.7 (broken) |
|---|---|---|
| kombu | 5.6.2 | **5.7.0** |
| redis (redis-py) | 5.0.1 | 5.0.1 |

`kombu 5.7.0` requires `redis-py>=6.1.0` for its Redis transport, but `redis-py` is
pinned at `5.0.1` in `backend/requirements.txt`. pip does **not** report this
conflict at install time, so the build stayed green and the image shipped. In
production the worker then died on startup:

```
kombu.exceptions.VersionMismatch: Redis transport requires redis-py versions
6.1.0 or later. You have 5.0.1
```

Both `celery-worker` and `celery-beat` crash-looped, so scheduled jobs (auto
invoicing, low-stock alerts, DB backups) stopped. The collection chain was **not**
affected — collection runs inside the API process via asyncio, not through Celery.

**Rule (as of v7.12.9)**: the production image installs **exactly one** dependency
file — `requirements.lock.txt` — and every version in it is pinned with `==`. The
runtime direct dependencies live in `requirements.txt` (also fully pinned), and
dev-only tools live in `requirements-dev.txt` (never installed into the production
image). There is no second install step, so nothing can drift between two files.

**Guards added in v7.12.8**:

- `scripts/verify_image_dependency_pins.py` compares the versions actually installed
  in a built image against the baseline in that script, and cross-checks the baseline
  against the `==` pins in the requirements files.
- The release workflow runs that check right after the backend image is built, so a
  drifted image never reaches the CNB mirror and never gets deployed.
- The startup smoke test now also starts a real Celery worker against a throwaway
  Redis, so a broker-connectivity regression fails the build instead of production.

**Fixed in v7.12.9 — single lock file**:

| file | role | installed into production image |
| --- | --- | --- |
| `requirements.lock.txt` | complete transitive dependency closure (116 packages), all `==` | **yes** (the only install) |
| `requirements.txt` | runtime **direct** dependencies only, all `==` | no (cross-checked against the lock) |
| `requirements-dev.txt` | pytest / linters / testcontainers, all `==` | no |

- `backend/requirements.txt` is **deleted** — the old two-file split was the drift
  source.
- `Dockerfile.backend` and `Dockerfile.collection` install the lock in **one** step.
- The lock was taken from the **measured** `pip freeze` of the running production
  v7.12.8 image, so v7.12.9 ships the exact versions production was already running
  (only the 5 dev tools leave the image). No runtime version change.
- `scripts/verify_image_dependency_pins.py` now **derives** its baseline from
  `requirements.lock.txt` instead of a hand-copied list, and additionally fails on
  floating ranges, a multi-step Dockerfile install, or any package in the image that
  is not in the lock.
- CI installs lock → requirements → dev in that order, so the CI environment and the
  production image resolve the same versions.

## Module Retirement (v7.12.9)

v7.12.9 removes five frontend pages whose backing capability was already dead or
never existed, plus the dead backend code behind them:

| retired page | route | backend permission id | why |
| --- | --- | --- | --- |
| 店铺管理 | `/store-management` | `store-management` | front-end-only mock, 0 API calls |
| 店铺分析 | `/store-analytics` | `store-analytics` | 4 API endpoints, 3 backing views missing in production |
| 财务报表 | `/finance-reports` | `finance-reports` | placeholder page, 0 API calls |
| 汇率管理 | `/fx-management` | `fx-management` | placeholder page, 0 API calls |
| 会计期间 | `/fiscal-periods` | `fiscal-periods` | placeholder page, 0 API calls |

Retirement pattern (reuse it, do not invent a new one):

- `frontend/scripts/moduleSunsetUi.test.mjs` — registers the retired routes and menu
  entries. This file has already retired 22 routes before v7.12.9.
- `frontend/scripts/frontPagePermissionAudit.test.mjs` — audits only the routes that
  are still alive.
- Backend permission ids are removed from `backend/services/permission_service.py`
  (the catalog served by `GET /api/permissions`) **and** from the role defaults in
  `backend/services/system_role_service.py`.
- `ensure_system_roles()` rewrites an existing role's permission list whenever it
  differs from the defaults, so removing an id from the defaults also repairs the
  production `core.dim_role` rows at the next startup — **no manual SQL needed**.

Also removed in v7.12.9:

- `backend/routers/dashboard_api.py` — a Metabase-era **stub** module (its
  `get_metabase_service()` raises `RuntimeError("... tests should monkeypatch it")`).
  It was never included in the production app; `backend/domains/business/routes.py`
  only includes `dashboard_api_postgresql.router`. Deleting it removes 5 dead
  `annual-summary` handlers and the last Metabase-era business-overview duplicates.
- `backend/services/annual_cost_aggregate.py` — zero live references (only the dead
  router above and its own test).
- `annual_summary` service methods, `reduce_annual_summary_kpi_rows`, the
  `api.annual_summary_*` / `api.store_analysis_*` SQL assets, and the
  `mart.shop_hour_traffic_kpi` SQL asset.

**Protected — do not delete**: `core.dim_fiscal_calendar`, `finance.fx_rates`,
`backend/services/profit_basis_service.py`, `labor_cost_policy_service.py`,
`shop_target_workbench_service.py`. These share a name with the retired pages but
carry live logic (fiscal periods are still written by
`profit_basis_service.ensure_fiscal_period_exists()`, and the fiscal calendar table
is referenced by 5 other business tables).

## Monitoring Existence Check (v7.12.9)

`GET /api/data-pipeline/freshness` used to report only what happened **at the time
of the last refresh**, so a target whose view had since been dropped still showed
`status = success` — the monitoring was **green while the asset was gone**. That is
how 9 zombie targets stayed invisible.

v7.12.9 adds a live existence check:

- Each freshness row now carries `object_exists`.
- A target that is registered but whose database object no longer exists is reported
  with `status = "missing"` (the original value is kept in `recorded_status`) and is
  listed in `missing_targets`.
- `GET /api/data-pipeline/lineage` adds `target_object_exists` / `source_object_exists`
  per edge and a `missing_objects` list.

One caveat: a **logical target** may not match its real object name — e.g.
`semantic.alias_registry` is the refresh codename for the table
`semantic.semantic_field_aliases`. Those are registered in
`LOGICAL_TARGET_OBJECTS` (`backend/services/data_pipeline/refresh_validation.py`),
and `backend/tests/data_pipeline/test_data_pipeline_freshness_existence.py` fails if
a new mismatch is not registered — otherwise the check would report a live target as
missing.

## Before Tagging

1. Confirm the working tree is clean or only contains intended release changes
2. Run the focused tests for the changed area
3. Run `python scripts/verify_rules_completeness.py`
4. Run `python scripts/verify_release_local.py`
5. If production compose or env handling changed, verify:
   - `docker-compose.prod.yml` uses `${DATABASE_URL}`
   - local production compose validation uses `--env-file .env.production`
   - no legacy password fallback remains
   - local `.env.production` matches the intended server `.env`
6. If any view asset under `sql/` changed, list the affected targets — the deploy
   rebuilds them automatically (Phase 2.7, see "Dashboard View Definitions" below):
   ```bash
   git diff --name-only v<previous-tag>..HEAD -- sql/
   ```
7. If any dependency file changed, confirm the pins are explicit (`==`) and that the
   baseline in `scripts/verify_image_dependency_pins.py` still matches them — see
   "Dependency Version Drift" above. After v7.12.9 the baseline is derived from
   `requirements.lock.txt`, so the check is: the lock is the only file the backend
   image installs, and every entry in it is `==`-pinned.

## Tag Release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Local Git Mirror Setup

Configure once per workstation:

```bash
git remote set-url --push origin https://github.com/timberdayz/timber_dayz.git
git remote set-url --add --push origin https://cnb.cool/timberdayz/xihong_erp
git remote -v
```

Then initialize the current computer and verify both mirrors before its first push:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Configure
```

Expected result: `origin` has two push URLs while `main` tracks `origin/main`; `cnb/main` is checked as the required mirror reference. The script refuses dirty worktrees, non-main branches, in-progress merges/rebases, remote divergence, and non-fast-forward local history.

## Dashboard View Definitions

Changing a **view definition** under `sql/` does not take effect by deploying alone:
the data refresh path and the dashboard bootstrap both skip views that already exist,
and production runs with `AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP=false`.

The deployment now handles this automatically. `scripts/deploy_remote_production.sh`
runs **Phase 2.7** — after the database migration and the schema gate, and before the
application layer starts:

```bash
python3 /app/scripts/rebuild_views.py --target api.clearance_ranking_module
```

- The rebuild happens while the old backend containers are already stopped, so the
  `CREATE OR REPLACE VIEW` exclusive lock does not block live dashboard queries.
- A failed rebuild aborts the deployment and the rollback path restores the previous
  containers, so the old definition never goes live on its own.
- Target list is configurable via `DEPLOY_REBUILD_VIEW_TARGETS` (space separated).
  The default is `api.clearance_ranking_module`.
- `scripts/rebuild_views.py` must be present in the backend image
  (`Dockerfile.backend`) — enforced by `scripts/verify_remote_deploy_contracts.py`.

## Inventory Layers

The inventory domain has **two independent persisted layers**, and they feed **two different
dashboards**. Do not assume one refresh covers the other:

| Layer | Table | Feeds | Rebuilt by |
| --- | --- | --- | --- |
| Age layer | `mart.inventory_age_current` / `_history` | inventory aging views | `scripts/rebuild_inventory_age_from_snapshots.py` (Phase 3a) |
| State layer | `mart.inventory_state` | clearance rankings (`api.clearance_ranking_module`, `api.sku_clearance_ranking_module`) | `scripts/rebuild_inventory_state_from_snapshots.py` (Phase 3a') |

`mart.inventory_state` is a **table**, not a view — the view rebuild in Phase 2.7 can only
guarantee it exists; **rows are written solely by `InventoryStateRefreshService`**.
If the state layer is empty, `days_since_restock` is NULL for every row, `age_days` collapses
to 0 and the clearance ranking returns **0 rows** (see
`docs/architecture/SYNC_MODULE_REFACTOR_PLAN.md` §3.9.11).

The deployment rebuilds both layers automatically:

```bash
python3 /app/scripts/rebuild_inventory_age_from_snapshots.py --full-rebuild    # Phase 3a
python3 /app/scripts/rebuild_inventory_state_from_snapshots.py --full-rebuild  # Phase 3a'
```

- Both scripts must be present in the backend image (`Dockerfile.backend`) — enforced by
  `scripts/verify_remote_deploy_contracts.py`.
- A failed rebuild aborts the deployment and the rollback path restores the previous containers.
- No row-count assertion is made on purpose: a genuinely empty environment legitimately has
  0 rows, and a row-count gate would report a false failure there.

## Watch GitHub Actions

Expected order:

1. `Outputs Directory Health Check`
2. `Deploy to Production`
3. Inside `Deploy to Production`:
   - `check-config`
   - `Validate Data Flow (Release Gate)`
   - `Build and Push Images (Release Tag)`
   - `Deploy to Production (Tag Release)`
     - remote phases: migrations → schema gate → dashboard bootstrap →
       **Phase 2.7 view rebuild** → backend →
       **Phase 3a/3a' inventory age + state rebuild** → frontend → nginx

## If Deployment Fails

- If it fails in `Validate Data Flow (Release Gate)`, inspect the validation script output first
- If it fails in `Deploy to Production (Tag Release)`, inspect:
  - SSH and host-key steps
  - compose sync step
  - remote migration logs
  - runtime `.env` and `docker-compose.prod.yml` consistency

## After Deployment

1. Confirm the backend health endpoint
2. Confirm key pages load
3. Confirm database migrations are applied
4. Confirm Redis and Celery services are healthy — `celery-worker` must show
   `Up ... (healthy)`, **not** `Restarting`. A container that has only been up for a
   few seconds is crash-looping, and `celery-beat` reports `healthy` while it is
   dying the same way. Read the worker log for a `VersionMismatch` traceback instead
   of trusting the container status alone (see "Dependency Version Drift" above).
5. Confirm the deployed tag matches the intended release
6. If `sql/` view assets changed, confirm Phase 2.7 succeeded:
   - server log: `${PRODUCTION_PATH}/deploy-logs/rebuild_views_<timestamp>.log`
   - the rebuilt view returns rows (a 0-row result usually means the join口径 drifted)
7. Confirm the inventory layers were rebuilt (Phase 3a / 3a'):
   - server log contains `[OK] Inventory age full rebuild completed` and
     `[OK] Inventory state full rebuild completed`
   - `GET /api/data-pipeline/freshness` shows `mart.inventory_state` with a
     `last_succeeded_at` **newer** than the deploy start (not the bootstrap timestamp)
   - `GET /api/dashboard/business-overview/inventory-backlog` shows
     `unknown_restock_row_count` **lower** than the total row count
     (an equal value means the state layer still contributes nothing)
8. Confirm the monitoring existence check behaves (v7.12.9+):
   - `GET /api/data-pipeline/freshness` returns `missing_targets: []` (or only the
     targets that were deliberately cleaned up) and every row carries `object_exists`
   - `GET /api/data-pipeline/lineage` returns `missing_objects: []`
   - a `status` of `"missing"` means the database object is gone — fix the asset
     before trusting that target's numbers
9. Confirm the retired modules are really gone (v7.12.9+):
   - `GET /api/permissions` no longer lists `finance-reports`, `fx-management`,
     `fiscal-periods`, `store-management`, `store-analytics`
   - the retired pages are absent from the menu and their routes no longer resolve
