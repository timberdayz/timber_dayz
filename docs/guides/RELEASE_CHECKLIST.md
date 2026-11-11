# Release Checklist

## Release Source Of Truth

- Production release is triggered by `git push origin vX.Y.Z`
- Deployment truth comes from the release tag, not `origin/main`
- Push `main` to `origin` only when you intentionally want GitHub branch history to match local history
- Local `origin` has two push URLs: GitHub **over SSH-443** and CNB Git over HTTPS. `main` keeps the existing GitHub `origin/main` upstream so normal Cursor/VS Code pull behavior remains unchanged. This is the **permanent** state since 2026-11-11 — GitHub's HTTPS endpoint is unreachable from this network, so `git push origin main` now goes to GitHub over `ssh://git@ssh.github.com:443/...` and needs **no per-push environment variables**. Use `powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync` before publishing a completed `main` change; it checks the CNB mirror before writing either remote.
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

`https://github.com` is unreachable from this network (DNS resolves, TCP/443
times out); GitHub's **SSH endpoint on port 443** stays reachable. The
repository's push URLs were therefore configured **once, permanently** — there is
no per-release dance left:

```powershell
git config --unset-all remote.origin.pushurl          # clear first — see the trap below
git remote set-url --add --push origin "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
git remote set-url --add --push origin "https://cnb.cool/timberdayz/xihong_erp"
git config core.sshCommand "ssh -i C:/Users/18689/.ssh/github_actions_deploy -o IdentitiesOnly=yes"
```

End-to-end proof (2026-11-11): `git push origin main` with **no environment
variables** reached both mirrors and reported `Everything up-to-date`.

> ⚠️ **Trap A — `git remote set-url --push origin <url>` does NOT replace a push
> URL when several push URLs are configured.** It fails with `multiple values`
> and exits fatally, and `--add` only *appends* (a repeated `--add` leaves
> duplicate entries behind). Always `git config --unset-all remote.origin.pushurl`
> first, then re-add **in order**. Verify with
> `git config --get-all remote.origin.pushurl`. Measured 2026-11-11.

> ⚠️ **Trap B — `git remote set-url origin <ssh-url>` only rewrites the *fetch*
> URL.** It does not change what `git push origin` uses, so switching the fetch
> URL alone never fixes a push.

> ⚠️ **Trap C — `git fetch <url>` does NOT update the remote-tracking refs**
> (e.g. `origin/main`). After fetching by URL, `origin/main` can still show the
> old SHA ⇒ a later "is it already pushed?" check reads stale data. Use
> `git ls-remote <url> refs/heads/main` as the authoritative remote state.

`scripts/sync_main_mirrors.ps1 -Sync` pushes **by explicit URL** (`$GitHubUrl` /
`$CnbUrl`) rather than by remote name, so it works with the SSH-443 form.
**But** `-Configure` rebuilds the push list from its parameters, and its default
`$GitHubUrl` is the **unreachable HTTPS URL** ⇒ running `-Configure` without
`-GitHubUrl` silently reverts this permanent fix. Always pass it explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Configure `
    -GitHubUrl "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
```

The two-mirror contract is unchanged (both remotes still receive the same commit);
only the transport to GitHub differs. Verified 2026-11-03: both mirrors ended at the
same SHA.

### Release Tag Parity Across Mirrors (CNB Git is a mirror, not a deploy trigger)

Every release tag must exist on **both** mirrors with the **same tag object**:

```powershell
git ls-remote --tags cnb refs/tags/vX.Y.Z
git ls-remote --tags "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git" refs/tags/vX.Y.Z
```

Both lines must print the same object id (annotated tags also peel with `^{}`).

**Pushing a tag to CNB Git is inert** (verified 2026-11-10, before backfilling `v7.19.3`):

- The repo has **no `.cnb.yml`**, and never had one on any branch
  (`git log --all --diff-filter=A --name-only -- '.cnb.yml'`) ⇒ CNB has no in-repo pipeline definition.
