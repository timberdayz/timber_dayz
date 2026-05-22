# Environment Model

This file is a repository adapter for `superpowers`. It defines environment boundaries so agents do not mix local development, Docker infrastructure, production, and collection runtime assumptions.

## Local Development

- Local development runs on Windows with PowerShell.
- Backend may run as a local Python process.
- Frontend may run through Vite.
- PostgreSQL, Redis, and Celery infrastructure should use Docker unless the task explicitly targets infrastructure setup.
- Default local startup reference is `docs/guides/DEVELOPMENT_ENVIRONMENT.md`.

## Docker Development

- Docker Compose files define local and deployment-like infrastructure.
- Do not assume a container is production merely because it runs through Docker.
- Before changing Docker files, identify whether the target is local development, collection, cloud, or production.

## Production Runtime

- Production changes must follow the tag-driven release model.
- Production deployment truth is the release tag, not `origin/main`.
- Do not change production runtime behavior as part of cleanup unless it is required for the task.

## Production Collection Runtime

- Production collection runtime should run stable canonical components.
- Do not run `pwcli` exploration output directly as production collection code.
- New collection authoring uses `pwcli + playwright skill + agent`, then promotes verified canonical Python components through the existing component lifecycle.

## Agent Rules

- State which environment a task affects before changing runtime behavior.
- Do not copy local-only values into production examples.
- Do not use production secrets or real account credentials in documentation, tests, or generated code.
