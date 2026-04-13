# Approval Center Unified Design

**Date:** 2026-04-13
**Last Updated:** 2026-04-13

## Goal

Design a unified approval center that can coexist cleanly with the existing employee task center, so the product no longer mixes a usable task inbox with unfinished approval pages and can evolve into a consistent approval experience without creating duplicate "待办" entry points.

## Problem Statement

The repository now has:
- a usable employee task center (`我的待办`, task detail, task notifications)
- several existing approval-capable backend flows spread across business modules
- three approval-center frontend placeholder pages:
  - `我的申请`
  - `审批历史`
  - `流程配置`

This creates a product-structure problem:
- users see an "审批中心" menu group
- only `我的待办` is actually usable
- approval behavior exists in backend modules, but is not unified into one front-end approval center

If this is left as-is, later approval work will become harder because:
- users will already have formed incorrect mental models
- task and approval concepts will keep getting conflated
- information architecture will drift further from actual runtime behavior

## Scope

This design covers:
- approval-center product structure
- relationship between approval center and task center
- first-wave approval types to unify
- approval domain model
- status model
- approval-to-task projection model
- page structure for `我的申请`, `审批历史`, and `流程配置`

This design does not cover:
- a full BPM engine
- a graphical workflow editor
- parallel multi-approver / countersign orchestration
- implementation details for every future approval template

## Recommended Product Direction

The approval center should be designed as a **separate business domain** that reuses the **existing task center as the unified pending-work entry point**.

That means:
- there should be only one user-facing `我的待办`
- approval work should still surface in that unified pending queue
- approval center should own:
  - `我的申请`
  - `审批历史`
  - `流程配置`

This avoids the worst product outcome:
- one "待办" in task center
- another "待办" in approval center

## Recommendation Summary

Use a **unified pending queue + separate approval domain** model.

### Keep in Task Center

- `我的待办`

This remains the single work inbox for:
- execution tasks
- confirmation tasks
- approval tasks
- reminder tasks

### Put in Approval Center

- `我的申请`
- `审批历史`
- `流程配置`

This makes approval center the place for:
- initiating approvals
- reviewing approval history
- managing approval templates / step rules

## Why Not Build A Full Workflow Engine First

The repository already has real approval behavior, but not a unified product surface.

The most pragmatic step now is not to build a heavy workflow engine, but to define a **unified approval-center model** with:
- approval templates
- approval instances
- approval steps
- approval action logs
- approval-task projection

This is enough to unify current approval flows without prematurely building:
- complex branch logic
- graphical editors
- generic BPM runtime semantics

## First-Wave Approval Types

Recommended first-wave unified approvals:

1. `user_registration_approval`
2. `leave_request_approval`
3. `overtime_request_approval`
4. `monthly_profit_settlement_approval`
5. `follow_investment_settlement_approval`

These are recommended because they already map closely to existing backend behavior and are structurally approval-shaped:
- clear applicant
- clear approver
- clear approve / reject outcome
- clear audit value

## Current Implementation Status

This design is now partially implemented on `main`.

Implemented and available:
- unified approval-center backend domain
- approval-center API
- approval-center frontend pages:
  - `我的申请`
  - `审批历史`
  - `流程配置` (read-only)
- approval-center permission controls
- first-wave integrations completed for:
  - `user_registration_approval`
  - `monthly_profit_settlement_approval`
  - `follow_investment_settlement_approval`

Still deferred:
- `leave_request_approval`
- `overtime_request_approval`
- editable workflow configuration
- richer approval detail page and broader approval-template administration

## What Should Stay In Task Center, Not Approval Center

These should remain task / confirmation domain work, not first-wave approval templates:
- monthly cost entry
- performance confirmation
- replenishment confirmation
- ad placement confirmation
- customer reply confirmation

Reason:
- these are not primarily approval-originated requests
- they are execution or confirmation flows first

## Domain Model

The approval center should introduce five core objects.

### 1. Approval Template

Defines a reusable approval type.

Suggested fields:
- `template_code`
- `template_name`
- `business_type`
- `enabled`
- `target_route`
- `form_schema`
- `approval_mode`

### 2. Approval Instance

Represents one concrete approval request.

Suggested fields:
- `approval_id`
- `template_code`
- `applicant_user_id`
- `business_key`
- `status`
- `current_step`
- `submitted_at`
- `finished_at`

### 3. Approval Step

Represents the current and historical steps of an approval instance.

