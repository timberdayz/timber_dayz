# Release Checklist

## Release Source Of Truth

- Production release is triggered by `git push origin vX.Y.Z`
- Deployment truth comes from the release tag, not `origin/main`
- Push `main` to `origin` only when you intentionally want GitHub branch history to match local history
- Local `origin` has two push URLs: GitHub and CNB Git. `main` keeps the existing GitHub `origin/main` upstream so normal Cursor/VS Code pull behavior remains unchanged. Use `powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync` before publishing a completed `main` change; it checks the CNB mirror before writing either remote.
- CNB registry is used as the preferred production image pull source in China; CNB Git is only a code mirror.

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
4. Confirm Redis and Celery services are healthy
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
