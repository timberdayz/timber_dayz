# Active Documentation Index

This index lists the current documentation entrypoints agents should prefer.

Do not use full-repository search as the first step when one of these files covers the task.

## Rule And Agent Context

- `AGENTS.md`: single active repository rule entrypoint
- `CLAUDE.md`: Claude supplemental adapter
- `docs/guides/AGENT_TASK_CONTRACT.md`: repository task framing for active skill workflows
- `docs/guides/ENVIRONMENT_MODEL.md`: local, Docker, production, and collection environment boundaries
- `docs/guides/DEVELOPMENT_ENVIRONMENT.md`: local machine, runtime, and application setup baseline
- `docs/guides/ENV_FILE_CONTRACT.md`: `.env*` and `env*.example` ownership, edit, and secrecy rules
- `docs/guides/CHANGE_CONTROL.md`: phase-specific scope constraints
- `docs/guides/VERIFICATION_MATRIX.md`: verification checks by changed surface
- `docs/guides/DOCUMENT_LIFECYCLE.md`: active, reference, runbook, and archive document policy
- `docs/guides/PERMISSION_MODEL.md`: active frontend/backend permission model and maintenance rules

## Development And Release

- `docs/guides/DEVELOPMENT_WORKFLOW.md`: startup, validation, testing, and release commands
- `docs/guides/LOCAL_DASHBOARD_ASSET_RECOVERY.md`: local dashboard asset recovery and rebuild decision path
- `docs/guides/COLLECTION_AUTHORING_RULES.md`: clean active collection authoring rules
- `docs/guides/PWCLI_COMMAND_REFERENCE.md`: `pwcli`, `pwcap`, and evidence helper command reference
- `docs/guides/PRE_LAUNCH_RULES.md`: launch-period change constraints
- `docs/guides/RELEASE_CHECKLIST.md`: tag-driven production release checklist
- `docs/guides/ENGINEERING_STATUS.md`: current engineering status and CI model
- `docs/guides/BUSINESS_OVERVIEW_METRIC_LINEAGE.md`: Business Overview key-metric lineage and verification path

## Architecture

- `docs/architecture/README.md`: architecture overview
- `docs/architecture/PROJECT_STRUCTURE.md`: repository file tree, ownership, and placement boundaries
- `docs/architecture/BOUNDARIES.md`: module and domain boundaries
- `docs/architecture/DASHBOARD.md`: PostgreSQL-first Dashboard architecture
- `docs/architecture/SAFE_CHANGE_ZONES.md`: safe vs high-risk change zones across raw/semantic/mart/api/frontend layers
- `docs/adr/README.md`: architecture decision record policy

## Implementation Standards

- `docs/DEVELOPMENT_RULES/README.md`: implementation standards index
- `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`: backend patterns
- `docs/DEVELOPMENT_RULES/API_AND_CONTRACTS.md`: API and contract standards
- `docs/DEVELOPMENT_RULES/DATABASE.md`: database and SQL standards
- `docs/DEVELOPMENT_RULES/FRONTEND_CODE_PATTERNS.md`: frontend patterns
- `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md`: testing and quality standards
- `docs/DEVELOPMENT_RULES/SECURITY_AND_DEPLOYMENT.md`: security and deployment guidance

## Collection

- `docs/guides/COLLECTION_AUTHORING_RULES.md`: active collection authoring workflow
- `docs/guides/COLLECTION_RUNTIME_RESTORE_RULES.md`: runtime session restore and page-ready rules for formal collection
- `docs/guides/PWCLI_COMMAND_REFERENCE.md`: active `pwcli` command reference
- `docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md`: manual shop inspection and account-session maintenance guide
- `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`: generated copy-paste account command list for manual inspection
- `docs/guides/PWCLI_AGENT_DEBUGGING_SOP.md`: collection debugging workflow
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`: canonical collection component reference
- `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`: active component inventory

## Superpowers Artifacts

- `docs/superpowers/README.md`: superpowers artifact locations
- `docs/superpowers/specs/`: approved design specs
- `docs/superpowers/plans/`: implementation plans
- `docs/superpowers/reports/`: acceptance and review reports

## Historical Material

- `docs/archive/`: archived reports, old rule references, and historical cleanup material
- `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`: legacy long-form collection reference with encoding damage
- `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`: legacy long-form environment reference with encoding damage
- `openspec/`: historical archive only

Historical material is useful for traceability, not as the current rule source.
