# Employee Task Center Runbook

## Purpose

This runbook explains how the first version of the employee collaboration task center operates, which task sources are active, and where the current implementation still uses bridge behavior.

## Current Scope

The current implementation covers:
- employee task domain tables
- backend service and API
- task notifications through the existing notification center
- frontend inbox and task detail page
- automatic task source helpers for:
  - monthly cost entry
  - performance confirmation

The current implementation does not yet fully cover:
- business-page task-context writeback in the finance and performance public pages
- procurement / replenishment automatic task generation
- system-level uniqueness enforcement for shop supervisor assignments

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
- sync is best-effort and must not roll back performance calculation

Known limitation:
- the employee-facing public page still needs a safe task writeback integration step

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
- a formal system-level guard in `hr_commission.py` is still pending because that file contains historical encoding/string corruption risk and should be cleaned carefully before behavioral edits

Operational guidance until the guard lands:
- keep one `supervisor` per `year_month + platform_code + shop_id`
- avoid assigning multiple supervisors to the same shop-month combination

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
1. clean historical string/encoding damage in the finance and performance public pages
2. add task-context-aware business-page writeback
3. add formal unique-supervisor enforcement in the shop assignment router
4. add procurement bridge messaging until replenishment runtime is ready
