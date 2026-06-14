# Development Workflow

This file contains operational commands. Repository rules live in `AGENTS.md`.

## Startup

Default local startup:

```bash
python run.py --local
```

For headed collection and cloud sync on a Windows laptop, use the mode-specific
wrappers documented in `docs/guides/LOCAL_COLLECTION_TAKEOVER.md`.

Formal collection laptop mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1
```

Development collection takeover mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1
```

Both collection modes keep Docker `backend-api` and Docker `backend-collector`
stopped. Docker should run only the infrastructure and background queue support
services: `postgres`, `redis`, `celery-worker`, and `celery-beat`. The Windows
host owns the local backend process and visible Playwright browser.

Local Redis in these modes is a temporary broker/cache for development. It is
not intended to preserve long-lived queue state across abnormal Windows
shutdowns. If Redis startup fails after an unexpected shutdown, repair it
before rebuilding the local volume:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -FixAof
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -Rebuild
```

Before shutting down the machine, prefer:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop
```

Other supported modes:

```bash
python run.py --use-docker
python run.py --backend-only
python run.py --frontend-only
```

Legacy or specialized launchers may exist in the repository. Do not present them
as the default path unless the task specifically requires them.

### Dashboard Asset Check

Before manually validating Business Overview or other PostgreSQL dashboard pages
locally, verify dashboard assets first:

```bash
python scripts/bootstrap_postgresql_dashboard.py --module business_overview --check --json
```

If `ready=false`, bootstrap the module and re-check:

```bash
python scripts/bootstrap_postgresql_dashboard.py --module business_overview
python scripts/bootstrap_postgresql_dashboard.py --module business_overview --check --json
```

## Database

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## Validation

```bash
python scripts/verify_utf8_source_hygiene.py
python scripts/verify_architecture_ssot.py
python scripts/verify_rules_completeness.py
python scripts/verify_no_emoji.py
python scripts/verify_api_contract_consistency.py
```

On Windows, do not rely on editor auto-detection for source encoding. Keep source
files in UTF-8 and let the repository guardrails fail fast if mojibake or
template corruption is introduced.

## Testing And Quality

Run the narrowest relevant tests first, then broaden when the change touches
shared behavior.

```bash
pytest
pytest --cov=backend --cov=modules --cov-report=html
black . --line-length 88
isort .
ruff check .
mypy backend/
```

## Release

Production deployment is tag-driven:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Use `docs/guides/RELEASE_CHECKLIST.md` for the release checklist.
