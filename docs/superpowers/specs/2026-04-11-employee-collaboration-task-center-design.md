# Employee Collaboration Task Center Design

**Date:** 2026-04-11
**Last Updated:** 2026-04-11

## Goal

Design a unified employee collaboration task center for daily operational work across the ERP so employees can receive, prioritize, execute, confirm, and close business tasks through one consistent workflow.

## Problem Statement

The repository already has:
- a system notification center for account and security events
- a generic persistent task center for long-running system jobs
- employee and user master data
- a placeholder `我的待办` page

What it does not have is a formal employee-facing collaboration model for daily business work such as:
- confirming replenishment orders
- confirming ad placement execution
- replying to customer requests and recording completion
- entering monthly cost data
- confirming performance scores

This gap currently causes four problems:

1. Daily work is scattered across business pages without a unified task inbox.
2. Existing notifications are message-oriented, not task-oriented.
3. There is no standard responsibility model for who owns a daily business action.
4. There is no shared completion-proof model for operational tasks.

## Scope

This design covers:
- employee-facing task center product shape
- task domain model
- task state model
- automatic task generation sources
- notification and reminder strategy
- integration boundaries with existing notification center, task center, and business modules

This design does not cover:
- a full implementation plan
- all module-specific task templates in the first release
- email / SMS / enterprise chat delivery in v1
- replacing the existing system long-task center used for data sync, collection, or cloud sync

## Product Positioning

The new capability should be positioned as an **employee collaboration task center**, not as:
- only an approval system
- only a notification center
- only a general-purpose text todo tool

It is a business execution layer that sits between system events and business processing pages.

Core principle:
- task is the source of truth for work
- notification is only a reminder shell around the task
- business modules remain the source of truth for domain data

## Recommended Architecture

The collaboration flow should be split into three layers.

### 1. Task Layer

The task layer owns:
- task identity
- task category and type
- owner and participants
- due time and priority
- state transitions
- completion proof
- operation timeline

This layer is the canonical control plane for employee collaboration work.

### 2. Notification Layer

The notification layer owns:
- new task reminders
- due-soon reminders
- overdue reminders
- returned / rejected reminders
- manual nudge reminders

It should not own business completion logic. Clicking a notification should always lead back to a task or task-linked business page.

### 3. Business Processing Layer

The business module remains where actual work is performed:
- replenishment pages
- ad placement pages
- customer service pages
- monthly cost entry pages
- performance confirmation pages

Employees should usually process a task in the business page, not inside a giant task-center-only form.

## User Experience Shape

The first release should use a **global unified entry + module-specific execution** model.

This means:
- employees enter through a unified `我的任务` view
- they prioritize work from one place
- each task links back to the correct business page for processing
- the business page writes completion results back to the task center

This avoids two bad outcomes:
- a disconnected inbox with no business context
- many isolated per-module pseudo-task systems

## Page Structure

The first release should provide five core surfaces.

### 1. 我的任务

Primary inbox for the current employee.

Responsibilities:
- show tasks due today
- show upcoming tasks
- show overdue tasks
- support filtering by status, priority, module, and category
- support views for owner / collaborator / CC

### 2. 我发起的

Shows tasks initiated or assigned by the current user.

Responsibilities:
- progress tracking
- reminder / nudge actions
- seeing whether work is stalled

### 3. 抄送我的

Shows awareness-only tasks without mixing them into the primary execution queue.

Responsibilities:
- visibility
- comments / context
- no owner-level completion rights

### 4. 任务详情

Shows:
- task summary
- linked business object
- responsibility model
- due time and priority
- required completion inputs
- history timeline
- completion proof and outcome

### 5. Business Page Quick Processing Entry

Business pages should support task-linked execution:
- open from task
- show current task context
- submit processing result back to task center

## Responsibility Model

Each task should have exactly one primary owner.

Supported participant roles in v1:
- one `主责任人`
- zero or more `协作人`
- zero or more `抄送人`

Rules:
- only one primary owner is allowed
- only the primary owner can submit the main completion result
- collaborators can provide supporting input
- CC users can read and comment but do not complete the task

This keeps responsibility clear and avoids “everyone saw it, nobody owned it.”

## Task Categories

All first-release tasks should map into four categories.

