# Release Checklist

## Release Source Of Truth

- Production release is triggered by `git push origin vX.Y.Z`
- Deployment truth comes from the release tag, not `origin/main`
- Push `main` to `origin` only when you intentionally want GitHub branch history to match local history
- Local `origin` has two push URLs: GitHub and CNB Git. `main` tracks `cnb/main`; mirror normal branch updates through `powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync`, not VS Code/Cursor Sync or a single-remote push.
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

## Tag Release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Local Git Mirror Setup

Configure once per workstation:

```bash
git remote set-url --push origin git@github.com:timberdayz/timber_dayz.git
git remote set-url --add --push origin https://cnb.cool/timberdayz/xihong_erp
git remote -v
```

Then initialize the current computer and verify both mirrors before its first push:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Configure
```

Expected result: `origin` has two push URLs while `main` tracks `cnb/main`. The script refuses dirty worktrees, non-main branches, in-progress merges/rebases, remote divergence, and non-fast-forward local history.

## Watch GitHub Actions

Expected order:

1. `Outputs Directory Health Check`
2. `Deploy to Production`
3. Inside `Deploy to Production`:
   - `check-config`
   - `Validate Data Flow (Release Gate)`
   - `Build and Push Images (Release Tag)`
   - `Deploy to Production (Tag Release)`

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
