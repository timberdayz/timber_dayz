# Employee Task Center Runbook

## Purpose

This runbook explains how the first version of the employee collaboration task center operates, which task sources are active, and where the current implementation still uses bridge behavior.

## Current Scope

The current implementation covers:
- employee task domain tables
- backend service and API
- task notifications through the existing notification center
- frontend inbox and task detail page
- phase 2 action policies for:
  - collaborator supplement
  - initiator close / cancel request
  - admin reassign / takeover / force close
- automatic task source helpers for:
  - monthly cost entry
  - performance confirmation
- business-page task-context writeback in:
  - expense management
  - performance public display
- system-level uniqueness enforcement for one supervisor per shop-month assignment

The current implementation does not yet fully cover:
- procurement / replenishment automatic task generation
- task statistics / management dashboards
- configurable reminder timing and escalation rules

## Task Categories

The task center uses four conceptual categories:
- execution
- confirmation
- approval
- reminder

The currently active task types are:
- `monthly_cost_entry`
- `performance_confirmation`

## State Model

Current backend state values:
- `pending`
- `in_progress`
- `pending_confirmation`
- `completed`
- `rejected`
- `closed`

Operational meaning:
- `pending`: assigned but not started
- `in_progress`: owner has started processing
- `pending_confirmation`: owner submitted result and is waiting for review
- `completed`: task is fully closed successfully
- `rejected`: result was returned or disputed
- `closed`: task no longer needs action

## Notifications

The task center reuses the existing notification infrastructure.

Current task notification types:
- `task_assigned`
- `task_due_soon`
- `task_overdue`
- `task_returned`
- `task_nudged`

The current implementation guarantees:
- notification schema support
- notification label support
- notification helper support for `task_assigned`
- notification click routing from task detail into linked business pages

## Active Automatic Sources

### 1. Monthly Cost Entry

Source module:
- `expense-management`

Task type:
- `monthly_cost_entry`

Owner resolution:
- resolve `year_month + platform_code + shop_id`
- find the unique `supervisor` row in `a_class.employee_shop_assignments`
- map `employee_code -> employees.user_id`

Current runtime behavior:
- after expense save succeeds, backend attempts to sync a monthly cost task
- the expense page can receive task context and submit a task result back after the matching month/shop save
- task sync is best-effort and must not roll back the expense save path

Known limitation:
- if the shop cannot be mapped to a platform code or if the supervisor relation is missing, task sync is skipped and logged

### 2. Performance Confirmation

Source module:
- `performance-management`

Task type:
- `performance_confirmation`

Owner resolution:
- map `employee_code -> employees.user_id`

Current runtime behavior:
- after performance calculation succeeds, backend attempts to sync one confirmation task per employee in the calculated month
- the public performance page can receive task context and let the employee confirm or dispute from that page
- sync is best-effort and must not roll back performance calculation

## Procurement / Replenishment Bridge

Replenishment is not yet a real automatic source.

Reason:
- the current procurement page is still an under-development placeholder
- there is no mature purchase-order runtime to safely attach automatic employee task generation

Current expectation:
- replenishment remains a bridge source in v1
- the product direction is still to route future replenishment confirmation tasks through the employee task center
- do not claim replenishment automation is live yet

## Shop Supervisor Rule

Business rule agreed for v1:
- one shop should have exactly one supervisor responsible for a given month

Current implementation status:
- the source helper assumes this uniqueness when resolving monthly cost task owners
- the shop assignment router now rejects duplicate `supervisor` rows for the same `year_month + platform_code + shop_id`

## Validation Commands

Current verified backend task suite:

```powershell
python -m pytest backend/tests/test_employee_task_schema.py backend/tests/test_employee_task_service.py backend/tests/test_employee_task_routes.py backend/tests/test_employee_task_notifications.py backend/tests/test_employee_task_sources.py -q
```

Current verified frontend checks:

```powershell
node --test frontend/scripts/employeeTaskRoutes.test.mjs frontend/scripts/employeeTaskUi.test.mjs
npm -C frontend run type-check
```

## Next Implementation Steps

Recommended next work order:
1. add richer task-detail forms for phase 2 actions
2. expand task sources beyond cost entry and performance confirmation
3. add task statistics / management dashboards
4. add procurement bridge messaging until replenishment runtime is ready
