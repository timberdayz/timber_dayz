# Agent Instructions

This repository uses a skill-first workflow.

## Current Workflow

- Use `superpowers` as the default development workflow for design, debugging, TDD, review, and verification.
- Use `planning-with-files` for complex multi-step work. The root files `task_plan.md`, `findings.md`, and `progress.md` are intentionally allowed and are gitignored.
- Treat `.cursorrules` as a repository-specific constraint file, not as a replacement for skills.
- Treat `openspec/` as a historical archive only. Do not use OpenSpec as the active workflow unless the user explicitly asks to inspect archived OpenSpec material.

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

Answer users in Chinese unless they explicitly ask for another language.