- The CNB remote exposes only `HEAD`, `refs/heads/main` and `refs/tags/*` — **no pipeline refs**.
- CNB Git's documented role is **code mirror only**; the CNB **image registry** is fed by the GitHub
  deploy workflow itself (`deploy-production.yml` logs in to `docker.cnb.cool` with `CNB_TOKEN` and
  pushes the `vX.Y.Z` images there).
- Empirically: the `v7.19.4` tag **was** pushed to CNB Git, and the production host recorded
  **exactly one** deploy batch afterwards (`/opt/xihong_erp/deploy-logs`, batch `20261110_123449`),
  with container `StartedAt` unchanged at `04:38–04:42Z`. A CNB-side tag trigger would have produced
  a second batch.

> ⚠️ The **GitHub** side is different: `deploy-production.yml` triggers on `push tag v*`, so pushing a
> **new** tag to GitHub **deploys to production**. Never backfill a tag on the GitHub side — backfill
> the mirror (CNB) only, and only with a tag object that already exists locally.

**Procedure when a mirror is missing a tag** (measured 2026-11-10, `v7.19.3` missing on CNB):

```powershell
# 1. confirm object identity before writing anything
git rev-parse v7.19.3
git ls-remote --tags "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git" refs/tags/v7.19.3

# 2. push the SAME existing object to the mirror only (never re-create it)
git push cnb 'refs/tags/v7.19.3:refs/tags/v7.19.3'

# 3. re-verify parity
git ls-remote --tags cnb refs/tags/v7.19.3
```

After the push, confirm **no deployment was triggered**: `gh run list --workflow deploy-production.yml`
must still show the previous release, and the production `deploy-logs` directory must show no new batch.

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

## Module Retirement (v7.13.0)

v7.13.0 retires the **business-overview 「滞销清理排名（月度）」board** — a section
inside the business overview page, not a route.

| retired thing | where | why |
| --- | --- | --- |
| 滞销清理排名（月度） board | `frontend/src/domains/business/views/BusinessOverview.vue` | shop-level monthly ranking vs SKU-level ageing are two different calibers mixed into one board; the ranking reads the order domain and re-derives identities every request |
| `GET /api/dashboard/clearance-ranking` | `backend/domains/business/routers/dashboard_api_postgresql.py` | endpoint of the retired board |
| `PostgresqlDashboardService.get_clearance_ranking` | `backend/services/postgresql_dashboard_service.py` | service of the retired board |
| `api.clearance_ranking_module` | `sql/api_modules/clearance_ranking_module.sql` | the view behind it |
| `dashboard_clearance_ranking` cache key | `backend/services/cache_service.py` | warmup + invalidation of the retired endpoint |

**Protected — do not delete**: `api.sku_clearance_ranking_module` and
`backend/services/inventory/sku_clearance_service.py`. The SKU-level clearance
list (库存 → 滞销清单) is a **different** module: it reads `mart.inventory_state`
(distance since last restock), not the order domain, and it stays.

Also removed in v7.13.0 (the dead write path of the retired board):

- `backend/services/clearance_ranking_service.py` — zero live references.
- ORM model `ClearanceRanking` and table `c_class.clearance_rankings` — the
  table's only writer was that service, and it had 0 rows in production.
  Leaving the table would leave a **write path that can resurrect a retired
  module**, so it goes with the model (schema SSOT + baseline + migration).
- `sql/metabase_questions/clearance_ranking.sql` — Metabase-era leftover.

Retirement pattern for a **pipeline module** (extends the v7.12.9 pattern):

- The pipeline module key in `DASHBOARD_MODULE_TARGETS` was `clearance_ranking`
  but it actually owned the **inventory-backlog asset group**
  (`mart.inventory_backlog_base` + its downstream api views). It was renamed to
  `inventory_backlog` rather than deleted, because the invariant
  *「基表与它的全部下游必须放在同一个模块里」* must hold: dropping the module
  would have left `mart.inventory_backlog_base` with no owner and the business
  overview 库存积压 cards would never be rebuilt after a collection.
