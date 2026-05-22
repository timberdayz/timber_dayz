# Development Workflow

This file contains operational commands. Repository rules live in `AGENTS.md`.

## Startup

Default local startup:

```bash
python run.py --local
```

Other supported modes:

```bash
python run.py --use-docker
python run.py --backend-only
python run.py --frontend-only
```

Legacy or specialized launchers may exist in the repository. Do not present them as the default path unless the task specifically requires them.

## Database

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## Validation

```bash
python scripts/verify_architecture_ssot.py
python scripts/verify_rules_completeness.py
python scripts/verify_no_emoji.py
python scripts/verify_api_contract_consistency.py
```

## Testing And Quality

Run the narrowest relevant tests first, then broaden when the change touches shared behavior.

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
