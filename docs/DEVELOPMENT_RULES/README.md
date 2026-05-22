# Development Rules Reference

This directory is a detailed reference for repository-specific implementation standards.

## Current Rule Model

- Active rule entrypoint: [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md)
- Active workflow: `superpowers` + `planning-with-files`
- Supplemental helper skills such as `gstack` are allowed only as explicit add-ons, not as the repository default workflow
- Claude-specific notes, if needed, live in [`CLAUDE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/CLAUDE.md)
- Cursor rule files are not part of the active workflow
- Historical archive: [`openspec/`](F:/Vscode/python_programme/AI_code/xihong_erp/openspec)

## Dashboard Data Architecture

- The active dashboard architecture direction is PostgreSQL-first rather than Metabase-first.
- Preferred dashboard flow is `b_class raw -> semantic -> mart -> api -> backend -> frontend`.
- `semantic` is the standardization layer, `mart` is the aggregate layer, and `api` is the module-facing query layer.

Use this directory for deep-dive references and templates. Do not treat it as the default workflow engine.

## Governance References

- Active docs index: [`docs/ACTIVE_DOCS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/ACTIVE_DOCS.md)
- Environment boundaries: [`docs/guides/ENVIRONMENT_MODEL.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/ENVIRONMENT_MODEL.md)
- Development environment: [`docs/guides/DEVELOPMENT_ENVIRONMENT.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/DEVELOPMENT_ENVIRONMENT.md)
- Agent task contract: [`docs/guides/AGENT_TASK_CONTRACT.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/AGENT_TASK_CONTRACT.md)
- Change control: [`docs/guides/CHANGE_CONTROL.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/CHANGE_CONTROL.md)
- Verification matrix: [`docs/guides/VERIFICATION_MATRIX.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/VERIFICATION_MATRIX.md)
- Document lifecycle: [`docs/guides/DOCUMENT_LIFECYCLE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/DOCUMENT_LIFECYCLE.md)
- PWCLI command reference: [`docs/guides/PWCLI_COMMAND_REFERENCE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/PWCLI_COMMAND_REFERENCE.md)
- Project structure: [`docs/architecture/PROJECT_STRUCTURE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/architecture/PROJECT_STRUCTURE.md)
- Architecture boundaries: [`docs/architecture/BOUNDARIES.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/architecture/BOUNDARIES.md)
- Architecture decisions: [`docs/adr/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/adr/README.md)

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
| `DASHBOARD_ASSETS_AND_MIGRATIONS.md` | Rules for Alembic vs bootstrap vs init_db and SQL asset hygiene |

## Current Status

- Current engineering state summary: [`docs/guides/ENGINEERING_STATUS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/ENGINEERING_STATUS.md)
- Current cloud sync operation notes: [`docs/deployment/CLOUD_SYNC_OPERATION_NOTES.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/deployment/CLOUD_SYNC_OPERATION_NOTES.md)

## Notes

- When detailed docs conflict with active skills, prefer skills unless the difference is a repository-specific constraint recorded in `AGENTS.md`.
- When `superpowers` and `gstack` overlap, treat `superpowers` as the default and use `gstack-*` only when explicitly requested or clearly acting as a bounded helper.
- When detailed docs conflict with `AGENTS.md`, update the docs so the repository constraint and the reference stay aligned.
- GitHub release operations in this repository are tag-driven; `origin/main` is not the deployment source of truth.
