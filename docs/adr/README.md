# Architecture Decision Records

Architecture Decision Records document accepted architecture decisions that agents and humans should preserve.

## When To Add An ADR

- The decision changes long-term architecture direction.
- The decision retires or replaces an existing workflow.
- The decision affects deployment, data ownership, environment boundaries, or agent workflow.
- The decision would otherwise be rediscovered repeatedly by future agents.

## Accepted Decisions

- `AGENTS.md` is the single active repository rule entrypoint.
- Codex is the primary development agent and Claude is supplemental.
- Cursor rule files are retired from the active workflow.
- Dashboard runtime is PostgreSQL-first.
- Production deployment truth is the release tag.
- New collection component authoring uses `pwcli + playwright skill + agent`.
- Template drift classification has a single decision entry point (`data_sync_status_semantics.classify_drift`); a template publish is a closed-loop action that re-checks affected files. See [ADR-2026-11-13](2026-11-13-template-drift-classification-ssot.md).
- A template dimension may host several file formats: `format_signature` is the single business-form signature shared by templates and variants; publish scope follows the save intent (update replaces, create coexists). Ingest refreshes are batched by the refresh queue. See [ADR-2026-11-13 (multi-format & batch refresh)](2026-11-13-template-multi-format-and-batch-refresh.md).

## Agent Rules

- Keep ADRs concise and decision-focused.
- Do not use ADRs as implementation runbooks.
- Link implementation details to guides or architecture references instead.
