# Collection Authoring Rules

This is the active, clean entrypoint for collection authoring. It replaces ambiguous or mojibake legacy SOP text as the first document agents should read.

## Active Workflow

- Use `pwcli + playwright skill + agent`.
- Use `pwcli` for page exploration, snapshots, state comparison, screenshots, and locator discovery.
- Use agent-generated canonical Python components as the supported output path.
- Do not use legacy recorder flows for new component authoring unless the user explicitly asks to maintain those paths.

## Output Contract

- Shared component primitives belong in `modules/components/`.
- Platform-specific canonical components belong in `modules/platforms/<platform>/components/`.
- Platform adapters belong in `modules/platforms/<platform>/adapter.py`.
- New collection code must be async-first and compatible with the current component runtime.
- Production collection should run verified stable components, not raw `pwcli` exploration output.

## Evidence Contract

For agent handoff, prefer Markdown and image artifacts:

- Current URL.
- Snapshot before and after key state changes.
- Screenshot for visually ambiguous UI states.
- Step description.
- Expected result.
- Actual result.
- Special conditions such as captcha, iframe, dialog, popup, download, or new tab.

## Authoring Sequence

1. Check whether an existing stable `export` or supporting component can be reused.
2. Use `pwcli` to collect page evidence.
3. Ask the agent to analyze structure before writing code.
4. Generate or patch the smallest canonical Python component.
5. Test against a real page/session or equivalent component test path.
6. Promote only verified components through the existing version lifecycle.

## Anti-Patterns

- Do not turn click recordings directly into production code.
- Do not hardcode account names, passwords, store names, verification codes, or downloaded local paths.
- Do not treat button clicks, toast messages, or dialog closure as business success without stronger signals.
- Do not rewrite an entire platform component when a narrow helper or selector fix is enough.
- Do not place new canonical components in root-level `collectors/`.

## Legacy References

- `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md` is legacy long-form material and currently contains encoding damage. Do not use it as the first rule source.
- `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md` is legacy long-form material and currently contains encoding damage. Use it only for historical detail when the clean active docs are insufficient.
- Use `docs/guides/PWCLI_COMMAND_REFERENCE.md` for command details.
- Use `docs/guides/DEVELOPMENT_ENVIRONMENT.md` for local runtime assumptions.