Suggested fields:
- `step_id`
- `approval_id`
- `step_order`
- `approver_type`
- `approver_user_id`
- `status`
- `acted_at`

### 4. Approval Action Log

Records all approval actions for audit and history.

Suggested fields:
- `action_id`
- `approval_id`
- `step_id`
- `actor_user_id`
- `action_type`
- `comment`
- `created_at`

### 5. Approval Task Projection

This is not necessarily a separate top-level table if the current task center can represent it as a normal task row.

Purpose:
- project the current pending approval step into the unified pending queue

## Approval And Task Relationship

This is the core architectural rule:

- approval center owns the **approval instance**
- task center owns the **pending work entry**
- a pending approval step becomes one projected task in the task center

Recommended linkage shape:
- `employee_task.source_module = approval-center`
- `employee_task.source_record_type = approval_instance`
- `employee_task.source_record_id = approval_id`

So:
- the task is the inbox item
- the approval instance is the source of truth

## Status Model

### Approval Instance Status

- `draft`
- `submitted`
- `in_review`
- `approved`
- `rejected`
- `cancelled`

### Approval Step Status

- `pending`
- `approved`
- `rejected`
- `skipped`

### Task Projection Status

Reuse existing task-center status model:
- `pending`
- `in_progress`
- `pending_confirmation`
- `completed`
- `rejected`
- `closed`

## Flow Model

### Submission Flow

1. Applicant creates approval instance
2. Instance becomes `submitted`
3. First approval step becomes `pending`
4. A projected task is created in the unified pending queue

### Approval Action Flow

1. Approver opens approval work from `我的待办`
2. Approver approves or rejects
3. Action is recorded in approval action log

### Multi-Step Sequential Flow

If additional steps exist:
- current step becomes `approved`
- next step becomes `pending`
- old task closes
- new pending task is projected to the next approver

### Terminal Flow

If workflow ends:
- instance becomes `approved` or `rejected`
- last pending task closes
- business result is written back to the source object

### Applicant Withdrawal

If the applicant withdraws before review has meaningfully advanced:
- instance becomes `cancelled`
- pending steps are closed
- projected task closes

## First-Version Approval Modes

Recommended supported modes for v1:

1. single approver
2. multi-step sequential approval
3. approver resolution by:
  - direct manager
  - administrator
  - finance
  - explicitly assigned user

Not recommended for v1:
- countersign / parallel approval
- arbitrary branching
- graphical flow editing
- deeply configurable workflow expressions

## Approval Center Page Structure

### 1. 我的申请

Purpose:
- view approval requests initiated by the current user
- track current step and final outcome
- withdraw where allowed

Suggested list fields:
- title
- template type
- current status
- current approver / current step
- submitted time

### 2. 审批历史

Purpose:
- view approval requests already acted on by the current user
- inspect action history and final results

Suggested list fields:
- title
- applicant
- action I took
- final result
- action time

### 3. 流程配置

Purpose:
- allow administrators to configure approval templates

First-version scope:
- list templates
- enable / disable templates
- define sequential steps
- define approver rules
- define target route and basic form schema

### 4. Approval Detail Page

Recommended even if not directly exposed as a menu item.

Should show:
- approval instance basics
- submitted form content
- status
- current step and remaining steps
- action timeline
- action panel

## User Journey

Recommended user journey:

### Applicant

1. Open `我的申请`
2. Submit approval
3. Track progress there
4. See final result there

### Approver

1. See pending approval in unified `我的待办`
2. Open task
3. Enter approval detail
4. Approve / reject

### Administrator

1. Manage templates in `流程配置`
2. Review completed work in `审批历史`

## Alternative Approaches Considered

### Option 1: Fully Separate Approval Inbox

Add a second `我的待办` inside approval center.

Why not recommended:
- duplicate inboxes
- user confusion
- inconsistent prioritization

### Option 2: Full Workflow Engine First

Build general workflow runtime before product unification.

Why not recommended:
- too much scope for current repository maturity
- delays alignment of already-existing approval behavior

### Option 3: Unified Pending Queue + Separate Approval Domain

Recommended.

Why:
- aligns with current task center investment
- keeps approval semantics complete
- avoids duplicate work queues

## Recommended Outcome

The repository should move toward:
- one unified pending queue for all actionable work
- one dedicated approval domain for approval-specific lifecycle and configuration
- one approval center with:
  - `我的申请`
  - `审批历史`
  - `流程配置`

This avoids current product confusion while giving the team a realistic path to unify existing approval capabilities without prematurely building a heavyweight workflow platform.
