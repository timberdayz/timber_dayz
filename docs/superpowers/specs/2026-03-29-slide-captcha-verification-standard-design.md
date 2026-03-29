# Slide Captcha Verification Standard Design

**Date:** 2026-03-29

## Goal

Define a single repository-wide standard for handling slider-style verification challenges so that test flows and formal collection flows do not invent platform-specific ad hoc behavior.

## Problem Statement

Slider verification is not a normal happy-path login step and is not equivalent to image captcha code entry or OTP entry.

It is:
- low-frequency
- challenge-based
- bound to the current browser page and session
- usually not resumable through a text input value

If each component handles it differently, the system will drift into incompatible resume rules and inconsistent frontend behavior.

## Standard Positioning

Slider verification must be modeled as:

- a **verification-required branch**
- outside the primary component success path
- but still inside the **shared verification protocol**

It is not:
- normal success flow
- a generic unknown error
- a text captcha that accepts `captcha_code`

## Verification Types

The shared verification protocol must support three standardized verification types:

- `graphical_captcha`
- `otp`
- `slide_captcha`

And each verification type must declare a frontend interaction mode:

- `code_entry`
- `manual_continue`

Mapping:

- `graphical_captcha` -> `code_entry`
- `otp` -> `code_entry`
- `slide_captcha` -> `manual_continue`

## Detection Standard

Slider detection must use **multi-signal detection**, not a single hard-coded selector.

### Required Detection Order

After a sensitive action such as login submit:

1. check explicit login error
2. check success/homepage readiness
3. check OTP visibility
4. check slider verification visibility
5. fallback to generic failure

This ordering prevents temporary loading states from being misclassified as slider challenges.

### Slider Detection Signals

#### Text signals

Examples:
- `滑动验证`
- `请拖动滑块`
- `拖动滑块`
- `向右滑动`

#### Structural signals

Examples:
- slider container
- captcha widget container
- `data-nc-*`
- `nc_wrapper`
- `captcha-slider`

#### Context signals

Slider detection should only be considered valid when:
- the user already submitted credentials or a protected action
- the page is not yet in a success state
- the page is not already in an OTP state

## Runtime Behavior

When `slide_captcha` is detected:

1. capture a screenshot
2. raise verification-required with:
   - `verification_type = "slide_captcha"`
   - `verification_input_mode = "manual_continue"`
3. keep the current browser session alive
4. do not close the browser
5. do not recreate the page or context
6. do not convert the challenge into `captcha_code`

## Resume Behavior

Slider verification resume must use a **manual-complete signal**, not a text value.

Shared resume payload supports:

- `captcha_code`
- `otp`
- `manual_completed`

Exactly one must be provided.

For slider verification:
- frontend sends `manual_completed = true`
- backend resumes on the same page
- component re-checks current state instead of filling an input

## Resume State Machine

After `manual_completed = true`:

1. re-check homepage readiness
2. if homepage ready -> success
3. else re-check OTP visibility
4. if OTP visible -> transition into OTP branch
5. else re-check slider visibility
6. if slider still visible -> fail with explicit message or continue waiting under bounded timeout
7. else return a concrete failure message

## Session Rules

Slider verification must always preserve:

- current browser process
- current browser context
- current page/tab
- current challenge state

It must never:

- restart the browser before resume
- open a fresh page for resume
- treat slider completion as stateless input replay

## Test Environment vs Formal Collection

The logic is the same in both environments.

### Shared behavior

- same `verification_type`
- same screenshot capture
- same `manual_continue` interaction mode
- same same-page resume
- same post-resume re-check logic

### Different host surfaces

#### Component test environment

- verification is exposed through version test status APIs
- frontend shows screenshot and a continue button

#### Formal collection environment

- verification is exposed through collection task APIs
- task enters paused / verification-required state
- operator completes slider in the headed browser and resumes task

## Component Responsibilities

Components should only do:

- detect slider challenge
- raise `VerificationRequiredError("slide_captcha", screenshot_path)`
- after resume, re-check state

Components must not:

- implement custom frontend instructions
- invent per-component resume payloads
- auto-solve slider captchas
- store slider-specific business logic outside the shared verification protocol

## Playwright Alignment

This design aligns with Playwright's supported strengths:

- headed debugging and manual inspection
- keeping the same browser/page alive
- pausing and continuing real browser interaction
- persisting authenticated state only after success

Playwright official documentation supports:
- headed mode and debugging flows
- actionability checks
- authentication state reuse

It does **not** provide an official automatic slider-captcha solving pattern.

Therefore the standard must be:

- manual completion in the live browser
- automated state recovery after completion

## Repository Rule

All platforms that encounter slider verification must adopt this shared protocol.

No component may introduce a platform-specific slider resume contract unless the shared protocol is extended first.
