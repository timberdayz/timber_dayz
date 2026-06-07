# Collection Runtime Restore Rules

This guide defines the active runtime restore rules for formal collection sessions. Use it when adjusting session reuse, persistent browser profiles, login gating, ready checks, or viewport policy.

## Core Principles

1. Prefer restoring the user-maintained browser profile over reconstructing runtime state.
2. Treat `login ready`, `target shop ready`, and `module ready` as separate gates.
3. Keep the restore phase as close as possible to a real human browser open.
4. Apply only the minimum runtime overrides needed for stability.

## Session Restore Priority

Formal collection should restore sessions in this order:

1. Persistent browser profile under `profiles/<platform>/<main_account_id>`
2. Saved `storage_state` under `data/sessions/<platform>/<main_account_id>/storage_state.json`
3. Fresh login

Rules:

- If a usable persistent profile exists, use `launch_persistent_context(...)` first.
- Do not prefer `storage_state` over a valid persistent profile.
- `storage_state` is a fallback, not the primary restore path.
- Shop-level tasks still resolve the session owner through `main_account_id`.

## Restore-Phase Minimalism

The restore phase must not overtake the browser's own recovery logic.

Allowed during persistent-profile restore:

- Open the persistent profile
- Wait for the browser to settle on its own
- Read diagnostic state
- Hand the settled page to the login component

Avoid during persistent-profile restore unless a platform explicitly proves it is safe:

- Forcing navigation to `login_url`
- Rebuilding state from `storage_state`
- Overriding page selection too early
- Overriding profile environment with aggressive runtime context settings

High-risk runtime overrides during persistent-profile restore:

- `user_agent`
- `locale`
- `timezone_id`
- `Accept-Language`
- `viewport`
- mobile/device-shape flags

### TikTok Exception

TikTok seller restore is especially sensitive to runtime overrides. The active rule is:

- For TikTok `persistent_profile` restore, strip runtime overrides that change the original browser environment.
- Keep only minimum safe options such as `accept_downloads`.

Reason:

- TikTok seller bootstrap depends on the original profile environment, seller cookies, local storage, IndexedDB, and shop-context recovery.
- Excess runtime overrides can make formal collection less stable than `pwcli` manual open.

## Page Selection Rules

Persistent-profile restore may recover multiple pages or tabs. The runtime must distinguish:

- `available_page_urls`: every restored page URL
- `selected_page_url`: the page continued by formal collection

Rules:

- Do not assume the first restored page is always the correct business page.
- Record all restored page URLs for diagnostics.
- When debugging a platform restore issue, compare restored pages from formal collection against a manual `pwcli` open of the same account.

## Ready Gates

Formal collection must not collapse all readiness into one boolean.

### 1. Login Ready

Definition:

- The browser session is authenticated and the platform is no longer on the login surface.

This does not imply:

- the correct shop is active
- the target module is fully usable

### 2. Target Shop Ready

Definition:

- The shop badge, region, or other business context matches the task target.

Examples:

- A seller homepage may be visible, but the wrong shop is active.
- A restored main-account profile may land on the last manually used shop rather than the current task target.

### 3. Module Ready

Definition:

- The target business module is visible and its key controls are usable.

Examples:

- filters are visible
- date range controls are stable
- export controls are present
- required table/grid content is rendered

## Stable Page Criteria

Before the login component judges a restored page, the runtime should wait until:

- navigation is no longer in progress
- the page is not auto-refreshing
- major loading or bootstrap indicators are gone
- the main DOM is visible

Important:

- DOM visibility is necessary but not sufficient for business readiness.
- If a platform depends on deferred business bootstrap, add a separate business-ready gate instead of weakening login detection.

## Viewport Policy

Viewport policy must not destabilize persistent-profile restore.

Rules:

- Do not blindly reuse profile-time viewport overrides during restore.
- Do not force a responsive or narrow layout that hides key controls.
- If a platform needs a stable desktop viewport for interaction, apply it after restore and after login/shop readiness is confirmed.

Practical consequence:

- Restore phase should be minimal.
- Interaction phase may normalize the viewport if needed for stable selectors and clicks.

## Debugging Checklist

When a restored session behaves differently from manual `pwcli` open, check these items in order:

1. Did formal collection use `persistent_profile` or fall back to `storage_state`?
2. What were `available_page_urls` and `selected_page_url`?
3. What runtime context overrides were applied?
4. Is the current shop context the target shop?
5. Is the page only `login ready`, or truly `module ready`?
6. Is a challenge/captcha shown on the correct seller page rather than on a wrong page?
7. Is the viewport hiding or collapsing controls?

## Anti-Patterns

- Treating `storage_state` as higher quality than a user-maintained profile
- Forcing `login_url` before checking the restored page
- Declaring success as soon as the login page disappears
- Assuming seller homepage means the target shop is correct
- Applying platform-wide fingerprint overrides to a sensitive persistent-profile restore path
- Using viewport normalization as a substitute for real ready detection

## Recommended Evidence for Future Incidents

For each restore failure, capture:

- `session_source`
- `runtime_strategy_reason`
- `persistent_profile_path`
- `available_page_urls`
- `selected_page_url`
- `runtime_context_summary`
- screenshot of the blocking UI
- whether the issue occurs in manual `pwcli` open of the same account

This evidence should be enough to decide whether the failure is caused by:

- wrong restore source
- wrong page selection
- runtime override interference
- wrong shop context
- module-level readiness failure
