# Agent Task Contract

This file is a repository adapter for `superpowers`. It helps agents frame tasks before changing code or rules.

## Recommended Task Fields

- Goal: the business or engineering outcome.
- Scope: files, modules, or user flows expected to change.
- Non-scope: adjacent areas that must not be changed opportunistically.
- Environment: local, Docker, production, or collection runtime.
- Contracts: API, database, frontend, collection, or documentation boundaries involved.
- Verification: commands or manual checks that prove the change.
- Handoff: remaining risks, skipped checks, and next recommended action.

## Agent Rules

- Keep work scoped to the requested outcome.
- Prefer small, reviewable changes during the pre-launch period.
- Use repository-specific references from `AGENTS.md` and `docs/ACTIVE_DOCS.md`.
- Record non-blocking technical debt instead of fixing it opportunistically.
