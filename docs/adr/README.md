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

## Agent Rules

- Keep ADRs concise and decision-focused.
- Do not use ADRs as implementation runbooks.
- Link implementation details to guides or architecture references instead.
