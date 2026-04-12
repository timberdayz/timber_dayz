# Employee Task Center Phase 2 Enhancements Design

**Date:** 2026-04-12
**Last Updated:** 2026-04-12

## Goal

Design the second phase of the employee collaboration task center so it can operate safely at scale with clearer participant behavior, stronger administrative controls, and explicit permission alignment between task types and business pages.

## Background

The first phase already established:
- employee task domain tables
- task API and notification integration
- `我的任务` and task detail pages
- automatic task generation for monthly cost entry and performance confirmation
- task detail links into business pages

That first phase is enough to make employee tasks usable, but not enough to make the system operationally robust for long-term use.

Current weak spots:
- collaborators are visible but not behaviorally differentiated
- initiators have no controlled cancellation model
- admins cannot safely recover or reroute stuck tasks
- task assignment does not yet formally validate target business-page permission compatibility
- action permissions are still mostly implicit rather than task-type-driven

## Scope

This phase covers:
- collaborator action policy
- initiator cancellation / close policy
- administrator reassignment / takeover policy
- task-type to business-page permission mapping
- task-type-specific action strategy model

This phase does not cover:
- new task sources
- email / SMS / enterprise-chat delivery
- replacing the current task state model
- redesigning the first-phase data model from scratch

## Design Principles

### 1. Keep One Primary Owner

Each task still has exactly one primary owner.

This phase adds richer supporting behavior around that owner, but does not weaken ownership clarity.

### 2. Differentiate Visibility From Authority

Not everyone who can see a task should be allowed to complete it.

The system must distinguish:
- visibility
- collaboration
- review
- forced administration

### 3. Make Task Operations Explicit

Task actions should no longer be inferred ad hoc from route or role alone.

The system should define:
- which actions exist
- which participant types may execute them
- which task types allow them

### 4. Validate Permission Compatibility Early

Before a task is assigned, the system should know whether the assignee can actually open and use the target business page.

## Enhancement 1: Collaborator Supplement Workflow

### Problem

Collaborators already exist in the phase-1 model, but they do not yet have a clear action boundary.

Without explicit boundaries, one of two bad outcomes happens:
- collaborators become useless read-only copies
- collaborators gain too much power and blur accountability

### Recommendation

Allow collaborators to supplement a task, but do not let them formally submit the task result.

### Collaborator Allowed Actions

- add comment
- add evidence
- add structured supporting data

### Collaborator Disallowed Actions

- start task
- submit final result
- confirm result
- reject result
- close task

### Data Model Impact

No new top-level state is required.

Add task timeline actions such as:
- `append_comment`
- `append_evidence`
- `append_structured_data`

Optional future addition:
- a small structured `supplement_payload` block for collaborator-only data

### UX Impact

Task detail page should show collaborator actions as “补充材料” rather than “提交结果”.

### Recommendation

This enhancement should be implemented in phase 2.

## Enhancement 2: Initiator Cancellation And Close Policy

### Problem

The initiator currently lacks a controlled mechanism to retract or cancel a task that was issued by mistake or became irrelevant.

### Recommendation

Allow initiators to directly close tasks only before work begins.

For work that has already started, initiators should be able to request cancellation, but not unilaterally terminate it.

### Rules

Initiator may directly close:
- `pending` tasks

Initiator may not directly close:
- `in_progress`
- `pending_confirmation`
- `completed`

For started tasks:
- initiator may issue `request_cancel`
- admin or designated reviewer decides whether to close

### Data / Timeline Impact

Suggested new task actions:
- `close_unstarted_task`
- `request_cancel`

Optional future field:
- `cancellation_reason`

### Recommendation

This enhancement should be implemented early in phase 2 because it reduces operational friction quickly.

## Enhancement 3: Administrator Reassignment, Takeover, And Force Close

### Problem

Production task systems inevitably hit stuck states:
- wrong assignee
- assignee unavailable
- role change
- employee offboarding
- urgent rerouting

Without administrative intervention tools, tasks become operational dead weight.

### Recommendation

Administrators should be allowed to:
- reassign a task
- take over a task
- force close a task
- add or remove collaborators / CC users

### Required Constraints

Every forced action must record:
- actor
- previous assignment or status
- new assignment or status
- reason

### Suggested Actions

- `reassign_task`
- `takeover_task`
- `force_close_task`
- `add_participant`
- `remove_participant`

### Recommendation

This is the highest-priority phase-2 enhancement because it is required for safe operation.

## Enhancement 4: Task Type To Business Page Permission Mapping

### Problem

A task may be assigned to a user who lacks permission for the target page.

The first phase works mainly because the initial task types were chosen carefully, but this does not scale safely.

### Recommendation

Introduce an explicit mapping layer:

- `task_type -> target_route`
- `task_type -> required_permission`
- `task_type -> allowed_roles`

### Example Mapping

`monthly_cost_entry`
- target route: `/expense-management`
- required permission: `expense-management`
- allowed roles: `admin`, `manager`, `finance`

`performance_confirmation`
- target route: `/hr-performance-display`
- required permission: `performance:read`
- allowed roles: `admin`, `manager`, `operator`, `finance`

### Runtime Use

This mapping should be used in two places:

1. Assignment-time validation
   - do not assign a task to a user who cannot open the business page

2. Task-detail deep-link generation
   - centralize route generation instead of scattering it across UI components

### Recommendation

This should be implemented in phase 2 after admin controls and before many new task types are added.

## Enhancement 5: Task-Type-Specific Action Strategy

### Problem

Different task types should not all behave the same way:
- execution tasks
- confirmation tasks
- approval tasks
- reminder tasks

If action rules remain implicit and hardcoded, the task center will become fragile as more sources are added.

### Recommendation

Define action strategy per task type.

Suggested strategy dimensions:
- allowed actions
- participant action matrix
- completion mode
- review mode
- target route
- required permission

### Example

#### Execution Task

Primary owner:
- start
- submit result

Collaborator:
- append evidence
- append comment

Initiator:
- close if not started
- request cancellation if started

Admin:
- reassign
- take over
- force close

#### Confirmation Task

Primary owner:
- confirm
- dispute

Reviewer / admin:
- accept
- reject

#### Approval Task

Approver:
- approve
- reject

Requester:
- cancel before approval starts

### Data Model Direction

This does not require immediate table redesign.

It can begin as code-level task-type strategy config, then become persisted config later if needed.

## Recommended Implementation Order

### Phase 2A

1. Administrator reassignment / takeover / force close
2. Initiator close-before-started and cancellation request

### Phase 2B

3. Collaborator supplement actions
4. Task-type to business-page permission mapping

### Phase 2C

5. Task-type-specific action strategy configuration

This order prioritizes operational safety first, then collaboration quality, then platform extensibility.

## Risks

### 1. Over-complicating Phase 2

If every enhancement is implemented at once, the task center may become harder to stabilize.

Mitigation:
- phase the rollout

### 2. Hidden Permission Mismatches

Task assignment without explicit permission mapping can create silent dead-end tasks.

Mitigation:
- add assignment-time validation

### 3. Responsibility Drift

If collaborator or admin actions are too broad, ownership clarity will degrade.

Mitigation:
- keep the primary owner model strict
- force timeline audit on privileged actions

## Recommended Outcome

After phase 2, the employee task center should evolve from a usable task inbox into an operationally safe task platform with:
- stronger participant semantics
- recoverable task administration
- predictable assignment validity
- structured action rules by task type

This creates a solid base for future task-source expansion such as replenishment, customer reply confirmation, ad placement confirmation, and anomaly handling.
