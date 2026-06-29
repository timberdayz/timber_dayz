# PWCLI Command Reference

This file is the agent-facing command reference for `pwcli`, `pwcap`, and related PowerShell helpers. The active authoring workflow remains `pwcli + playwright skill + agent`.

## Verified Local Helpers

Load the repository-owned helpers before using the user-facing commands in a
new PowerShell window:

```powershell
. .\scripts\pwcli_helpers.ps1
```

The helper script exposes these user-facing commands:

- `pwcli`
- `Open-PwcliMiaoshou`
- `Open-PwcliShopee`
- `Open-PwcliTiktok`
- `Save-PwcliMiaoshouState`
- `Save-PwcliShopeeState`
- `Save-PwcliTiktokState`
- `Show-PwcliPaths`
- `pwsnap`
- `pwnote`
- `pwshot`
- `pwpack`
- `pwcap`

Before suggesting setup steps, first check helper availability:

```powershell
Get-Command pwcli, Open-PwcliMiaoshou, Open-PwcliShopee, Open-PwcliTiktok, Save-PwcliMiaoshouState, Save-PwcliShopeeState, Save-PwcliTiktokState, Show-PwcliPaths, pwsnap, pwnote, pwshot, pwpack, pwcap -ErrorAction SilentlyContinue
```

For a repository-owned self-check, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_pwcli_helpers.ps1
```

If these commands exist, prefer them in user-facing guidance over longer repo-local script paths.

## Primary Commands

- `pwcli`: page exploration, locator discovery, state management, and direct browser actions.
- `Open-PwcliMiaoshou`: open a Miaoshou collection session.
- `Open-PwcliShopee`: open a Shopee collection session.
- `Open-PwcliTiktok`: open a TikTok collection session.
- `Save-PwcliMiaoshouState`: save Miaoshou login/session state.
- `Save-PwcliShopeeState`: save Shopee login/session state.
- `Save-PwcliTiktokState`: save TikTok login/session state.
- `Show-PwcliPaths`: show local helper paths and artifact locations.

For manual shop inspection and account-session maintenance, use the same
account-scoped session paths as formal collection. Always pass `-AccountId`
when the goal is to create or refresh a reusable account session. Do not treat
temporary no-account `pwcli` sessions as formal collection session sources.

See:

- `docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md`
- `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`
- `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`

Common `pwcli` action categories:

- Open or attach to a browser session.
- Capture page snapshots for agent analysis.
- Click, fill, press, reload, and inspect page state.
- Save and load authenticated browser state.
- Capture screenshots for UI or selector evidence.

Prefer Markdown artifacts for snapshots and notes so agents can read evidence directly.

## Evidence Helpers

- `pwsnap`: capture a Markdown page snapshot.
- `pwnote`: write a Markdown note for agent consumption.
- `pwshot`: capture a screenshot.
- `pwpack`: package related evidence artifacts.
- `pwcap`: capture a Markdown snapshot and screenshot together.

Use evidence helpers when reporting collection bugs, selector changes, login-state problems, or page-flow differences.

## `pwcap`

`pwcap` exists in the current PowerShell helper set and refers to the snapshot-plus-screenshot capture helper. If only repo-local scripts are available, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-cap.ps1 -Name <artifact-name>
```

Repo fallback behavior:

- `scripts/pw-cap.ps1` requires `-Name`.
- Optional parameters are `-Ref`, `-Ext`, and `-Session`.
- `-Session` defaults to `$env:PLAYWRIGHT_CLI_SESSION`.
- The script captures a `pwcli snapshot` Markdown artifact and a screenshot artifact.
- The script forwards `-s=<session>` when a session is provided.

## Repo-Local Fallback Scripts

Treat these scripts as implementation assets or fallback paths:

- `scripts/pwcli.ps1`: delegates to `scripts/pwcli_native.py`.
- `scripts/pw-open.ps1`: open or attach to a session.
- `scripts/pw-step.ps1`: execute an interaction step.
- `scripts/pw-note.ps1`: create a note artifact.
- `scripts/pw-shot.ps1`: create a screenshot artifact.
- `scripts/pw-pack.ps1`: package artifacts.
- `scripts/pw-cap.ps1`: capture snapshot and screenshot artifacts together.

Do not replace the active `pwcli + playwright skill + agent` workflow with legacy recorder flows unless the user explicitly asks to inspect or maintain the legacy recorder path.

## Related References

- `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
- `docs/guides/PWCLI_AGENT_DEBUGGING_SOP.md`
- `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`
- `docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md`
- `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`
