# TikTok Edge Profile Semi-Automatic Collection Design

**Date:** 2026-04-16

## Goal

Introduce a TikTok-specific formal collection runtime that reuses a local dedicated Microsoft Edge profile on this Windows machine, prioritizing low-detection, stable export execution over fully headless automation.

This design is intentionally platform-specific.

- TikTok gets a dedicated runtime path.
- Existing Shopee and Miaoshou formal collection behavior stays unchanged.
- The primary objective is to save repetitive manual work, not to guarantee unattended server-style headless collection.

## Problem Statement

Current TikTok formal collection still depends on Playwright-managed browser startup.

In the current repository state:

- the formal executor opens Playwright runtime browsers through the normal collection runtime flow
- browser launch args are normalized by [`browser_config_helper.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/browser_config_helper.py)
- branded browser overrides such as `channel` and `executable_path` are explicitly removed

That behavior is reasonable for normal cross-platform automation, but it is a mismatch for TikTok.

Observed practical issue:

- the same TikTok account can log in normally in a human-operated local Edge browser
- the Playwright-managed browser is much more likely to trigger stricter anti-automation checks
- in the worst case, even the graphical verification flow does not become passable in the current automated runtime

So the current bottleneck is not primarily the canonical TikTok component semantics.

The bigger bottleneck is the runtime browser strategy.

## Confirmed Constraints

The design is based on the following confirmed user requirements:

- TikTok formal collection may be semi-automatic rather than fully unattended
- TikTok does not need strict headless support
- TikTok should use a dedicated Edge profile, not the user's everyday personal browser profile
- that dedicated Edge profile is local to this Windows machine only
- if session expiry, verification, or login is required, the task should pause and wait for human intervention in the same Edge window, then continue

## Non-Goals

This design does not attempt to provide:

- fully headless TikTok collection
- Docker-compatible TikTok runtime parity
- server-side TikTok collection portability
- generic cross-platform browser replacement for all collection platforms
- a stealth-arms-race redesign of every Playwright context option

This design also does not replace the current canonical TikTok components with recorder output or ad hoc scripts.

## Why Headless Is Not The Target

TikTok's risk model here is not just about cookies.

The practical goal is to stay as close as possible to a real local seller-browser environment:

- real Edge binary
- real Edge profile directory
- real local login state
- real interactive recovery path when verification appears

That makes a fully headless target strategically wrong for this platform.

For TikTok, the better optimization is:

- reduce manual navigation and export clicks
- preserve a human-compatible recovery loop
- accept a local headed runtime when needed

In other words, this is a productivity automation path, not a pure headless infrastructure path.

## Options Considered

### Option A: Keep current Playwright-managed browser runtime and only add more stealth parameters

Trade-offs:

- smallest apparent code change
- does not address the user's observed real-world difference between local Edge and Playwright browser behavior
- keeps TikTok formal collection dependent on a browser family already shown to trigger stricter detection
- likely leads to repeated small evasive patches with weak long-term stability

### Option B: Reuse Edge login once, then export storage state back into the current runtime

Trade-offs:

- smaller runtime redesign than full Edge takeover
- still returns the actual collection flow to a Playwright-managed browser family
- may preserve cookies while losing important real-browser characteristics
- likely better than current behavior, but still not aligned with the user's direct observation

### Option C: Add a TikTok-specific dedicated Edge-profile runtime and run existing canonical TikTok components inside that attached browser context

Trade-offs:

- best alignment with the observed working environment
- keeps current canonical component semantics mostly intact
- introduces a clear local-machine-only boundary
- requires a separate runtime path and pause/resume handling

**Recommendation:** Option C.

## Design Summary

TikTok formal collection should gain a new runtime mode:

- `edge_profile_attached`

This mode will:

1. launch local Microsoft Edge with a dedicated TikTok profile directory
2. expose a local remote-debugging endpoint
3. attach to that Edge instance through CDP
4. reuse the attached browser context and page for the existing TikTok formal collection components
5. pause instead of failing hard when verification or re-login is required
6. allow the user to resolve the challenge manually in the same browser window and then continue execution

This runtime is explicitly a local semi-automatic Windows workflow.

## Scope Boundary

This design changes:

- TikTok formal runtime browser acquisition
- TikTok runtime strategy selection
- TikTok verification/login interruption handling
- TikTok-specific operator guidance and diagnostics

This design does not fundamentally change:

- canonical TikTok login component behavior
- canonical TikTok export component boundaries
- TikTok page-entry semantics
- TikTok shop-switch semantics
- TikTok date-picker semantics
- output file validation semantics

## Target Architecture

## 1. TikTok-Specific Runtime Strategy

TikTok should no longer be forced through the same browser launch policy as the general formal collection path.

Instead, runtime strategy selection should support a TikTok-specific branch:

- default TikTok formal mode: `edge_profile_attached`
- fallback TikTok modes: explicit only, not silent
- non-TikTok platforms remain on current runtime behavior

This keeps platform-specific risk isolated instead of weakening the global runtime policy.

## 2. Dedicated Local Edge Profile

TikTok formal collection should use a dedicated Edge user-data directory created and maintained only for TikTok collection on this machine.

Requirements:

- must not depend on the user's everyday personal Edge profile
- must be stable across runs
- must preserve login state whenever TikTok session remains valid
- must be documented as single-machine local state

Operational model:

- the user logs in manually in that dedicated Edge profile when needed
- future runs attempt to reuse the same profile automatically
- collection uses the profile as the primary session source, not as a temporary bootstrap artifact

## 3. Edge Launch And Attachment Layer

TikTok runtime should introduce a browser provider with this responsibility:

- resolve local Edge executable path
- resolve the configured TikTok dedicated profile path
- start Edge with:
  - remote debugging port
  - dedicated user-data-dir
  - anti-noise startup flags only where operationally necessary
- attach through CDP
- surface an existing or newly created page back to the runtime executor

Important boundary:

- this provider owns browser process attachment
- TikTok components do not own browser startup policy

## 4. Existing Canonical Components Stay In Charge Of Business Flow

Once the attached Edge page is available, the current canonical TikTok components should keep owning business behavior:

- [`modules/platforms/tiktok/components/login.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/login.py)
- [`modules/platforms/tiktok/components/products_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/products_export.py)
- [`modules/platforms/tiktok/components/analytics_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/analytics_export.py)
- [`modules/platforms/tiktok/components/services_agent_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/tiktok/components/services_agent_export.py)

The design goal is not to bypass the canonical component system.

The design goal is to give the canonical TikTok components a browser environment that better matches the real working environment.

## 5. Verification And Re-Login Pause/Resume Model

When TikTok runtime detects any of the following:

- redirected login page
- graph verification / human verification requirement
- OTP or additional trust confirmation
- login gate remains unsatisfied after automatic attempt

the executor should not immediately mark the task as a normal hard failure.

Instead it should enter a controlled paused state.

Paused-state contract:

1. keep the current Edge window and page alive
2. mark the task as waiting for operator intervention
3. present a clear instruction that the user should complete verification or login in the existing TikTok Edge window
4. allow the task to continue from the same browser context after operator confirmation

This is the core difference between semi-automatic recovery and brittle automated retry loops.

## 6. Runtime State Model

TikTok should treat the dedicated Edge profile as the durable primary runtime state.

`storage_state` may still be useful for diagnostics or compatibility, but it should no longer be the main TikTok session strategy.

Priority order for TikTok:

1. attached dedicated Edge profile
2. same-context resume after manual intervention
3. explicit manual recovery if the profile is no longer valid

This avoids degrading TikTok back into a Playwright-bundled browser path after session reuse.

## 7. Execution Mode

TikTok formal collection should default to a headed local mode.

Expected behavior:

- a visible Edge process exists
- the window may be minimized by the operator, but the runtime does not guarantee invisible execution
- desktop session availability is assumed

This design intentionally does not promise fully headless TikTok execution.

## Detailed Component Responsibilities

## Browser Provider Layer

Responsibilities:

- find or validate Edge executable path
- validate the TikTok dedicated profile directory
- allocate or reuse remote debugging port
- start and monitor Edge process
- attach through CDP
- expose browser, context, page, and diagnostics

Must not:

- own TikTok business navigation
- own export semantics
- decide business success

## Runtime Strategy Layer

Responsibilities:

- choose `edge_profile_attached` for TikTok formal collection by default
- keep current modes for other platforms
- annotate runtime diagnostics clearly so logs and UI indicate the actual browser strategy in use

Must not:

- silently downgrade TikTok to Playwright bundled Chromium without explicit operator intent

## TikTok Components

Responsibilities remain unchanged in principle:

- login surface handling
- shop selection
- page entry
- date handling
- export triggering
- download success validation

Required adaptation:

- components must tolerate pause/resume after human recovery without assuming a fresh browser

## Error Handling Model

## Hard Failure

Hard failure still applies when:

- Edge executable cannot be found
- dedicated profile path is invalid or inaccessible
- CDP attachment fails repeatedly
- export action completes but no valid file is produced
- business page remains unusable after recovery

## Paused Recovery

Paused recovery applies when:

- TikTok asks for verification
- TikTok login state is missing or expired
- the operator can likely recover by interacting with the current page

This is not a generic retry.

This is an intentional operator-assisted continuation state.

## Security And Safety Boundaries

- only a dedicated local TikTok profile should be used
- the design should avoid modifying the user's everyday personal Edge profile
- the runtime should not require exporting secrets into code or repository config
- any machine-specific profile path should live in local config, not hard-coded repository constants

## Testing Strategy

Required verification focus:

1. TikTok runtime strategy selects `edge_profile_attached` when platform is `tiktok`
2. non-TikTok platforms are unaffected
3. attached Edge runtime returns a usable page/context bundle to the executor
4. TikTok component execution still succeeds when given an attached browser page
5. verification-required state transitions into paused recovery instead of immediate terminal failure
6. task continuation resumes from the same attached context after manual intervention
7. export file validation remains unchanged:
   - file path returned
   - file exists
   - file non-empty

Useful lower-level tests:

- Edge launch command construction
- profile path resolution
- CDP attachment failure reporting
- paused-state metadata and diagnostics

## Migration Plan Shape

Recommended implementation order:

1. add the written spec and implementation plan first
2. introduce TikTok runtime strategy constants and diagnostics
3. add a local Edge attachment helper/provider
4. wire TikTok formal collection to use that provider
5. add paused recovery semantics for verification/login-required states
6. adapt targeted tests around runtime strategy and pause/resume behavior
7. run focused TikTok formal collection verification on this machine

## Operational Expectations

Expected daily workflow after implementation:

1. user maintains a dedicated TikTok Edge profile on this machine
2. formal TikTok collection launches or reuses that Edge profile
3. most runs proceed automatically through export
4. if TikTok asks for verification or login, the task pauses
5. user completes the action in the same Edge window
6. task resumes and continues the export flow

This is the intended productivity win:

- fewer repetitive manual clicks
- preserved real-browser environment
- lower anti-automation friction than the current Playwright-managed browser path

## Final Recommendation

Do not keep treating TikTok as a normal bundled-browser formal collection target.

For TikTok, the correct optimization is:

- use a dedicated local Edge profile
- attach to that browser instead of forcing Playwright-managed startup
- keep current canonical TikTok components
- replace hard-fail login/verification behavior with pause/resume recovery
- explicitly accept a local headed semi-automatic runtime rather than promising full headless support

That gives the repository a TikTok strategy that matches real-world usage instead of forcing TikTok into the same browser assumptions as lower-friction platforms.
