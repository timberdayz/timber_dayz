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

Do not invent alternative startup paths unless the task explicitly requires debugging startup infrastructure.

## Environment Variables

Use the existing environment examples and runtime guides as the source of truth. For local Redis, the expected baseline is:

```env
REDIS_PORT=16379
REDIS_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_BROKER_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_RESULT_BACKEND=redis://:redis_pass_2025@localhost:16379/0
```

Do not start a duplicate manual Redis container when the repository Docker runtime already provides Redis.

## Agent Rules

- Before changing runtime assumptions, inspect `docs/guides/ENVIRONMENT_MODEL.md` and `docs/guides/LOCAL_DEV_RUNTIME_GUIDE.md`.
- Before adding new dependencies, verify whether they affect local, Docker, production, or collection environments.
- For collection work, also inspect `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`.
- For launch-period work, follow `docs/guides/PRE_LAUNCH_RULES.md` and avoid broad environment refactors.
