# Development Environment

This file is the agent-facing baseline for local development environment assumptions. It is a repository adapter for `superpowers`, not a replacement workflow.

## Verified Local Baseline

- Operating system: Windows.
- Shell: PowerShell.
- Python: current local version is Python 3.13.13; use Python 3.11 for CI parity when possible.
- Node.js: current local version is Node.js 24.14.0; `.nvmrc` requires Node.js 24.
- npm: current local version is npm 11.9.0.
- Docker: Docker Desktop is available; current local Docker CLI is 28.5.1.
- Terminal and log output must avoid emoji.
- Repository text source files must be saved as UTF-8 with LF line endings.

## Runtime Requirements

- Backend stack: FastAPI + SQLAlchemy async + Pydantic + PostgreSQL.
- Frontend stack: Vue 3 + Element Plus + Pinia + Vite.
- PostgreSQL: use PostgreSQL 15+ through Docker for local database infrastructure.
- Redis: use Docker; local host port convention is `16379`, container port is `6379`.
- Celery: use Docker for Worker and Beat when background jobs are required.
- Playwright: required for collection authoring, page exploration, snapshots, screenshots, and component testing.

## Local Runtime Topology

The preferred local topology is:

- PostgreSQL runs in Docker.
- Redis runs in Docker.
- Celery Worker and Celery Beat run in Docker when background jobs are needed.
- Backend runs as a local Python process.
- Frontend runs through the local Vite development server.

Default local startup path:

```powershell
python run.py --local
```

When `python run.py --local` is used for collection or scheduled collection on a
Windows machine:

- keep `postgres`, `redis`, `celery-worker`, and `celery-beat` in Docker
- run backend and frontend as local processes
- do not keep Docker `backend-api` or Docker `backend-collector` running at the
  same time

Otherwise the frontend proxy on `localhost:8001` can target the wrong backend,
and scheduled collection may be consumed by the container runtime instead of the
local takeover runtime.

Do not invent alternative startup paths unless the task explicitly requires debugging startup infrastructure.

## Environment Variables

Use `docs/guides/ENV_FILE_CONTRACT.md` before reading or changing `.env*` and `env*.example` files. Use the existing environment examples and runtime guides as the source of truth. For local Redis, the expected baseline is:

```env
REDIS_PORT=16379
REDIS_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_BROKER_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_RESULT_BACKEND=redis://:redis_pass_2025@localhost:16379/0
```

Do not start a duplicate manual Redis container when the repository Docker runtime already provides Redis.

## Agent Rules

- Before changing runtime assumptions, inspect `docs/guides/ENVIRONMENT_MODEL.md` and `docs/guides/LOCAL_DEV_RUNTIME_GUIDE.md`.
- Before reading or changing environment files, inspect `docs/guides/ENV_FILE_CONTRACT.md`.
- Before adding new dependencies, verify whether they affect local, Docker, production, or collection environments.
- For collection work, also inspect `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`.
- For launch-period work, follow `docs/guides/PRE_LAUNCH_RULES.md` and avoid broad environment refactors.
- Use `.editorconfig` and `.vscode/settings.json` as the local editor baseline for UTF-8 source hygiene.
