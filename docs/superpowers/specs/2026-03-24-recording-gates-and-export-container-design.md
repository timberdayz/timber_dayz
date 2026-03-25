# Recording Gates And Export Container Design

**Date:** 2026-03-24  
**Last Updated:** 2026-03-24

## Goal

Simplify collection recording and testing by defining one consistent model for:

- recorder preconditions
- login gating
- export recording
- export completion
- tagged reusable sub-capabilities inside export components

The immediate target is to stop invalid flows such as:

- starting export recording before login is actually complete
- allowing recorder/test/runtime to use different success criteria for the same transition

## Non-Goals

Out of scope for this design:

- redesigning the whole collection UI
- changing platform-specific selector implementations for every component
- removing step tagging from the recorder
- replacing platform-specific login implementations with one shared login script
- solving platform-specific date-range label differences in this document

## Current Reality Check

The repository already has several partial standards, but they are not applied consistently across recorder, tester, and runtime.

What exists today:

- base component contract via:
  - `modules/components/base.py`
- login/export/date-picker/navigation base types
- execution ordering guidance via:
  - `modules/apps/collection_center/execution_order.py`
- collaboration guidance via:
  - `docs/guides/COMPONENT_COLLABORATION.md`
- recorder step tagging
- login-state detection via:
  - `modules/utils/login_status_detector.py`

What is still inconsistent:

- recorder pre-login, component test pre-login, and runtime pre-login do not behave like one state machine
- export components are treated partly as self-contained containers and partly as if navigation/date/date-picker should exist as top-level execution stages
- component transition completion signals are not defined as one SSOT
- recorder previously allowed export recording to begin even when login was not confirmed complete

## Key Decisions

### 1. Export is a container component

`export` is the primary business component for collection.

It is responsible for the full data-export flow after login readiness:

- reach the correct page
- switch shop if needed
- set date range
- apply filters if needed
- trigger export
- wait for download

`navigation`, `shop_switch`, `date_picker`, and `filters` remain valid reusable capabilities, but in the recorder and generated output they are treated as **tagged substeps inside export**, not as the top-level runtime chain.

### 2. Login is a gate, not an export substep

`login` is not part of the business export flow itself.

It is a **gate** that must be satisfied before:

- starting export recording
- starting export component testing
- starting runtime export execution when the session is not already valid

### 3. Hard gate before Inspector

The recorder must not open Inspector for export recording until login has been confirmed complete.

Approved behavior:

- if the current account session is already valid, skip login
- otherwise run automatic login
- if login is blocked by captcha/OTP, pause before recording
- if login is not confirmed after automatic login, fail fast and do not open Inspector

No fallback mode should allow export recording to begin from the login page.

### 4. Every step boundary needs an explicit completion signal

Each meaningful transition must produce a deterministic “ready/complete” signal.

This applies to:

- login
- navigation
- date selection
- filters
- captcha pause/resume
- export completion

### 5. Recorder, tester, and runtime must share the same gates

The same gating semantics must be reused across:

- recorder pre-login
- component test pre-login
- runtime pre-login

Platform-specific implementations may differ, but the transition contract must stay the same.

## Canonical Model

## Top-Level Flow

For export recording/testing/runtime, the top-level model is:

`login_gate -> export_container -> export_complete`

Not:

`login -> navigation -> date_picker -> filters -> export`

at the execution-engine top level.

## Recorder State Machine

Recommended recorder states:

- `idle`
- `starting`
- `login_checking`
- `login_verification_pending`
- `login_ready`
- `inspector_recording`
- `stopped`
- `code_generated`
- `saved_draft`
- `failed_before_recording`

Required transitions:

1. `starting -> login_checking`
2. `login_checking -> login_ready`
   - only if login gate succeeds
3. `login_checking -> login_verification_pending`
   - when captcha/OTP requires user input
4. `login_verification_pending -> login_checking`
   - after callback submission
5. `login_checking -> failed_before_recording`
   - if login cannot be confirmed
6. `login_ready -> inspector_recording`
   - only then may Inspector open

## Tagged Export Substeps

Recorder-generated export steps may carry tags such as:

- `navigation`
- `shop_switch`
- `date_picker`
- `filters`
- `captcha`
- `export_action`
- `download_wait`

These tags serve four purposes:

- human review
- testing diagnostics
- future refactoring into reusable sub-capabilities
- transition-signal verification inside the export container

They do **not** change the top-level model away from “export as container”.

## Completion Signals

### 1. `login_ready`

`login_ready` must not be defined as “clicked login”.

It must be defined as:

- current URL has left the login page, and
- current URL matches a platform backend/workbench pattern, and
- at least one platform logged-in signature element is visible

This is a deliberate dual-signal rule:

- URL-only is too weak
- element-only is too weak

The login detector may still internally use URL/cookie/element voting, but the gate result exposed to recorder/test/runtime should be interpreted as:

- `LOGGED_IN`
- confidence `>= 0.7`

Otherwise the gate is not complete.

### 2. `navigation_ready`