- The frontend still checks **two** modules for `blocked`
  (`business_overview` + `inventory_backlog`) — same protection as before.
- A migration must clean the **monitoring** rows, not just the view:
  `ops.dashboard_asset_state` (module row), `ops.data_freshness_log`
  (zombie freshness — v7.12.9's monitoring reports a registered target whose
  object no longer exists as `status=missing`) and `ops.data_lineage_registry`
  (zombie lineage edges).
- `sql/api_modules/<name>.sql` must also be removed from
  `backend/services/data_pipeline/refresh_registry.py`
  (`PIPELINE_DEPENDENCIES` + `SQL_TARGET_PATHS`),
  `backend/services/data_pipeline/dashboard_bootstrap.py` (asset group),
  `backend/services/event_listeners.py` (refresh targets) and
  `backend/tasks/refresh_queue_tasks.py` (cache invalidation).
- The **deploy-time default view rebuild target** lives in
  `scripts/deploy_remote_production.sh` (`DEPLOY_REBUILD_VIEW_TARGETS`) and is
  **asserted as a literal** by `scripts/verify_remote_deploy_contracts.py` —
  retiring a view means changing both.

## Materialized View for a Slow Semantic Layer (v7.13.0)

The business overview and B-cost pages were 504-ing because
`semantic.fact_orders_atomic` is a **plain view**: every row runs a shop-alias
resolution (`LEFT JOIN LATERAL`), and PostgreSQL cannot push a `metric_date`
filter below the dedup window, so each request re-scans and re-parses all 9
B-class order tables (~20 s). The fix is to **materialize the atomic layer**.

Pattern to copy when a semantic view is the slow part of a request path:

| step | what | why |
| --- | --- | --- |
| 1 | measure the **row/caliber composition** of the source tables in production before designing | it decides whether a *source swap* is even safe (here: 38,607 rows = monthly 36,624 + weekly 1,506 + daily 477, and the dedup window never actually merged anything) |
| 2 | materialize the **whole** atomic view (`SELECT * FROM <plain view>`), not a per-granularity rebuild | the MV body is the plain view body ⇒ **zero caliber change**; a source swap changes the row set and drifts money |
| 3 | refresh with **「exists → REFRESH in place / not exists → CREATE」**, never `DROP ... CASCADE` | CASCADE deletes downstream objects — including ones that are **not registry-rebuildable** (`mart.hr_shop_monthly_profit`, `mart.inventory_backlog_base_mv`) and ones outside the bootstrap plan (the B-cost chain) ⇒ deleted and never rebuilt |
| 4 | keep the MV body referencing the plain view | the MV then always follows the plain view's latest definition (`CREATE OR REPLACE VIEW`) ⇒ no "file changed but MV is stale" drift |
| 5 | register the MV in `refresh_registry.PIPELINE_DEPENDENCIES` + `SQL_TARGET_PATHS`, and in `dashboard_bootstrap`'s `refresh_targets` | refresh order is enforced by the dependency graph; the MV must be rebuilt before its consumers |
| 6 | migration creates the MV + indexes and rebuilds the consumers **from the `sql/` assets** | the asset files stay the SSOT for view definitions; copying them into the migration creates a second copy that drifts |

Guards live in `backend/tests/data_pipeline/test_atomic_materialized_views.py`:
the MV body must be `SELECT * FROM <plain view>`, the MV assets must not contain
`DROP MATERIALIZED VIEW`, and the two non-rebuildable downstream views must keep
reading the plain view.

### v7.13.0 post-deploy acceptance (atomic materialization)

The deploy runs migration `20261105_create_atomic_materialized_views`, which
creates the two materialized views and rebuilds the six consumers from the
`sql/` assets. **Capture the caliber baseline BEFORE deploying** (read-only),
then compare after:

