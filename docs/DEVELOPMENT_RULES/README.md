# Development Rules - L3 Detailed Reference

This directory contains the L3 detailed reference documents for the XiHong ERP project.

> **Rule hierarchy**: L1 (`CLAUDE.md`) -> L2 (`.cursorrules`) -> L3 (this directory)
>
> `.cursorrules` is the authoritative source for zero-tolerance rules.
> This directory provides deep-dive references and code templates.

## Core Thematic Files (7)

| File | Description |
|------|-------------|
| [CODE_PATTERNS.md](CODE_PATTERNS.md) | Code templates: AsyncCRUDService, Router, Schema, conftest, transaction, cache, optimistic lock, DI |
| [API_AND_CONTRACTS.md](API_AND_CONTRACTS.md) | API design standards, code review process, review checklist, HTTP status code migration strategy |
| [DATABASE.md](DATABASE.md) | Database design, migration (Alembic), SQL writing standards, design checklist, examples |
| [TESTING_AND_QUALITY.md](TESTING_AND_QUALITY.md) | Test pyramid, coverage targets, code quality, static analysis |
| [ERROR_AND_LOGGING.md](ERROR_AND_LOGGING.md) | Error handling patterns, logging standards (error codes SSOT: `backend/utils/error_codes.py`) |
| [SECURITY_AND_DEPLOYMENT.md](SECURITY_AND_DEPLOYMENT.md) | Security (JWT/RBAC), deployment (CI/CD), monitoring and observability |
| [UI_DESIGN.md](UI_DESIGN.md) | UI design patterns, partial loading, background refresh, async UX |

## Extension Files (Production Governance — added by `add-production-readiness-and-operational-governance`)

| File | Description |
|------|-------------|
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Performance SLOs, capacity baselines, load test gate, release/rollback governance, RPO/RTO, ERP acceptance standards |
| [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md) | Four-level data classification, restricted data inventory, desensitization rules, audit retention requirements |
| [FRONTEND_CODE_PATTERNS.md](FRONTEND_CODE_PATTERNS.md) | Frontend Agent templates: API layer, Pinia store, list page, form page, permission button, loading patterns |

When adding new extension files, update this index and the `.cursorrules` L3 docs table accordingly.