Navigation is complete only when:

- the page has reached the intended business page, and
- the target page’s key feature element is visible

Examples:

- order list visible
- product table visible
- analytics panel visible
- service page list visible

### 3. `date_picker_ready`

Date selection is complete only when:

- the intended date range has been applied in the UI

Not when:

- the picker was opened
- a quick option was clicked but not reflected
- the custom date fields were filled but not confirmed

### 4. `filters_ready`

Filter selection is complete only when:

- the selected filter state is reflected in the UI
- or the filtered results have visibly refreshed

### 5. `captcha_pending`

Captcha/OTP is a first-class pause state.

When reached:

- the flow must stop
- the required verification artifact must be surfaced
- after user input is submitted, execution continues on the same page/context

This should behave like a formal gate, not as a best-effort warning.

### 6. `export_complete`

Export is complete only when:

- a download event was triggered, and
- the file was persisted to disk, and
- the file path exists, and
- the file is not empty

For the first standardization pass, “downloaded file exists and is non-empty” is the canonical success criterion.

This is better than:

- button click success
- toast success
- progress modal disappearing

Those may remain supporting signals, but not the primary completion definition.

## Recorder Behavior

## Start Recording

When the user starts export recording:

1. validate account exists
2. create recorder session in `starting`
3. create browser context with:
   - account-scoped persistence
   - fixed fingerprint
4. enter `login_checking`
5. check whether session is already valid
6. if not valid:
   - run canonical platform login component
7. if captcha/OTP is required:
   - enter `login_verification_pending`
8. after resume:
   - return to `login_checking`
9. only when `login_ready` is confirmed:
   - open Inspector
   - enter `inspector_recording`
10. if not confirmed:
   - enter `failed_before_recording`
   - do not open Inspector

## Stop Recording

When the user stops recording:

1. parse recorded steps
2. preserve component-step tags
3. generate one self-contained export component
4. retain tags for later review/testing
5. save draft version only after user confirms save

## Tester Behavior

Export component testing must reuse the same pre-login gate:

1. check existing session
2. login if needed
3. pause on verification if needed
4. only execute export test after `login_ready`

This prevents the test page from accepting “export started from login page” as a valid test attempt.

## Runtime Behavior

Runtime export execution also uses the same gate:

1. restore/reuse session if possible
2. run platform login component if required
3. verify `login_ready`
4. execute export container
5. verify `export_complete`

## Transition Contract Shape

Recommended logical transition outcomes:

- `ready`
- `pending_verification`
- `failed`

Recommended payload fields:

- `stage`
- `status`
- `reason`
- `confidence`
- `current_url`
- `matched_signal`
- `screenshot_path` when applicable

Example stages:

- `login_gate`
- `navigation`
- `date_picker`
- `filters`
- `export`

## Recommended Refactor Direction

### 1. Move to shared gate helpers

Introduce shared gate helpers so recorder/test/runtime stop re-implementing the same logic differently.

Priority helpers:

- `ensure_login_ready(...)`
- `ensure_navigation_ready(...)`
- `ensure_date_picker_ready(...)`
- `ensure_export_complete(...)`

### 2. Keep step tags, but downgrade their architectural role

Keep recorder tags because they are useful.

But treat them as:

- metadata and diagnostics

not as:

- a second competing top-level execution model

### 3. Make start-recording semantics honest

The recorder start API should no longer imply:

- “recording is ready”

when it only means:

- “subprocess started”

The returned state should reflect gate progress truthfully.

## Risks

### 1. Over-strict gates may block valid sessions

If backend signature selectors are too strict, valid sessions may be rejected.

Mitigation:

- require per-platform logged-in signature selectors to be curated
- keep detector evidence visible in logs

### 2. Export completion may vary by platform

Some platforms may show async generation before actual download.

Mitigation:

- keep “file exists and non-empty” as the final success signal
- allow async pre-download waiting inside export component logic

### 3. Historical recorder flows may assume permissive behavior

Some users may be used to recording from semi-invalid states.

Mitigation:

- deliberately break that behavior
- prefer correctness over permissiveness

## Testing Strategy

Required regression coverage:

- recorder does not open export recording until `login_ready`
- recorder runs canonical Python login component when present
- recorder fails before recording when post-login check does not confirm success
- captcha/OTP pre-login pause returns to the same gate state
- miaoshou/shopee/tiktok login gates all support active-session short-circuit
- export completion requires actual downloaded file presence

## Implementation Outline

1. Harden recorder pre-login gate
2. Align tester pre-login gate with recorder/runtime
3. Add shared transition helper layer
4. Update docs/rules to state:
   - export is container
   - login is gate
   - completion signals are mandatory
5. Update UI wording to show actual recorder states

## Final Position

The correct simplified model is:

- `login` is a gate
- `export` is a self-contained business container
- `navigation/date_picker/filters` are tagged sub-capabilities inside export
- each transition must emit a deterministic completion signal
- recorder/test/runtime must share the same gate semantics

This is the smallest model that matches how the product is actually used while still enforcing correctness.
