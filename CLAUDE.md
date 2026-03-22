# CLAUDE.md

This file gives repository context for AI coding agents.

## Project Overview

- Project: 西虹 ERP
- Version: `v4.20.0`
- Architecture: SSOT + Contract-First + async-first backend
- Backend: FastAPI + SQLAlchemy async + PostgreSQL
- Frontend: Vue 3 + Element Plus + Pinia + Vite
- Node.js: `24+` from [`.nvmrc`](F:/Vscode/python_programme/AI_code/xihong_erp/.nvmrc)

## Workflow Priority

This repository is now skill-first:

1. User instructions
2. Repository-specific technical constraints in [`.cursorrules`](F:/Vscode/python_programme/AI_code/xihong_erp/.cursorrules)
3. `superpowers` and `planning-with-files`
4. Other downloaded skills
5. Historical material under [`openspec/`](F:/Vscode/python_programme/AI_code/xihong_erp/openspec)

Interpretation:

- Skills define the default workflow.
- Repository rules only add stack-specific, safety-specific, and architecture-specific constraints.
- `openspec/` stays in the repo for historical reference only. It is not the active planning workflow.

## Skill-First Workflow

| Scenario | Preferred workflow |
|---|---|
| New feature or behavior change | `brainstorming` -> `writing-plans` -> `test-driven-development` -> `verification-before-completion` |
| Bug fix | `systematic-debugging` -> `test-driven-development` -> `verification-before-completion` |
| Complex refactor, migration, or research | `planning-with-files` |
| Frontend design work | `ui-ux-pro-max` + `frontend-design`, implemented in Vue 3 + Element Plus |
| Browser testing | `webapp-testing`; standalone scripts may use sync Playwright, runtime backend code stays async |

Root planning files are intentionally allowed:

- `task_plan.md`
- `findings.md`
- `progress.md`

They are gitignored and are part of the active workflow.

## Common Commands

### Startup

```bash
python run.py --local
python run.py --use-docker
python run.py --with-metabase  # legacy/debug only
python local_run.py
python run.py --backend-only
python run.py --frontend-only
python run_new.py
```

### Database

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

### Validation

```bash
python scripts/verify_architecture_ssot.py
python scripts/verify_root_md_whitelist.py
python scripts/verify_rules_completeness.py
python scripts/verify_no_emoji.py
python scripts/verify_api_contract_consistency.py
python scripts/identify_dead_code.py
```

### Testing And Quality

```bash
pytest
pytest --cov=backend --cov=modules --cov-report=html
black . --line-length 88
isort .
ruff check .
mypy backend/
```

### Release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Release interpretation:

- GitHub Actions production deployment is triggered by release tags.
- `origin/main` is not the release source of truth.
- `main`, `cnb/main`, and `origin/main` can legitimately differ if only tags are pushed to GitHub.
- If you want GitHub branch state to match local branch state, push `main` separately.

## Repository Constraints

- ORM models are defined only in `modules/core/db/schema.py`
- Pydantic models belong in `backend/schemas/`, not in routers
- New backend runtime code uses `AsyncSession` and `get_async_db()`
- New CRUD-style services should build on `backend/services/base_service.py`
- Frontend code must stay in the Vue 3 ecosystem; do not introduce React or React Native patterns
- Frontend API calls go through `frontend/src/api/`
- In FastAPI routes and backend services, Playwright usage must be `async_playwright`
- Standalone scripts and tests may use sync Playwright when appropriate
- Use `datetime.now(timezone.utc)`, not `datetime.utcnow()`
- Avoid emoji in terminal and log output

## Dashboard Architecture

- Dashboard cutover is PostgreSQL-first and no longer treats Metabase as the target steady-state query layer.
- Preferred Dashboard flow is `b_class raw -> semantic -> mart -> api -> backend -> frontend`.
- `semantic` owns standardization, `mart` owns reusable aggregation, and `api` owns page-module query contracts.
- Use `USE_POSTGRESQL_DASHBOARD_ROUTER` to switch the runtime Dashboard router during gray rollout.
- Treat Metabase as legacy fallback/debug infrastructure unless a task explicitly requires it.

## Documentation Map

| File | Purpose |
|---|---|
| [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md) | Active workflow entrypoint |
| [`.cursorrules`](F:/Vscode/python_programme/AI_code/xihong_erp/.cursorrules) | Repository-specific constraints |
| [`.cursor/rules/skill-integration.mdc`](F:/Vscode/python_programme/AI_code/xihong_erp/.cursor/rules/skill-integration.mdc) | Skill adaptation rules |
| [`docs/DEVELOPMENT_RULES/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/DEVELOPMENT_RULES/README.md) | Detailed reference index |
| [`docs/guides/RELEASE_CHECKLIST.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/RELEASE_CHECKLIST.md) | Tag release and post-release verification checklist |
| [`docs/superpowers/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/superpowers/README.md) | Skill-first planning/spec locations |
| [`openspec/`](F:/Vscode/python_programme/AI_code/xihong_erp/openspec) | Historical archive only |

Always answer users in Chinese unless they explicitly ask for another language.
