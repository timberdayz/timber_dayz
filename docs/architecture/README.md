# Architecture Overview

This directory contains architecture references. The active repository rule entrypoint is `AGENTS.md`.

## Core Stack

- Backend: FastAPI + SQLAlchemy async + Pydantic + PostgreSQL
- Frontend: Vue 3 + Element Plus + Pinia + Vite
- ORM source of truth: `modules/core/db/schema.py`

## Primary Boundaries

- `backend/`: FastAPI routers, schemas, services, and API-facing application logic
- `modules/core/`: shared core database and domain primitives
- `modules/components/`: shared collection component base classes and reusable primitives
- `modules/platforms/`: platform adapters and platform-specific canonical components
- `modules/services/`: shared service layer used by backend and collection runtime code
- `frontend/`: Vue application, stores, API wrappers, and UI modules
- `collectors/`: legacy or narrow collector entrypoints, not the default destination for new canonical components
- `sql/`: PostgreSQL semantic, mart, and API-layer assets
- `docs/DEVELOPMENT_RULES/`: detailed implementation standards

## Detailed References

- Project structure: `docs/architecture/PROJECT_STRUCTURE.md`
- Domain and module boundaries: `docs/architecture/BOUNDARIES.md`
- Dashboard architecture: `docs/architecture/DASHBOARD.md`
- Data sync contract: `docs/architecture/DATA_SYNC_CONTRACT.md`
- Semantic field rules: `docs/architecture/SEMANTIC_FIELD_RULES.md`
- Field alias migration prep: `docs/architecture/FIELD_ALIAS_RULES_MIGRATION_PREP.md`
- Backend patterns: `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`
- API and contracts: `docs/DEVELOPMENT_RULES/API_AND_CONTRACTS.md`
- Database rules: `docs/DEVELOPMENT_RULES/DATABASE.md`
- Frontend patterns: `docs/DEVELOPMENT_RULES/FRONTEND_CODE_PATTERNS.md`
- Testing and quality: `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md`
