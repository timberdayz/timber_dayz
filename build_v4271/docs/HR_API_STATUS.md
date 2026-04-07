# HR API Status

**Updated**: 2026-04-04  
**Status**: HR income and payroll chain is implemented and operational

## Current Summary

The HR domain is no longer in the earlier “performance only, employee/attendance pending” state.

The following runtime capabilities are available in the repository today:

- Employee profile and “my profile” APIs
- My Income API using payroll as the final source of truth
- Payroll record query and draft editing
- Payroll state transitions:
  - `confirm`
  - `reopen`
  - `pay`
- Performance recalculation
- Employee commission and employee performance recalculation
- Payroll generation from salary structure + commission + performance

## Implemented Areas

### 1. Performance management

- Router: `backend/routers/performance_management.py`
- Main route: `POST /performance/scores/calculate`
- Status: implemented

Capabilities:

- performance config read/write
- shop performance score calculation
- employee commission recalculation
- employee performance recalculation
- payroll draft generation/update
- locked payroll conflict count and detail return

### 2. Employee profile and My Income

- Router: `backend/routers/hr_employee.py`
- Main routes:
  - `GET /api/hr/me/profile`
  - `PUT /api/hr/me/profile`
  - `GET /api/hr/me/income`
- Status: implemented

Capabilities:

- current user to employee linkage
- employee self-profile update
- payroll-based My Income display
- access audit logging for My Income

### 3. Payroll management

- Router: `backend/routers/hr_salary.py`
- Main routes:
  - `GET /api/hr/payroll-records`
  - `GET /api/hr/payroll-records/{employee_code}/{year_month}`
  - `PUT /api/hr/payroll-records/{record_id}`
  - `POST /api/hr/payroll-records/{record_id}/confirm`
  - `POST /api/hr/payroll-records/{record_id}/reopen`
  - `POST /api/hr/payroll-records/{record_id}/pay`
- Status: implemented

Capabilities:

- payroll list and detail query
- manual-field editing on `draft` payroll
- `draft -> confirmed`
- `confirmed -> draft`
- `confirmed -> paid`
- admin-only authorization on `pay`
- audit logging on successful `pay`

### 4. Salary structures

- Router: `backend/routers/hr_salary.py`
- Main routes:
  - `GET /api/hr/salary-structures`
  - `GET /api/hr/salary-structures/{employee_code}`
  - `POST /api/hr/salary-structures`
- Status: implemented

## Frontend Status

### Implemented pages

- `frontend/src/views/HumanResources.vue`
  - payroll list
  - draft edit
  - confirm / reopen / pay actions
  - payroll runbook entry
- `frontend/src/views/hr/MyIncome.vue`
  - payroll-only income view
  - full payroll breakdown
  - payroll runbook entry
- `frontend/src/views/hr/PerformanceManagement.vue`
  - monthly recalculation trigger
  - payroll locked-conflict dialog

### Help and operations docs

- `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
- `frontend/src/views/help/UserGuide.vue`
  - contains `hr-payroll` guide section

## Remaining Expansion Items

These are not missing base APIs; they are later-stage enhancements:

- external payment / finance system linkage after `paid`
- finer-grained payroll permission model beyond admin-only `pay`
- dedicated payroll conflict list page
- richer payroll operation dashboards / metrics

## Recommended Reference Docs

- `docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md`
- `docs/superpowers/specs/2026-04-03-hr-income-payroll-closure-design.md`
- `docs/superpowers/specs/2026-04-04-hr-income-payroll-end-to-end.md`
