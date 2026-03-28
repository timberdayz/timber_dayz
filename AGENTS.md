# Agent Instructions

This repository uses a skill-first workflow.

## Current Workflow

- Use `superpowers` as the default development workflow for design, debugging, TDD, review, and verification.
- Use `planning-with-files` for complex multi-step work. The root files `task_plan.md`, `findings.md`, and `progress.md` are intentionally allowed and are gitignored.
- Treat `.cursorrules` as a repository-specific constraint file, not as a replacement for skills.
- Treat `openspec/` as a historical archive only. Do not use OpenSpec as the active workflow unless the user explicitly asks to inspect archived OpenSpec material.

## Collection Authoring Workflow

- The active collection component authoring workflow is `pwcli + playwright skill + agent`.
- Use `pwcli` for page exploration, snapshots, state comparison, and locator discovery.
- Use agent-generated canonical Python components as the only supported output path for new collection work.
- Do not default to `tools/record_component.py`, `tools/launch_inspector_recorder.py`, backend `/recorder` flows, or frontend recorder flows for new component authoring unless the user explicitly asks to inspect or maintain the legacy recorder path.
- Treat legacy recorder scripts, `/recorder` APIs, and recorder-oriented docs as historical or maintenance-only unless explicitly requested.
- Primary workflow reference for collection authoring is `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`.

## Rule Sources

1. User instructions
2. Repository-specific constraints in `.cursorrules`
3. Active skills such as `superpowers` and `planning-with-files`
4. Other downloaded skills
5. Reference docs in `docs/DEVELOPMENT_RULES/`
6. Archived material in `openspec/`

## Key Repository Constraints

- Backend stack: FastAPI + SQLAlchemy async + Pydantic
- Frontend stack: Vue 3 + Element Plus + Pinia + Vite
- ORM SSOT: `modules/core/db/schema.py`
- Runtime Playwright inside backend code must stay async-first
- Windows terminal/log output must avoid emoji

## Dashboard Architecture

- The active Dashboard cutover direction is PostgreSQL-first, replacing Metabase on the online query path.
- Dashboard data flow is `b_class raw -> semantic -> mart -> api -> backend router -> frontend`.
- `semantic` is the standardization layer, `mart` is the reusable aggregate layer, and `api` is the page-module query layer.
- Metabase is historical-only and is no longer part of the active runtime or deployment path.
- The runtime switch for the new Dashboard path is `USE_POSTGRESQL_DASHBOARD_ROUTER`.

## Release Model

- The GitHub deployment pipeline is tag-driven, not `origin/main` driven.
- Treat release tags such as `vX.Y.Z` as the deployment source of truth.
- `origin/main` may lag behind the currently deployed tag and that alone is not an error.
- Local `main` currently tracks `cnb/main`; `origin/main` is only the GitHub remote-tracking branch.

Answer users in Chinese unless they explicitly ask for another language.
