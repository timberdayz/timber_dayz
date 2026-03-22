# Metabase To PostgreSQL Cleanup Plan

**Date:** 2026-03-22

## Goal

Align the repository with the new direction:

- PostgreSQL becomes the primary online query path
- Metabase is removed from the main runtime/deployment path
- repository rules and active documentation no longer instruct engineers to build against Metabase-first assumptions

This plan is a cleanup/governance companion to:
- [2026-03-21-postgresql-api-semantic-mart-cutover.md](F:/Vscode/python_programme/AI_code/xihong_erp/docs/superpowers/plans/2026-03-21-postgresql-api-semantic-mart-cutover.md)

That earlier plan focuses on the new PostgreSQL semantic/api implementation.
This plan focuses on retiring the old Metabase-first guidance and runtime coupling.

## Current Assessment

The repository currently contains three overlapping architectural stories:

1. **Current desired direction**
   - FastAPI + SQLAlchemy async + PostgreSQL
   - new semantic / mart / api cutover plan exists

2. **Current runtime reality**
   - dashboard and part of HR/performance logic still call `MetabaseQuestionService`
   - startup and deployment flows still include Metabase

3. **Historical residue**
   - older Superset and materialized-view documents still exist in active doc paths
   - some docs say "Metabase replaces materialized views"
   - newer migration direction says "PostgreSQL semantic/api replaces Metabase"

This mismatch is now a governance problem, not just a documentation problem.

## Priority Model

### P0: Runtime And Deployment Truth

These files actively influence execution, startup, or production deployment.
They must be updated first.

### P1: Rule And Onboarding Truth

These files actively shape developer behavior and architectural decisions.
They must be updated immediately after P0, or in the same batch if easy.

### P2: Active Reference Docs

These are still likely to be read during development/deployment.
They should be rewritten or explicitly marked as historical.

### P3: Historical Docs And Scripts

These should be archived, renamed, or de-indexed from active workflows.
They are lower risk but create ongoing confusion if left in active paths.

## P0: Files That Must Change First

### Runtime entrypoints

- `backend/main.py`
- `run.py`

Current issue:
- still includes `metabase_proxy`
- still treats dashboard path as Metabase-backed
- still exposes `--with-metabase` startup path
- still documents Metabase as a normal runtime dependency

Required adjustment:
- remove Metabase from default startup/main-path wording
- gate or remove Metabase router registration from the primary runtime path
- replace startup copy/help text with PostgreSQL semantic/api wording

### Main dashboard / BI path

- `backend/routers/dashboard_api.py`
- `backend/services/metabase_question_service.py`
- `backend/routers/metabase_proxy.py`

Current issue:
- dashboard API still uses Metabase Question as the primary online data source

Required adjustment:
- cut over dashboard endpoints to PostgreSQL semantic/api sources
- keep Metabase code only behind explicit fallback or remove it entirely
- once cutover is complete, delete `metabase_proxy` main-path exposure

### Secondary runtime consumers

- `backend/routers/hr_commission.py`
- `backend/routers/performance_management.py`
- `backend/services/hr_income_calculation_service.py`
- `backend/services/cache_warmup_service.py`

Current issue:
- these still call `MetabaseQuestionService`

Required adjustment:
- port to PostgreSQL semantic/api module sources
- remove Metabase-dependent cache warmup behavior

### Deployment and environment

- `.github/workflows/deploy-production.yml`
- `docker-compose.metabase.yml`
- `docker-compose.metabase.dev.yml`
- `docker-compose.metabase.4c8g.yml`
- `docker-compose.metabase.lockdown.yml`
- `config/metabase_config.yaml`
- `scripts/init_metabase.py`
- `.env.cleaned`

Current issue:
- production pipeline still uploads/boots Metabase artifacts
- environment reference still exposes Metabase vars as active

Required adjustment:
- remove Metabase as a required production phase
- remove Phase 3.5 `init_metabase.py` coupling
- replace Metabase env variables with PostgreSQL semantic/api feature flags if needed

## P1: Rule And Onboarding Files To Update

### Highest priority onboarding files

- `CLAUDE.md`
- `README.md`
- `docs/AGENT_START_HERE.md`

Current issue:
- `CLAUDE.md` still shows `--with-metabase`
- `README.md` still contains old Superset + materialized-view + Metabase layers mixed together
- `docs/AGENT_START_HERE.md` is actively dangerous because it still instructs people to:
  - avoid business SQL
  - add Metabase Questions for new queries
  - use Metabase as the primary BI/query layer

Required adjustment:
- rewrite these files so PostgreSQL semantic/api is the main path
- explicitly mark Metabase/Superset material as historical or optional internal BI only