```sql
-- baseline: B-cost per-month totals (before/after must be byte-identical)
WITH monthly_base AS (
    SELECT date_trunc('month', metric_date)::date AS period_month,
           platform_code, shop_id, currency_code,
           SUM(paid_amount) AS gmv, SUM(purchase_amount) AS purchase_amount,
           SUM(warehouse_operation_fee) AS wh_fee,
           SUM(platform_total_cost_itemized) AS platform_itemized
    FROM semantic.fact_orders_atomic
    GROUP BY 1, 2, 3, 4
)
SELECT period_month, count(*), round(sum(gmv), 2), round(sum(purchase_amount), 2),
       round(sum(wh_fee), 2), round(sum(platform_itemized), 2)
FROM monthly_base GROUP BY period_month ORDER BY period_month;
```

Also compare `mart.shop_day_kpi` / `mart.shop_week_kpi` /
`mart.platform_day_kpi` / `mart.platform_week_kpi` row-by-row.

Acceptance:

- B-cost per-month totals: **identical** (not "close"). A difference means the
  MV is not the same row set as the plain view — stop and roll back.
- `operational-metrics` and `bootstrap` P95 < 3s (was ~23s).
- B-cost endpoints P95 < 5s (were 20s+).
- `mart.hr_shop_monthly_profit` and `mart.inventory_backlog_base_mv` still
  exist and still query — they read the plain view on purpose.
- nginx error log: **0 new 5xx** over 24h.

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

Configure once per workstation. **GitHub's HTTPS endpoint is unreachable from this
network**, so the GitHub push URL must be the SSH-443 form:

```bash
git config --unset-all remote.origin.pushurl
git remote set-url --add --push origin "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
git remote set-url --add --push origin "https://cnb.cool/timberdayz/xihong_erp"
git config core.sshCommand "ssh -i C:/Users/18689/.ssh/github_actions_deploy -o IdentitiesOnly=yes"
git remote -v
```

> ⚠️ Do **not** use the old `git remote set-url --push origin https://github.com/...`
> form: it points the GitHub push channel at the unreachable HTTPS endpoint and
> every `git push origin` fails at the first hop. And `git remote set-url --push`
> **refuses to replace** an existing multi-entry push list (`multiple values`),
> so `--unset-all` must come first and `--add` must follow in order.
> See "Mirroring `main` When GitHub HTTPS Is Unreachable" above.

Then initialize the current computer and verify both mirrors before its first push:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Configure `
    -GitHubUrl "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
```

> ⚠️ `-Configure` **rebuilds** `remote.origin.pushurl` from its parameters, and
> the script's default `$GitHubUrl` is the unreachable HTTPS URL ⇒ omitting
> `-GitHubUrl` silently reverts the SSH-443 push URL. Always pass it explicitly.

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

## Field-Measured Release Rules (2026-11-10 / 2026-11-11)

Six rules that each cost real time during the v7.19.5 / v7.20.1 releases. Every
number below was **measured** on this machine or on the production host.

### 1. The version number lives in **two** places — `VERSION` and the tag

`backend/main.py::_load_app_version()` resolves the reported version in this order:
`APP_VERSION` → `IMAGE_TAG` → `RELEASE_VERSION` → the repository-root `VERSION`
file → `"dev"`. A stale `VERSION` therefore makes `/healthz/ready` report an **old**
version even though the image itself is new — measured: production served `v7.2.1`
while `v7.19.5` was live.

- Bump `VERSION` **in the same commit** that creates the tag.
- The dev compose must expose it too: `APP_VERSION` on backend-api / collector /
  celery-worker / celery-beat, plus `./VERSION:/app/VERSION:ro` so the file
  fallback resolves inside the container.
- After deploying, the version reported by `/healthz/ready` **and** by
  `docker compose ps` must equal the tag.

### 2. Verify the mirrors with `ls-remote`, not with a fetched tracking ref

