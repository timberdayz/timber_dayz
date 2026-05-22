# Architecture Index

This document is a navigational map for the current codebase architecture and the most important entry points.

## Rule-Facing Architecture Entry Points

- `docs/architecture/PROJECT_STRUCTURE.md` (file tree, ownership, and placement boundaries)
- `docs/architecture/BOUNDARIES.md` (module and domain ownership boundaries)
- `docs/architecture/DASHBOARD.md` (PostgreSQL-first Dashboard architecture)

## Backend (FastAPI)

Runtime entry points:
- `backend/app/main.py` (primary app creation + runtime mode selection)
- `backend/main.py` (compatibility import path)
- `run.py` (runtime-mode handoff and start commands)

Runtime composition:
- `backend/app/bootstrap/` (thin composition wrappers)
- `backend/domains/*/routes.py` (domain-owned route registration surfaces)

Domain layout:
- `backend/domains/collection/`
- `backend/domains/data_platform/`
- `backend/domains/business/`
- `backend/domains/platform/`

Legacy compatibility layer:
- `backend/routers/` (kept for external imports/tests; avoid adding new runtime dependencies)

Guards/tests:
- `backend/tests/test_domain_route_registration.py`
- `backend/tests/test_runtime_mode_route_registration.py`
- `backend/tests/test_domain_legacy_router_boundary.py`

## ORM SSOT (SQLAlchemy)

Public import surface (SSOT):
- `modules/core/db/schema.py`

Internal slices (implementation detail; do not import `schema.py` from parts):
- `modules/core/db/schema_parts/`

Contract/guard test:
- `backend/tests/test_schema_ssot_import_contract.py`

## Collection Components

Shared component primitives:
- `modules/components/`

Platform-specific canonical components:
- `modules/platforms/miaoshou/components/`
- `modules/platforms/shopee/components/`
- `modules/platforms/tiktok/components/`
- `modules/platforms/amazon/components/`

Platform adapters:
- `modules/platforms/*/adapter.py`

Legacy or narrow collector entrypoints:
- `collectors/`

## Frontend (Vue 3)

Router:
- `frontend/src/router/index.js`

Domain-owned UI:
- `frontend/src/domains/`

Compatibility (should be kept minimal):
- `frontend/src/views/` (bridge wrappers; route table should prefer direct domain view imports)

Guards/tests:
- `frontend/scripts/domainBridgeInventory.test.mjs`

## Workflow Docs (Superpowers)

Plans and closure state:
- `docs/superpowers/plans/STATUS.md`
- `docs/superpowers/plans/2026-05-05-project-simplification-phase6-closure.md`
- `docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md`
