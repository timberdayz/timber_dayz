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
       **Phase 2.7 view rebuild** → backend → frontend → nginx

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