### 1. 执行类

Examples:
- ad placement completed
- customer reply completed
- monthly cost entered

### 2. 确认类

Examples:
- replenishment order confirmed
- performance score confirmed
- anomaly record confirmed

### 3. 审批类

Examples:
- leave approval
- expense approval
- profile-change approval

### 4. 提醒类

Examples:
- monthly deadline reminder
- overdue reminder
- recheck reminder

This keeps the system flexible without turning every business event into its own workflow engine.

## Task State Model

The first release should use a simplified shared state vocabulary:

- `待处理`
- `进行中`
- `待确认`
- `已完成`
- `已驳回`
- `已关闭`

Recommended semantics:

### 待处理

Task has been assigned but not started.

### 进行中

Primary owner has started work.

### 待确认

Owner submitted a result and is waiting for business confirmation, approval, or validation.

### 已完成

Task is fully closed successfully.

### 已驳回

Submitted result was rejected and needs correction or supplementation.

### 已关闭

Task no longer needs execution because it was cancelled, replaced, or invalidated.

## State Transition Rules

Recommended v1 rules:

- new task -> `待处理`
- owner starts processing -> `进行中`
- result submission requiring review -> `待确认`
- accepted result -> `已完成`
- rejected result -> `已驳回`
- cancelled / no longer required -> `已关闭`

Permissions:
- primary owner can move work into `进行中` and submit result
- initiator, supervisor, or module rules can confirm / reject / close
- CC users cannot change task state by default

## Completion Proof Model

Completion proof should be layered, not one-size-fits-all.

### 1. Basic Proof

Default for most tasks:
- completion comment
- completion time
- actor

### 2. Structured Proof

For operational tasks with real outputs:
- numeric values
- selected outcome
- linked order number
- linked business record ID

Examples:
- replenishment confirmation -> order number, confirm result
- ad placement -> channel, placed time
- monthly cost entry -> month, amount, source
- performance confirmation -> score, confirmation comment

### 3. Attachment Proof

For tasks that truly require evidence:
- screenshot
- image
- file

This should be optional per task type, not globally required.

### 4. Review Outcome

For approval / confirmation workflows:
- approve
- reject
- return for supplement
- reason

## Task Data Model

The collaboration domain should use a dedicated employee-facing task model rather than directly overloading the existing system long-task center.

Suggested core fields:

- `task_id`
- `task_type`
- `task_category`
- `title`
- `description`
- `status`
- `priority`
- `owner_user_id`
- `cc_user_ids`
- `collaborator_user_ids`
- `source_type`
- `source_module`
- `source_record_type`
- `source_record_id`
- `due_at`
- `started_at`
- `completed_at`
- `closed_at`
- `completion_schema`
- `completion_payload`
- `result_status`
- `result_comment`
- `created_by`
- `created_at`
- `updated_at`

Recommended supporting tables:
- task operation timeline / logs
- participant mappings if not stored in JSON
- task template / rule definitions for automatic creation

## Automatic Task Sources

The first release should only integrate sources that are standardizable and business-critical.

### 1. Business Document Confirmation

Examples:
- replenishment order confirmation
- missing required form fields
- business record completion requests

Characteristics:
- clear business object
- clear owner
- clear confirm action

### 2. Execution Result Backfill

Examples:
- ad placement confirmation
- customer response registration
- campaign result backfill

Characteristics:
- operational action already happened
- system needs structured proof or confirmation

### 3. Data Anomaly Handling

Examples:
- missing fields
- abnormal values
- import failures
- reconciliation differences

Characteristics:
- system-generated
- must be assigned to a clear owner
- should usually deep-link into a repair page

### 4. Periodic Operating Actions

Examples:
- monthly cost entry
- monthly performance confirmation
- scheduled review work

Characteristics:
- generated on a schedule
- deadline-driven
- repeated across periods, stores, or employees

## Automatic Task Creation Rules

A business event should only become a task if it has:
- a clear owner
- a clear business object
- a clear completion action
- a meaningful deadline or SLA

Do not turn every message or every low-level log into a task.

Events that should stay as notifications only:
- generic informational alerts
- low-value noisy logs
- events without an accountable owner
- events without a concrete completion action

## Notification Strategy

