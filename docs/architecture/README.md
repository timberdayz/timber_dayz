# Architecture Overview

This directory contains architecture references. The active repository rule entrypoint is `AGENTS.md`.

## Core Stack

- Backend: FastAPI + SQLAlchemy async + Pydantic + PostgreSQL
- Frontend: Vue 3 + Element Plus + Pinia + Vite
- ORM source of truth: `modules/core/db/schema.py`

## Primary Boundaries

- `backend/`: FastAPI routers, schemas, services, and API-facing application logic
- `modules/core/`: shared core database and domain primitives
- `frontend/`: Vue application, stores, API wrappers, and UI modules
- `collectors/`: collection-specific runtime and component logic
- `sql/`: PostgreSQL semantic, mart, and API-layer assets
- `docs/DEVELOPMENT_RULES/`: detailed implementation standards

## Detailed References

- Dashboard architecture: `docs/architecture/DASHBOARD.md`
- Backend patterns: `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`
- API and contracts: `docs/DEVELOPMENT_RULES/API_AND_CONTRACTS.md`
- Database rules: `docs/DEVELOPMENT_RULES/DATABASE.md`
- Frontend patterns: `docs/DEVELOPMENT_RULES/FRONTEND_CODE_PATTERNS.md`
- Testing and quality: `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md`
