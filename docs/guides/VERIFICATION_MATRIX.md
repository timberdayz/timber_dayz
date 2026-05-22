# Verification Matrix

This file maps changed surfaces to repository-specific checks. The active verification workflow remains `superpowers`.

## Rule And Documentation Changes

- Run `python scripts/verify_rules_completeness.py`.
- Run `python scripts/verify_root_md_whitelist.py` when root Markdown or documentation policy changes.
- Run `python -m py_compile scripts/verify_rules_completeness.py scripts/verify_root_md_whitelist.py scripts/verify_architecture_ssot.py` when verification scripts change.
- Run `powershell -ExecutionPolicy Bypass -File .\scripts\verify_pwcli_helpers.ps1` when `pwcli` helper rules or wrappers change.

## Architecture Changes

- Run `python scripts/verify_architecture_ssot.py` for ORM, schema, or architecture-boundary changes.
- Inspect `docs/architecture/PROJECT_STRUCTURE.md` and `docs/architecture/BOUNDARIES.md` for placement rules.

## Backend Changes

- Prefer targeted backend tests under `backend/tests/`.
- Check async database usage when touching runtime database code.
- Verify typed endpoints use schemas from `backend/schemas/`.

## Frontend Changes

- Prefer targeted frontend checks for the affected module.
- Verify API access stays under `frontend/src/api/`.

## Collection Changes

- Use `pwcli` evidence for page behavior changes.
- Use `docs/guides/COLLECTION_AUTHORING_RULES.md` as the clean active collection authoring entrypoint.
- Verify canonical components under `modules/platforms/<platform>/components/`.
- Preserve Markdown snapshots and notes when evidence is needed for agent handoff.

## Agent Rules

- Start with the narrowest check that proves the changed behavior.
- Do not claim completion without fresh verification output.
