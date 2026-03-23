# Development Rules Reference

This directory is a detailed reference for repository-specific implementation standards.

## Current Rule Model

- Active workflow: `superpowers` + `planning-with-files`
- Repository constraints: [`.cursorrules`](F:/Vscode/python_programme/AI_code/xihong_erp/.cursorrules)
- Entry docs: [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md) and [`CLAUDE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/CLAUDE.md)
- Historical archive: [`openspec/`](F:/Vscode/python_programme/AI_code/xihong_erp/openspec)

## Dashboard Data Architecture

- The active dashboard architecture direction is PostgreSQL-first rather than Metabase-first.
- Preferred dashboard flow is `b_class raw -> semantic -> mart -> api -> backend -> frontend`.
- `semantic` is the standardization layer, `mart` is the aggregate layer, and `api` is the module-facing query layer.

Use this directory for deep-dive references and templates. Do not treat it as the default workflow engine.

## Core Files

| File | Purpose |
|---|---|
| `CODE_PATTERNS.md` | Backend service, router, schema, transaction, and DI patterns |
| `API_AND_CONTRACTS.md` | API design and review standards |
| `DATABASE.md` | Database design, migration, and SQL standards |
| `TESTING_AND_QUALITY.md` | Testing strategy, coverage, and code-quality standards |
| `ERROR_AND_LOGGING.md` | Error-handling and logging standards |
| `SECURITY_AND_DEPLOYMENT.md` | Security, deployment, and observability guidance |
| `UI_DESIGN.md` | Frontend interaction and loading patterns |
| `PRODUCTION_READINESS.md` | SLOs, release governance, rollback, and recovery |
| `DATA_GOVERNANCE.md` | Data classification and sensitive-data handling |
| `FRONTEND_CODE_PATTERNS.md` | Vue 3 + Element Plus frontend patterns |

## Current Status

- Current engineering state summary: [`docs/guides/ENGINEERING_STATUS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/ENGINEERING_STATUS.md)

## Notes

- When detailed docs conflict with active skills, prefer skills unless the difference is a repository-specific constraint recorded in `.cursorrules`.
- When detailed docs conflict with `.cursorrules`, update the docs so the repository constraint and the reference stay aligned.
- GitHub release operations in this repository are tag-driven; `origin/main` is not the deployment source of truth.
