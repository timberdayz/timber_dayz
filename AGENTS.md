# Agent Instructions

This file is the single active rule entrypoint for this repository.

## Rule Priority

1. Direct user instructions
2. This file
3. Detailed references under `docs/`
4. Active skills such as `superpowers`, `planning-with-files`, and explicit `gstack-*` helpers
5. Historical material under `archive/`, `docs/archive/`, and `openspec/`

If another document conflicts with this file, follow this file and update the other document when the task includes rule maintenance.

## Current Tool Model

- Primary development agent: Codex
- Supplemental review or consultation agent: Claude
- Cursor is not part of the active workflow
- Do not use `.cursorrules` or `.cursor/rules/*` as active rule sources
- `CLAUDE.md`, if present, is a thin Claude adapter and must not duplicate repository rules

## Default Workflow

- Use `superpowers` as the default workflow for design, debugging, TDD, review, and verification.
- Use `planning-with-files` for complex multi-step work. The root files `task_plan.md`, `findings.md`, and `progress.md` are intentionally allowed and are gitignored.
- Use `gstack` only as a supplemental skillset through explicit `gstack-*` flows or direct user requests.
- Prefer explicit `gstack-*` skill names so generic verbs such as review, plan, QA, or ship stay unambiguous.
- Treat `openspec/` as a historical archive only. Do not route active work through OpenSpec unless the user explicitly asks to inspect archived OpenSpec material.

## Pre-Launch Development Constraints

Until production launch is stable:

- Prioritize launch-blocking work over cleanup.
- Do not perform broad refactors unless they are required to unblock launch.
- Keep each task scoped to a clear business area and validation path.
- Do not add new root-level temporary reports, screenshots, or one-off scripts.
- Record non-blocking technical debt for the post-launch V2 rebuild instead of fixing it opportunistically.

Detailed rules: `docs/guides/PRE_LAUNCH_RULES.md`.

## Superpowers Repository Adapters

`superpowers` remains the workflow engine. These files provide repository-specific context and must not be treated as replacement workflows.

- Use `docs/guides/AGENT_TASK_CONTRACT.md` to clarify scope, non-scope, verification, and handoff context.
- Use `docs/guides/ENVIRONMENT_MODEL.md` before acting across local, Docker, production, or collection environments.
- Use `docs/guides/DEVELOPMENT_ENVIRONMENT.md` for local OS, shell, runtime, Docker, Redis, PostgreSQL, Node, Python, and Playwright assumptions.
- Use `docs/guides/VERIFICATION_MATRIX.md` when the verification skill needs repository-specific commands.
- Use `docs/guides/CHANGE_CONTROL.md` to apply phase-specific scope boundaries.

## Core Stack Constraints

- Backend stack: FastAPI + SQLAlchemy async + Pydantic + PostgreSQL
- Frontend stack: Vue 3 + Element Plus + Pinia + Vite
- ORM SSOT: `modules/core/db/schema.py`
- Pydantic contracts belong in `backend/schemas/`, not in routers
- New backend routes should declare `response_model` when the endpoint returns a typed payload
- New backend runtime code uses `AsyncSession` and `get_async_db()`
- Do not use synchronous ORM patterns such as `db.query()` in new async runtime code
- CRUD-style services should reuse `AsyncCRUDService` from `backend/services/base_service.py`
- Frontend API access goes through `frontend/src/api/`
- Runtime Playwright inside backend code must use `async_playwright`
- Use `datetime.now(timezone.utc)`, not `datetime.utcnow()`
- Windows terminal and log output must avoid emoji

## Dashboard Architecture

- The active Dashboard direction is PostgreSQL-first.
- Dashboard data flow is `b_class raw -> semantic -> mart -> api -> backend router -> frontend`.
- `semantic` is the standardization layer, `mart` is the reusable aggregate layer, and `api` is the page-module query layer.
- Metabase is historical-only and is not part of the active runtime or deployment path.
- New production Dashboard work must not add dependencies on Metabase when equivalent PostgreSQL assets exist.

Detailed rules: `docs/architecture/DASHBOARD.md`.

## Collection Authoring Workflow

- The active collection component authoring workflow is `pwcli + playwright skill + agent`.
- Use `pwcli` for page exploration, snapshots, state comparison, and locator discovery.
- Use agent-generated canonical Python components as the supported output path for new collection work.
- Do not default to legacy recorder scripts, backend `/recorder` APIs, or frontend recorder pages for new component authoring unless the user explicitly asks to maintain legacy recorder paths.
- Primary workflow reference: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`.
- Command reference: `docs/guides/PWCLI_COMMAND_REFERENCE.md`.
- Collection runtime baseline: `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`.
- Collection failure debugging: `docs/guides/PWCLI_AGENT_DEBUGGING_SOP.md`.

## Release Model

- GitHub deployment is tag-driven, not `origin/main` driven.
- Release tags such as `vX.Y.Z` are the deployment source of truth.
- Local `main` currently tracks `cnb/main`; `origin/main` is the GitHub remote-tracking branch.
- `origin/main` may lag behind the deployed tag and that alone is not an error.

Detailed workflow: `docs/guides/RELEASE_CHECKLIST.md`.

## Documentation Map

- `docs/ACTIVE_DOCS.md`: current documentation entrypoints agents should prefer
- `docs/guides/AGENT_TASK_CONTRACT.md`: repository task framing for active skill workflows
- `docs/guides/ENVIRONMENT_MODEL.md`: local, Docker, production, and collection environment boundaries
- `docs/guides/DEVELOPMENT_ENVIRONMENT.md`: local machine, runtime, and application setup baseline
- `docs/guides/DEVELOPMENT_WORKFLOW.md`: startup, validation, testing, and release commands
- `docs/guides/PWCLI_COMMAND_REFERENCE.md`: `pwcli`, `pwcap`, and evidence helper command reference
- `docs/guides/PRE_LAUNCH_RULES.md`: launch-period change constraints
- `docs/guides/CHANGE_CONTROL.md`: phase-specific change-scope rules
- `docs/guides/VERIFICATION_MATRIX.md`: repository checks by changed surface
- `docs/guides/DOCUMENT_LIFECYCLE.md`: active, reference, runbook, and archive document policy
- `docs/architecture/README.md`: architecture overview
- `docs/architecture/PROJECT_STRUCTURE.md`: repository file tree, ownership, and placement boundaries
- `docs/architecture/BOUNDARIES.md`: module and domain boundaries
- `docs/architecture/DASHBOARD.md`: Dashboard data flow and runtime direction
- `docs/adr/README.md`: architecture decision record policy and accepted decisions
- `docs/DEVELOPMENT_RULES/README.md`: detailed implementation standards index
- `docs/superpowers/README.md`: skill-first spec and plan locations

Answer users in Chinese unless they explicitly ask for another language.
