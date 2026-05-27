# Architecture Boundaries

This file defines ownership boundaries for agents.

## Backend

- Routers live in `backend/routers/` or matching `backend/domains/*/routers/`.
- Schemas live in `backend/schemas/`.
- Services live in `backend/services/`.
- New async runtime code uses `AsyncSession` and `get_async_db()`.

## Database

- ORM source of truth is `modules/core/db/schema.py`.
- Do not create another SQLAlchemy declarative base.
- Migrations live in `migrations/`.
- SQL assets live in `sql/`.

## Frontend

- API wrappers live in `frontend/src/api/`.
- Stores live in `frontend/src/stores/`.
- Routes live in `frontend/src/router/`.
- Domain UI should stay in `frontend/src/domains/` or the existing feature folder.

## Collection

- Active authoring uses `pwcli + playwright skill + agent`.
- Shared component primitives live in `modules/components/`.
- Platform-specific canonical components live in `modules/platforms/<platform>/components/`.
- Root-level `collectors/` is not the default destination for new canonical components.

## Dashboard

- Dashboard runtime is PostgreSQL-first.
- Data flow is `b_class raw -> semantic -> mart -> api -> backend router -> frontend`.
- Metabase is historical-only for active runtime decisions.
- Semantic field unification must follow the architecture rule: same-platform, same-domain, same-file coexisting fields split by default; only cross-platform business-equivalent fields merge into canonical semantic fields.
