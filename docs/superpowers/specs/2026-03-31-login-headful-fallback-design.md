# Login Headful Fallback Design

**Date:** 2026-03-31

## Goal

Define a unified fallback strategy for login components when automatic login fails under normal execution, especially for platforms such as TikTok where OTP, slider verification, and unstable post-submit state transitions make pure automatic login unreliable.

The system should:

1. try normal automatic login first
2. if login becomes unrecoverable, switch to a headed login fallback
3. allow the user to manually complete login until homepage is reached
4. persist the authenticated session
5. resume the main collection flow in the original execution mode

## Problem Statement

The current verification protocol already supports:

- `code_entry` for OTP and captcha values
- `manual_continue` for slider-style or manual interventions

But formal collection usually runs headless. In a truly headless session, a user cannot interact with the actual browser page for slider verification or complex manual login recovery.

This creates a mismatch:

- the protocol assumes "resume on the same page/context"
- the operational environment for formal collection is often headless

For login specifically, this mismatch can be resolved because successful login can be persisted and then reused by a later run.

## Scope

This design applies only to the **login stage**.

It does not apply to:

- export-stage manual repair
- post-login business page manual intervention
- resuming arbitrary in-page business workflows from headless to headed

## Core Decision

When login automation fails in a way that cannot be reliably resolved automatically, the system should:

1. stop the current login attempt
2. launch a **headed login fallback** using the same account identity, session namespace, and fingerprint inputs
3. continue login in headed mode
4. if still blocked, allow manual user handling until homepage is reached
5. validate homepage readiness
6. persist the authenticated session/storage state
7. restart the main collection flow from the normal login entry
8. allow the login component to short-circuit success from the newly persisted session

## Trigger Conditions

The fallback should be used only for login-stage failures that are not safely handled by existing automatic branches.

Examples:

- repeated ambiguous post-submit state
- repeated login-page refresh loops
- slider verification
- complex challenge pages not modeled as OTP/code-entry
- explicit `manual_intervention`

It should not trigger for:

- normal OTP where code-entry works
- simple incorrect password errors
- explicit account-disabled or permission-denied cases

## Execution Model

### Phase 1: Normal Login Attempt

The system first runs the existing login component in the current execution mode.

Possible outcomes:

- success
- `VerificationRequiredError("otp", ...)`
- `VerificationRequiredError("graphical_captcha", ...)`
- `VerificationRequiredError("slide_captcha", ...)`
- `VerificationRequiredError("manual_intervention", ...)`
- generic failure/timeout

### Phase 2: Decision

- `otp` / graphical code entry:
  keep the current value-entry protocol
- `slide_captcha` / `manual_intervention` / repeated ambiguous login failure:
  enter headed login fallback

### Phase 3: Headed Login Fallback

The fallback browser session must:

- use the same platform/account identity
- use the same session namespace/account_id
- use the same fingerprint selection rules
- preserve the same session output destination

It does **not** need to preserve the exact failing headless page instance.

Instead, it is a new login attempt specifically for establishing a valid authenticated session.

### Phase 4: Manual Completion

In headed mode, the user may:

- solve slider verification
- handle extra confirmation
- complete QR-like or challenge-based steps
- wait through unstable redirects

The target condition is **homepage ready**, not "button clicked".

### Phase 5: Homepage Validation

Before accepting the fallback as successful, the system must verify homepage readiness using the platform login component's success checks.

For TikTok this means:

- not on login URL
- homepage URL or target page URL reached
- homepage shell signals visible
- no longer in OTP/login-surface state

### Phase 6: Persist Session

Once homepage ready is confirmed:

- save storage state/session
- mark login fallback resolved

### Phase 7: Resume Main Flow

After session persistence, the main collection flow resumes in the original execution mode.

Recommended restart point:

- restart from the normal login component entry

Because the session is now valid, login should short-circuit quickly and the rest of the collection flow continues normally.

## Why Restart From Login Entry

This is safer than attempting to continue from an arbitrary half-completed state.

Benefits:

- one canonical login success path
- no hidden coupling between fallback browser and export browser
- session reuse becomes the bridge between headed fallback and normal execution
- easier reasoning and testing

## State Model

Introduce a login-specific fallback state progression:

- `login_running`
- `login_fallback_required`
- `login_fallback_running`
- `login_manual_intervention_required`
- `login_fallback_resolved`
- `login_fallback_failed`

These states can still map into the shared verification model for UI purposes, but the executor should track them explicitly inside the login orchestration layer.

## User Interaction Model

The user-facing action should be:

- "Open headed login fallback"
- user completes login in the fallback browser
- user presses "Continue"

Pressing "Continue" does not blindly trust the user action.

It means:

1. re-check homepage readiness in the headed fallback browser
2. if ready -> persist session and resume
3. if not ready -> remain blocked with an explicit reason

## Current Repository Fit

This design fits the repository better than forcing all login recovery into pure headless resume because:

- the session manager already exists
- login gate already exists
- login components already short-circuit when homepage/session is ready
- OTP value-entry already works as a separate path

The missing piece is the executor-level orchestration that connects:

- automatic login failure
- headed fallback login run
- manual completion
- session save
- resume from normal login entry

## Non-Goals

This design does not introduce:

- automatic slider solving
- generic business-stage headful fallback
- arbitrary page-state transfer from headless to headed and back

## Engineering Conclusion

For login only, the correct fallback strategy is:

**automatic login -> if unrecoverable, headed login fallback -> manual completion to homepage -> homepage validation -> save session -> restart main flow from normal login entry**
