# Verification Pause Resume Design

**Date:** 2026-03-26  
**Last Updated:** 2026-03-26

## Goal

Unify captcha and OTP pause/resume handling across:

- recorder pre-login
- component testing
- production collection tasks

The system must consistently pause, surface a recovery UI, accept verification input, resume on the same execution context, and report structured success or failure.

## Non-Goals

Out of scope for this design:

- OCR or automatic captcha solving
- third-party captcha provider integration
- browser-manual completion mode without value callback
- redesigning the entire task center UI

## Core Decision

All verification types use a single recovery model:

**pause -> collect verification input -> resume execution**

No browser-side “I already completed it manually” mode is supported.

This applies equally to:

- graphical captcha
- SMS OTP
- email OTP

## Unified State Machine

Shared states:

- `running`
- `verification_required`
- `verification_submitted`
- `verification_retrying`
- `verification_resolved`
- `verification_failed`
- `expired`

These states are attached to different owners:

- recorder: `recorder_session`
- component test: `component_test`
- production collection: `collection_task`

## Unified Verification Payload

All owners expose the same verification state fields:

- `state`
- `verification_type`
- `verification_id`
- `owner_type`
- `owner_id`
- `phase`
- `current_url`
- `screenshot_url`
- `message`
- `created_at`
- `expires_at`
- `attempt_count`

For multi-account collection, the payload must also include:

- `account_id`
- `store_name`

## Unified Resume Request

All resume APIs accept the same body:

```json
{
  "captcha_code": "1234",
  "otp": null
}
```

Rules:

- exactly one effective value is allowed
- graphical captcha uses `captcha_code`
- OTP uses `otp`
- empty strings are invalid

## Unified Resume Protocol

Resume semantics are fixed:

1. execution hits verification
2. component raises `VerificationRequiredError(type, screenshot_path)`
3. owner state becomes `verification_required`
4. frontend surfaces a verification dialog
5. user submits verification value
6. owner state becomes `verification_submitted`
7. executor/recorder/tester reloads value into the existing runtime context
8. owner state becomes `verification_retrying`
9. execution resumes on the same page/context
10. gate is re-evaluated
11. state becomes `verification_resolved` or `verification_failed`

## Frontend Model

All three flows should use the same UI component:

- `frontend/src/components/verification/VerificationResumeDialog.vue`

Required behavior:

- modal dialog, not passive inline hint
- explicit paused state messaging
- screenshot preview for graphical captcha
- OTP input mode without screenshot
- disabled duplicate submissions while retrying
- visible timeout/expiry state

## Ownership Rules

Who owns the flow determines where the user must resume it:

- recorder flow -> recorder page
- component test flow -> component test page/dialog
- collection task flow -> task details/task center

Users should never need to leave the owner page to submit verification input.

## Multi-Account Collection Rule

For concurrent collection tasks, verification must be tracked at:

**task + account + verification instance**

The UI must not collapse all verification prompts into one generic task-level prompt.

Each pending verification item must show:

- platform
- account
- store
- verification type
- phase
- screenshot
- submission entry

## Backend Architecture

Introduce shared verification services:

- `backend/schemas/verification.py`
- `backend/services/verification_service.py`
- `backend/services/verification_state_store.py`

Integrate them into:

- `tools/launch_inspector_recorder.py`
- `tools/test_component.py`
- `modules/apps/collection_center/executor_v2.py`

## Phased Rollout

### Phase 1

Unified backend verification protocol and state model

### Phase 2

Recorder flow end-to-end

### Phase 3

Component test flow end-to-end

### Phase 4

Production collection flow, first single-account then multi-account

## Acceptance Criteria

The design is complete when:

- recorder captcha can be viewed and resumed from recorder page
- component test captcha can be viewed and resumed from test page
- collection task captcha can be viewed and resumed from task page
- resume continues same execution context rather than restarting flow
- failure, retry, timeout, and expiry states are explicit
- multi-account task prompts are separated per account