### Rule files that are already mostly clean

- `AGENTS.md`
- `.cursorrules`
- `.cursor/rules/skill-integration.mdc`
- `docs/DEVELOPMENT_RULES/README.md`
- `docs/guides/ENGINEERING_STATUS.md`

Current issue:
- these are largely fine already
- only minor follow-up wording may be needed after runtime cutover lands

Required adjustment:
- keep aligned after the runtime cutover
- do not make these the first cleanup target

## P2: Active Docs That Still Need Rewrite

### Deployment docs

- `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`
- `docs/deployment/CLOUD_METABASE_ACCESS.md`
- `docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md`
- `docs/deployment/LOCAL_COLLECTION_DEV.md`
- `docs/deployment/LOCAL_AND_CLOUD_DEPLOYMENT_ROLES.md`
- `docs/CI_CD_DEPLOYMENT_GUIDE.md`

Current issue:
- these still describe Metabase startup, Metabase health checks, `init_metabase.py`, and Metabase-backed verification as active deployment steps

Required adjustment:
- replace them with PostgreSQL semantic/api deployment and verification instructions
- if some are no longer relevant, archive them

### Data contract / source-of-truth docs

- `docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md`
- `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`

Current issue:
- these currently treat `sql/metabase_models/*` and Metabase Question outputs as the authority

Required adjustment:
- redefine authority as PostgreSQL `semantic.*` / `mart.*` / `api.*`
- update examples and ownership rules

### User-facing docs

- `docs/guides/QUICK_START_ALL_FEATURES.md`
- `docs/系统使用说明书.md`

Current issue:
- they still present Metabase as a visible product path

Required adjustment:
- update to PostgreSQL-backed dashboard/report wording

## P3: Historical Or Transitional Content To Archive Or Mark

### Metabase-specific docs

All of these should be archived or explicitly marked as historical after cutover:

- `docs/METABASE_API_INTEGRATION_GUIDE.md`
- `docs/METABASE_DASHBOARD_SETUP.md`
- `docs/METABASE_*`
- `docs/DATA_BROWSER_AND_METABASE_TROUBLESHOOTING.md`

### Superset residue

Still present in active docs:

- old Superset startup references in `README.md`
- old Superset docs under `docs/`
- old Superset cleanup scripts and summaries

Required adjustment:
- move to archive or explicitly label as historical only

### Materialized-view residue in active docs

Examples:

- `docs/API_TESTING_GUIDE.md`
- `docs/API_ENDPOINTS_INVENTORY.md`
- `docs/C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md`
- `docs/SEMANTIC_LAYER_DESIGN.md`
- many old database design and migration summaries

Current issue:
- many still describe MV-driven design as active

Required adjustment:
- for still-relevant docs: rewrite around PostgreSQL semantic/mart/api
- for obsolete docs: archive

## Execution Order

### Batch 1: Stop active misdirection

Target:
- `CLAUDE.md`
- `README.md`
- `docs/AGENT_START_HERE.md`
- `run.py`

Why first:
- these are the files most likely to mislead engineers immediately

### Batch 2: Remove runtime dependence

Target:
- `backend/main.py`
- `backend/routers/dashboard_api.py`
- `backend/routers/metabase_proxy.py`
- `backend/services/metabase_question_service.py`
- secondary router/service consumers

Why second:
- this is the actual production-path cutover

### Batch 3: Remove deployment dependence

Target:
- workflow files
- compose files
- env references
- `config/metabase_config.yaml`
- `scripts/init_metabase.py`

Why third:
- once runtime no longer needs Metabase, deployment should stop provisioning it

### Batch 4: Rewrite active docs

Target:
- deployment docs
- data-contract docs
- user-facing docs

### Batch 5: Archive historical residue

Target:
- Metabase/Superset/MV historical docs and helper scripts

## Keep / Remove Guidance

### Keep

- PostgreSQL as the only primary online query engine
- `b_class` JSONB raw layer
- semantic/mart/api PostgreSQL layering plan
- cloud canonical sync work

### Remove From Main Path

- `MetabaseQuestionService` as runtime dependency
- `/api/metabase` as active main-path API
- Metabase startup and deployment phases
- documentation instructing developers to create Questions for new product queries

### Optional Historical Retention

If the team still wants Metabase for ad hoc internal BI:
- keep it explicitly labeled as optional internal BI
- remove all wording that treats it as production source of truth

## Recommended Next Step

Start with **Batch 1** and **Batch 2** together, because they are the minimum set required to stop future work from drifting back into the old Metabase-first model.

After that:
- Batch 3 removes deployment burden
- Batch 4 and Batch 5 clean up the remaining confusion