`git fetch <url>` does **not** update `origin/main` (or `cnb/main`), so the local
tracking refs can silently keep an old SHA. The authoritative remote state is:

```powershell
git ls-remote "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git" refs/heads/main
git ls-remote cnb refs/heads/main
git ls-remote "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git" 'refs/tags/vX.Y.Z*'
git ls-remote cnb 'refs/tags/vX.Y.Z*'
```

Both mirror lines must print the same object id (annotated tags also peel with `^{}`).

### 3. A cron/rotation-style mechanism needs a **second** cycle to be accepted

The logrotate config landed on 2026-11-10 and the first real rotation happened on
**2026-11-11 03:17** — but only `access.log` rotated, because it was
316,827,303 B (`maxsize 100M` forces a rotation). `error.log` (22,316,693 B) did
**not** rotate on that first cycle: logrotate only *records* the state for files
modified inside the interval and defers them to the next cycle.

- Acceptance rule: verify such a mechanism **once per cycle**, then re-check on the
  next cycle before declaring it done.
- Concrete indicators: the rotation counter in `logrotate.state` (`error.log` was
  `0` while `access.log` was `1`) and the existence of `error.log.1`.

### 4. "The pipeline says success" is **not** acceptance — verify over SSH yourself

After the deploy, log in independently (read-only) and check:

- all 7 containers `healthy`, and the application containers report the **intended
  tag** (measured: backend-api / celery-worker / celery-beat / frontend all on the
  released tag);
- the database version is **unchanged** (no migration ran);
- the connection count stays constant (measured: 18 before and after);
- the disk usage and the reclaimed space (measured: 352 MB reclaimed);
- `deploy-logs` contains **exactly one** new batch — a second batch would mean the
  mirror triggered a deploy as well.

A green pipeline only proves the pipeline's own steps ran.

### 5. A readiness probe must connect **the way the workload will connect**

The official `postgres` image first starts a **socket-only** temporary server for
`initdb`. A container-local `pg_isready` (default = unix socket) reports
"accepting connections" during that window ⇒ the job continues while the real
server is still starting ⇒ the next step fails with
`FATAL: the database system is starting up` (measured: CI run `42842488697` red,
re-run green).

- Measured 2026-11-11 on this machine (fresh `postgres:15-alpine` container, both
  probes polled at 20 ms in the same clock): the socket probe reported "accepting
  connections" **0.51 / 0.49 / 0.50 / 0.52 s before** the TCP probe did, across
  4 runs ⇒ a **reproducible false-ready window**. A CI runner (slower disk, more
  contention) widens it, which is exactly the "randomly red, green on re-run"
  symptom.
- The readiness criterion is "**actually connect once**", using the same path the
  workload uses: TCP + target database + target account.
- For container-local probes, `pg_isready -h 127.0.0.1` switches the probe from the
  socket to TCP (the temporary server does not listen on TCP). Verified exit codes:
  a wrong user/database still exits `0` (pg_isready does not authenticate), and a
  port with no listener exits `2` ⇒ the health check fails exactly while the
  server is not yet serving.
- Where a real failure is possible, retry once — but the **last** exit code must
  remain the step's exit code, so a genuine failure still fails the gate.

### 6. In a shared worktree, commit through an **isolated index**

When several sessions share one worktree, a normal `git add -A` / commit can sweep
another session's in-flight changes into the commit. Commit through an isolated
index instead — it touches neither the working tree nor the other session's files:

```powershell
$env:GIT_INDEX_FILE = "$env:TEMP\xihong_index"
git read-tree <base>
git update-index --add --cacheinfo 100644,<blob>,<path>
$tree = git write-tree
$commit = git commit-tree $tree -p <parent> -m "<message>"
git update-ref refs/heads/main $commit <old-head>
```

- Never `git stash` — it would move another session's work.
- Never switch branches inside a shared worktree; use a dedicated
  `git worktree add` for the branch you own.
