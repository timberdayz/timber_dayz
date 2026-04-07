# Collection Verification Workbench Design

**Date:** 2026-03-27  
**Last Updated:** 2026-03-27

## Goal

Upgrade the current minimal collection-task verification handling into a task-page workbench that makes multi-account captcha/OTP recovery readable, actionable, and operationally safe.

The workbench remains inside the collection task page instead of introducing a new top-level page.

## Scope

This design covers only the collection-task owner flow:

- task-page pending verification overview
- per-item verification workbench entries
- shared verification dialog usage
- image readability improvements for full-page captcha screenshots
- backend verification-item projection for the collection page

## Non-Goals

Out of scope:

- creating a separate global verification center page
- automatic cropping or OCR for captchas
- browser-side manual completion mode
- changing the task execution model itself
- batch verification submission

## Current Problem

The current collection page already supports:

- paused task detection
- a minimal pending verification list
- shared verification dialog

But it still has practical gaps:

- verification items are only minimally projected from task rows
- task list and human-action queue are still mixed conceptually
- full-page captcha screenshots can be too small to read
- multi-account waiting items need better scanning and prioritization
- the page needs a clearer operator workflow for “what should I handle first?”

## Core Decision

The next version should remain an **enhanced panel inside the task page**, not a new standalone page.

Reasoning:

- the verification owner is still the collection task
- operators need immediate task context
- it is lower risk while other collection refactors are still active
- later extraction into a dedicated center remains possible if volume grows

## Approaches Considered

### Approach A: Task-page enhanced panel

Add a dedicated verification workbench panel above the task table.

Pros:

- lowest implementation risk
- keeps task context visible
- easiest for operators to understand

Cons:

- dense pages can become taller

### Approach B: Task-page drawer workbench

Keep the task page mostly unchanged and open a drawer containing pending verification items.

Pros:

- cleaner default page
- isolates operator work area

Cons:

- extra click before action
- lower visibility for urgent paused items

### Approach C: Separate verification center

Create a new page aggregating verification items across collection tasks.

Pros:

- best long-term separation of concerns

Cons:

- new route, permissions, aggregation, navigation, and state-sync cost
- unnecessary at the current maturity stage

## Recommendation

Use **Approach A** now.

Later, if pending verification volume becomes large or cross-page operations become necessary, evolve into Approach B or C.

## Backend Design

### 1. Task response contract

Collection task responses should expose stable verification fields:

- `verification_type`
- `verification_screenshot`
- `verification_id`
- `verification_message`
- `verification_expires_at`
- `verification_attempt_count`

This allows the task table and the workbench panel to consume the same source contract.

### 2. Verification item projection

Introduce a projection helper for paused verification tasks:

- `_build_task_verification_item(task)`

Each item should expose:

- `task_id`
- `account_id`
- `verification_id`
- `platform`
- `verification_type`
- `verification_message`
- `verification_screenshot`

The item identity must be at least:

**task + account + verification**

### 3. Aggregation endpoint

Preferred next step:

- `GET /collection/tasks/verification-items`

This endpoint should return only active operator work items instead of forcing the frontend to infer everything from the general task list.

Supported filters in the first version:

- `platform`
- `verification_type`
- `account_id`
- `status`

### 4. Resume semantics

Resume remains unchanged in principle:

- collection task stays the owner
- user submits captcha/OTP through task page dialog
- task transitions into `verification_submitted`
- executor continues on the same runtime context

## Frontend Design

### 1. Workbench layout

Inside `CollectionTasks.vue`, add three layers:

#### Summary strip

Show:

- total pending verification count
- graphical captcha count
- OTP count
- expired/failed count

#### Pending verification panel

Each item shows:

- platform
- task ID
- account
- store name if available
- verification type
- current phase/message
- created time
- expires time
- quick actions

#### Shared verification dialog

Continue using `VerificationResumeDialog.vue` for all collection verification handling.

### 2. Screenshot readability

This is a key usability requirement.

The dialog should support:

- thumbnail preview
- click-to-enlarge image preview
- fallback message when image loading fails

First version recommendation:

- keep the inline preview
- support original image preview using the existing image component / preview behavior
- do not attempt automatic screenshot cropping yet

### 3. Pending-item actions

Recommended actions:

- `立即回填`
- `查看截图`
- `跳到任务详情`
- `复制任务ID`

OTP items do not need image preview actions.

## Sorting and Prioritization

Default sort order:

1. unexpired items first
2. graphical captcha before OTP
3. older created items first

This gives operators a sane default without extra tuning.

## Failure Classification

The workbench should help distinguish at least:

- popup missing
- screenshot missing
- resume state wrong
- context restart
- error not visible
- multi-item collision

These categories align with the final verification acceptance checklist.

## Testing Strategy

### Backend

Add collection verification contract coverage for:

- task response verification fields
- verification item projection identity
- resume state transition to `verification_submitted`

### Frontend

Add smoke coverage for:

- task page uses shared verification dialog
- task page exposes pending verification items
- owner pages pass `message`, `expires-at`, and `error-message`
- shared dialog supports fallback and restoring hints

## Acceptance Criteria

The enhancement is complete when:

1. collection task page exposes a dedicated pending verification workbench panel
2. paused multi-account items are clearly separated
3. operators can open verification handling directly from the panel
4. graphical captcha screenshots are readable through preview/enlarge flow
5. collection task resume transitions still move to `verification_submitted`
6. frontend and backend contract coverage protect the workbench from regression

## Implementation Order

1. Add backend verification-item projection contract
2. Add or refine collection verification-items aggregation endpoint
3. Upgrade task page pending verification panel
4. Enhance shared dialog image readability for collection operators
5. Add regression coverage
