# Recorder Segment Validation Design

**Date:** 2026-03-25  
**Last Updated:** 2026-03-25

## Goal

Add a recorder-side validation loop that lets operators inspect live recorded steps and validate a selected contiguous segment without leaving the recorder page.

The feature must improve authoring speed for collection scripts while preserving the existing production runtime path.

## Non-Goals

Out of scope for the first version:

- replacing the existing component version test flow
- validating inside the same Inspector page that is being used for recording
- automatic validation after every single step
- generating temporary production versions during recording
- introducing a background job system for recorder validation

## Current Reality Check

The repository already has the main pieces of the workflow:

- recorder UI:
  - `frontend/src/views/ComponentRecorder.vue`
- recorder backend:
  - `backend/routers/component_recorder.py`
  - `backend/schemas/component_recorder.py`
- recorder runtime:
  - `tools/launch_inspector_recorder.py`
- generator:
  - `backend/services/steps_to_python.py`
- component tester and transition gates:
  - `tools/test_component.py`
  - `modules/apps/collection_center/transition_gates.py`

The main gaps are:

- live recorder steps are not guaranteed to be available during recording
- recorder UI cannot validate an in-progress segment
- transition validation logic exists for tester/runtime, but recorder has no segment-scoped validator

## Key Decisions

### 1. Validation runs from the recorder page

Operators trigger validation from `ComponentRecorder.vue`, using the same step selection area they already use for batch tagging.

The recorder page is the only first-class UI for this feature.

### 2. Validation uses an isolated browser context

Segment validation must never reuse the active Inspector browser/page.

The validator creates its own Playwright context so recording state and validation state cannot contaminate each other.

### 3. Validation is manual, not automatic

The first version adds a `校验当前段` action that validates only when the user clicks it.

This keeps false positives, load, and UI noise under control.

### 4. Validation is signal-based, not action-based

A segment passes only when it reaches an explicit ready signal, not merely because its clicks/fills did not throw.

Supported signals:

- `login_ready`
- `navigation_ready`
- `date_picker_ready`
- `filters_ready`
- `export_complete`

### 5. Auto signal resolution is allowed, but explicit selection wins

The UI defaults to `auto`.

Backend resolves `auto` using:

1. selected steps' `step_group`
2. component type
3. export-specific fallback rules

If the user explicitly selects a signal, backend uses that signal.

## Architecture

## Channel A: Live Recording Feed

`tools/launch_inspector_recorder.py` incrementally writes the current step payload to `steps_file` whenever the recorded step set changes.

`backend/routers/component_recorder.py` updates `/recorder/steps` to read the latest `steps_file` during active recording, instead of relying only on the in-memory session snapshot.

`frontend/src/views/ComponentRecorder.vue` continues polling `/recorder/status` and `/recorder/steps`, so the step editor reflects live actions before recording stops.

## Channel B: Segment Validation

The recorder page posts the selected contiguous step slice to a new endpoint:

- `POST /collection/recorder/validate-segment`

The backend routes the request to a new service:

- `backend/services/recorder_segment_validator.py`

The service:

1. builds an isolated Playwright context
2. prepares prerequisite state, especially login gate readiness
3. replays the selected step segment
4. evaluates the requested or resolved ready signal
5. captures structured output and a failure screenshot when needed

## Frontend UX

Add to the recorder page:

- a `校验当前段` button in the step toolbar
- an `expected signal` selector with `auto` default
- contiguous-range validation guard in the client
- a validation result panel showing:
  - pass/fail
  - resolved signal
  - step range
  - current URL
  - failure step
  - screenshot
  - actionable suggestions

The user flow is:

1. start recording
2. perform a small action burst
3. wait for steps to appear live in the editor
4. select a contiguous range
5. click `校验当前段`
6. inspect the validation result

## API Contract

Add request/response schemas in `backend/schemas/component_recorder.py`.

Request fields:

- `platform`
- `component_type`
- `account_id`
- `data_domain`
- `sub_domain`
- `expected_signal`
- `step_start`
- `step_end`
- `steps`

Response fields:

- `passed`
- `resolved_signal`
- `step_start`
- `step_end`
- `validated_steps`
- `current_url`
- `failure_step_id`
- `failure_phase`
- `error_message`
- `screenshot_url`
- `suggestions`

The first version should return synchronously.

## Ready Signal Rules

### `login_ready`

Use existing login gate semantics from `tools/test_component.py` and `modules/apps/collection_center/transition_gates.py`.

Evidence should include:

- non-login state
- acceptable confidence
- current URL context

### `navigation_ready`

Must use dual confirmation:

- route or URL moved to the intended area
- target page marker is visible

### `date_picker_ready`

Pass when the segment produces an observable accepted date state, such as:

- picker closes and field value changes
- applied date label changes

### `filters_ready`

Pass when the filter has been accepted by the UI, such as:

- control value changes
- result region refreshes
- state marker changes

### `export_complete`

Must follow the repository rule:

- downloaded file exists
- file is non-empty

Toast-only or dialog-only success is not sufficient.

## Error Observability

Segment validation failures must be structured and diagnosable.

At minimum include:

- `phase`
- `step_id`
- `component_type`
- `expected_signal`
- `resolved_signal`
- `current_url`
- selector context when available
- failure screenshot path

## Testing Strategy

Add backend tests for:

- validate-segment request contract
- contiguous step rules
- auto signal resolution
- failure structure
- export-complete gate failure on missing file

Add recorder integration coverage for:

- live step feed reads latest `steps_file`
- recorder validation endpoint returns result payload compatible with the UI

Manual acceptance should confirm:

- steps appear during recording before stop
- validation does not interrupt the active Inspector session
- navigation and export signals do not get conflated

## Rollout

Recommended implementation order:

1. live step feed during recording
2. validation request/response contract tests
3. backend validator service and route
4. recorder page UI integration
5. targeted verification and regression tests
