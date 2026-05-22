# Project Structure

This file is the agent-facing map of repository ownership, file placement, and boundary contracts.

## Top-Level Map

- `AGENTS.md`: single active repository rule entrypoint.
- `CLAUDE.md`: thin Claude adapter; not a duplicated rule source.
- `backend/`: FastAPI application code, routers, schemas, services, tasks, and backend tests.
- `frontend/`: Vue 3 application, API wrappers, stores, routes, services, components, and UI assets.
- `modules/core/`: shared core database and domain primitives.
- `modules/core/db/schema.py`: ORM SSOT.
- `modules/components/`: shared collection component base classes and reusable component primitives.
- `modules/platforms/`: platform adapters and platform-specific canonical collection components.
- `modules/services/`: shared service layer used by backend and collection runtime code.
- `collectors/`: legacy or narrow collector entrypoints; do not place new canonical components here by default.
- `sql/`: PostgreSQL assets for semantic, mart, API, migration, and operational SQL layers.
- `scripts/`: repository automation, verification, development helpers, and fallback PowerShell wrappers.
- `docs/`: active documentation, architecture references, guides, ADRs, and archived material.
- `tests/`: repository-level tests that do not belong to a narrower package-specific test directory.
- `docker/`, `nginx/`, `monitoring/`, `security/`: deployment and operational infrastructure.

## Backend Boundaries

- Routers belong in `backend/routers/` or the matching `backend/domains/*/routers/` package.
- Pydantic request and response contracts belong in `backend/schemas/`, not in routers.
- Business services belong in `backend/services/`.
- Domain-specific backend code should stay under the matching `backend/domains/` or service module.
- New async runtime code should use `AsyncSession` and `get_async_db()`.
- CRUD-style services should reuse `AsyncCRUDService` from `backend/services/base_service.py`.
- New typed endpoints should declare `response_model` when returning structured payloads.

## Database Boundaries

- ORM SSOT is `modules/core/db/schema.py`.
- Do not create a second SQLAlchemy declarative base.
- Alembic migrations belong in `migrations/`.
- PostgreSQL SQL assets belong in `sql/`.
- Dashboard SQL follows `b_class raw -> semantic -> mart -> api -> backend router -> frontend`.
- `semantic` standardizes source data, `mart` owns reusable aggregates, and `api` owns page-module query shapes.

## Frontend Boundaries

- Frontend API access belongs in `frontend/src/api/`.
- Shared UI components belong in `frontend/src/components/`.
- Route definitions belong in `frontend/src/router/`.
- Pinia stores belong in `frontend/src/stores/`.
- Domain UI modules belong in `frontend/src/domains/` or the existing feature-specific folder.
- Do not call backend endpoints directly from arbitrary components when an API wrapper should own the contract.

## Collection Boundaries

- Active collection authoring uses `pwcli + playwright skill + agent`.
- Shared component primitives belong in `modules/components/`.
- Platform-specific canonical components belong in `modules/platforms/<platform>/components/`.
- Platform adapters belong in `modules/platforms/<platform>/adapter.py`.
- Agent-generated canonical Python components are the supported output path for new collection work.
- Root-level `collectors/` is not the default destination for new canonical components.
- Legacy recorder scripts, backend `/recorder` APIs, and frontend recorder pages are maintenance-only unless explicitly requested.

## Documentation Boundaries

- Active documentation entrypoints are listed in `docs/ACTIVE_DOCS.md`.
- Architecture decisions belong in `docs/adr/`.
- Architecture references belong in `docs/architecture/`.
- Implementation standards belong in `docs/DEVELOPMENT_RULES/`.
- Runbooks and guides belong in `docs/guides/`.
- Historical material belongs in `archive/`, `docs/archive/`, or `openspec/`.

## Where Not To Put Things

- Do not add new root-level temporary reports, screenshots, or one-off scripts.
- Do not add ad hoc backup source files beside active source files.
- Do not place Pydantic contracts inside routers.
- Do not place frontend API calls outside `frontend/src/api/` unless there is an existing local convention for that feature.
- Do not add new Metabase runtime dependencies for active Dashboard work when equivalent PostgreSQL assets exist.
- Do not treat `.cursorrules`, `.cursor/rules/*`, or `openspec/` as active rule sources.

## Related References

- `docs/architecture/BOUNDARIES.md`
- `docs/architecture/DASHBOARD.md`
- `docs/DEVELOPMENT_RULES/README.md`
- `docs/guides/AGENT_TASK_CONTRACT.md`
- `docs/guides/VERIFICATION_MATRIX.md`