Task is the main object. Notification is a reminder shell around task state.

The first release should support five reminder triggers:

### 1. New Assignment

When:
- task is created and assigned

Recipient:
- primary owner

### 2. Due Soon

When:
- task is approaching deadline

Recipient:
- primary owner

### 3. Overdue

When:
- task passes deadline without completion

Recipient:
- primary owner
- optionally initiator or supervisor in later rollout

### 4. Returned / Rejected

When:
- submitted result is rejected or returned

Recipient:
- current owner

### 5. Nudge / Reminder

When:
- initiator actively nudges task

Recipient:
- primary owner

## Notification Integration

The new task system should reuse the existing notification center for delivery.

Recommended new notification types:
- `task_assigned`
- `task_due_soon`
- `task_overdue`
- `task_returned`
- `task_nudged`

Notification payload should include at least:
- `task_id`
- `task_type`
- `source_module`
- `source_record_id`
- `target_route`

Click behavior:
- always route to task detail or directly into the linked business page with task context

## Reuse Boundaries

### Reuse As-Is

- existing notification storage and read surfaces
- existing notification WebSocket delivery
- existing user notification preferences page pattern
- existing `DimUser` and `Employee.user_id` relationship for assignment

### Reuse As Reference, Not As Final Collaboration Model

The existing persistent system task center should be treated as a design reference, not the final employee collaboration domain model.

Reason:
- it is optimized for data sync, collection, cloud sync, and system long-running jobs
- it does not yet carry employee collaboration semantics such as owner, CC, completion proof, or task review outcome

### New Collaboration Domain Needed

The employee collaboration task center should introduce:
- dedicated collaboration task tables or equivalent domain objects
- task proof schema
- task reminder rules
- business-object linking for employee workflows

## Recommended First Release Scope

Do not launch with all possible task sources.

Recommended v1 rollout:

1. Build the shared collaboration task domain
2. Replace the placeholder `我的待办` page with a real inbox
3. Integrate 2-3 high-value task sources first
4. Add task-based notifications
5. Add task-context entry and completion callbacks inside selected business pages

Recommended first source set:
- monthly cost entry
- performance score confirmation
- replenishment confirmation

These are frequent, structured, and easy to reason about operationally.

## Current Implementation Note

The first implementation pass now has:
- collaboration task tables, service, API, and notifications
- a real `我的任务` page and task detail page
- backend source synchronization for:
  - monthly cost entry
  - performance confirmation
- task-detail links into corresponding business pages

The following items remain intentionally incomplete:
- business-page task writeback in the existing finance and performance public pages
- hard enforcement of one supervisor per `year_month + platform_code + shop_id`
- true replenishment automation

Replenishment should still be treated as a bridge source until the procurement runtime is production-ready.

## Out Of Scope For V1

- full email / SMS / enterprise-chat delivery
- user-defined reminder workflows
- every system message becoming a task
- building heavy business forms entirely inside the task center
- replacing the existing generic task center used by system jobs
- attachment-heavy mandatory evidence on every task

## Risks

### 1. Building a second disconnected inbox

If task center cannot deep-link cleanly into business pages, employees will ignore it.

Mitigation:
- task center must be summary and coordination first
- business pages remain processing surfaces

### 2. Over-modeling approvals and under-modeling execution

If the system is designed like an approval engine only, daily operational tasks will not fit.

Mitigation:
- execution tasks are the main design center
- approval tasks are only one task category

### 3. Noisy auto-generated tasks

If every alert becomes a task, users will stop trusting the queue.

Mitigation:
- strict entry rules for auto-task creation
- only high-value sources in v1

### 4. Responsibility ambiguity

If multiple people can “own” one task, nobody truly owns it.

Mitigation:
- exactly one primary owner

### 5. Excessive completion friction

If every task requires files and long forms, employees will game the system or delay completion.

Mitigation:
- layered proof model
- task-type-specific completion requirements

## Recommended Outcome

The repository should evolve toward:
- one employee-facing collaboration task center for daily business work
- one notification system reused for reminders
- business modules as the execution surfaces
- structured proof and timeline records for operational accountability

This fills the current gap between:
- message-like account notifications
- system-oriented long-task tracking
- and real employee day-to-day business execution.
