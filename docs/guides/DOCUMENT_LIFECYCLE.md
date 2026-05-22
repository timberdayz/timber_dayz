# Document Lifecycle

`AGENTS.md` is the only active rule entrypoint. Other documents provide references, runbooks, architecture details, or historical context.

## Active Documents

- Active entrypoints are listed in `docs/ACTIVE_DOCS.md`.
- Active rule references must be reachable from `AGENTS.md` or `docs/ACTIVE_DOCS.md`.

## Reference Documents

- Architecture references belong in `docs/architecture/`.
- Implementation standards belong in `docs/DEVELOPMENT_RULES/`.
- Runbooks and operating guides belong in `docs/guides/`.
- Architecture decisions belong in `docs/adr/`.

## Reports And Historical Notes

- Reports and historical notes should not become active rules.
- Move old reports to `docs/archive/` or `archive/` when they are no longer current.
- If a retained legacy document contains encoding damage or outdated workflow content, add a status warning at the top and point agents to a clean active entrypoint.
- Treat `openspec/` as historical unless the user explicitly asks to inspect it.

## Agent Rules

- Do not add new root-level Markdown files unless the file is explicitly allowlisted.
- Prefer updating active entrypoints over creating duplicate guidance.
- When a document conflicts with `AGENTS.md`, follow `AGENTS.md` and update the conflicting document if the task includes rule maintenance.
