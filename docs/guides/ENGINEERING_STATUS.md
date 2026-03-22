# Engineering Status

## Current State

- Repository workflow is `skill-first`
- Active flow is `superpowers` + `planning-with-files`
- `openspec/` is historical archive only
- `main`, `origin/main`, and `cnb/main` are currently aligned when release work is complete

## Active Source Of Truth

- Rule entrypoints:
  - [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md)
  - [`CLAUDE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/CLAUDE.md)
  - [`\.cursorrules`](F:/Vscode/python_programme/AI_code/xihong_erp/.cursorrules)
- Detailed reference:
  - [`docs/DEVELOPMENT_RULES/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/DEVELOPMENT_RULES/README.md)

## CI Model

- Default GitHub `CI Pipeline` is change-scoped, not full-repository regression
- Python test job is aligned to `3.11`
- `black`, `ruff`, `bandit`, and secret scan only inspect changed Python files
- `pytest` only runs changed test files in default CI
- Integration-style validations that depend on full external environments should not be folded back into the default CI gate

Key files:
- [`ci.yml`](F:/Vscode/python_programme/AI_code/xihong_erp/.github/workflows/ci.yml)
- [`ci_changed_python_files.py`](F:/Vscode/python_programme/AI_code/xihong_erp/scripts/ci_changed_python_files.py)
- [`pyproject.toml`](F:/Vscode/python_programme/AI_code/xihong_erp/pyproject.toml)

## Release Model

- GitHub deployment remains tag-driven
- Production source of truth is release tags such as `vX.Y.Z`
- `origin/main` is not deployment truth by itself
- Release checklist lives in [`RELEASE_CHECKLIST.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/RELEASE_CHECKLIST.md)

## Deployment Status

- Production deploy flow is healthy
- SSH host key pinning is enabled
- `StrictHostKeyChecking=no` is no longer part of the active deploy flow
- Production compose is expected to read `${DATABASE_URL}` instead of hardcoded database credentials

## Current Non-Blocking Warnings

- Docker build workflows may still show Node 20 deprecation warnings from upstream Docker-maintained GitHub Actions
- Those warnings are currently upstream-action warnings, not repository logic failures

## Practical Guidance

1. Do not revert default CI back to full-repository lint/test scanning
2. Keep release operations tag-driven
3. Keep repository-specific constraints in `.cursorrules`, not ad hoc workflow comments
4. When a future session investigates CI failures, inspect the latest GitHub Actions run first before changing rules
