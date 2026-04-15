# Labor Efficiency Employee Identity Design

## Goal

Correct the labor-efficiency denominator so XiHong ERP counts only real active employees, while excluding non-employee login users such as visitors and investors.

This design also closes the current mismatch between:

- the legacy business definition of labor efficiency
- the HR employee archive model
- the PostgreSQL dashboard runtime chain

## Business Definition

Labor efficiency should mean:

- `labor_efficiency = period GMV / active counted employees`

For this repository, "counted employees" must mean:

- real employees
- active in HR
- explicitly included in labor-efficiency counting

The following identities must not be counted:

- visitor
- investor
- external contractor
- part-time worker

At present, the user confirmed:

- visitors do not count
- investors do not count
- contractors and part-time workers do not have login accounts or permissions and should also not count

## Current State

The current repository has three related but different identity systems:

### System Login Identity

- table: `core.dim_users`
- used for authentication, roles, sessions, and permissions

### HR Employee Identity

- table: `a_class.employees`
- used for employee archive data
- currently linked to login users through `employees.user_id -> dim_users.user_id`

### Platform Business Accounts

- tables: `core.main_accounts`, `core.shop_accounts`, `core.shop_account_aliases`
- used for platform login, collection runtime, shop ownership, and raw-data alignment

These systems should not be conflated.

## Current Problem

### Legacy KPI Logic

The legacy business-overview KPI SQL defines labor efficiency as:

- `GMV / COUNT(active employees)`

with employee count sourced from:

- `a_class.employees`
- `status = 'active'`

This means the denominator currently depends only on employee archive status.

### PostgreSQL Dashboard Runtime Gap

The new PostgreSQL dashboard chain currently does not compute labor efficiency correctly:

- the API module does not expose employee count
- the dashboard aggregation service returns `labor_efficiency = 0`

So there are two problems:

1. the denominator definition is too broad in the legacy logic
2. the new runtime chain does not yet implement the metric correctly

### Auto-Creation Risk

`/api/hr/me/profile` currently auto-creates a minimal employee archive for a logged-in user who has no employee record yet.

That behavior is risky because a non-employee user could end up with:

- an employee archive row
- `status = 'active'`

which would incorrectly pollute labor-efficiency counting if the denominator is based only on employee status.

## Design Principles

### Principle 1: HR Identity Decides Counting

Permissions must not decide whether a user counts toward labor efficiency.

Why:

- permissions describe what the user can access
- labor efficiency is an HR/business metric
- identity classification belongs in employee master data

### Principle 2: Counting Must Be Explicit

A user should count only if HR explicitly marks them as an employee identity that is included in labor-efficiency metrics.

### Principle 3: PostgreSQL and Legacy KPI Paths Must Match

The legacy SQL and PostgreSQL dashboard runtime must produce the same denominator definition.

## Recommended Approach

Use an HR-owned employee identity field on `a_class.employees`.

Recommended field:

- `employee_identity_type`

Recommended values:

- `employee`
- `investor`
- `visitor`

Future-compatible optional values:

- `contractor`
- `part_time`

Then define labor-efficiency denominator as:

- `status = 'active'`
- `employee_identity_type = 'employee'`

This is the recommended approach because it is:

- simple to understand
- controlled by HR master data
- decoupled from permissions
- safe for future reporting reuse

## Options Considered

### Option A: Use permission roles to exclude investors and visitors

Pros:

- no new employee field required

Cons:

- wrong ownership boundary
- permissions are not HR truth
- users can hold multiple roles
- reporting logic becomes fragile

### Option B: Use employee identity type in HR data

Pros:

- clean business meaning
- stable denominator
- reusable by payroll, performance, and reporting
- easy to audit

Cons:

- requires schema and API updates
- requires backfill of existing employee rows

### Option C: Add a single boolean flag such as `include_in_labor_efficiency`

Pros:

- simplest query logic
- minimal reporting change

Cons:

- weaker semantics than identity type
- less reusable for future HR logic
- harder to explain and govern over time

### Recommendation

Adopt **Option B**.

If a smaller rollout is needed, Option C can be treated as a fallback, but Option B is the better long-term model.

## Target End State

After this change:

- only HR-classified real employees count toward labor efficiency
- visitors and investors are always excluded
- PostgreSQL business-overview KPI returns a real labor-efficiency value
- auto-created employee records for non-employee users do not pollute the denominator

## Data Model Changes

### Employee Table

Add to `a_class.employees`:

- `employee_identity_type VARCHAR(...) NOT NULL DEFAULT 'employee'`

Recommended allowed values:

- `employee`
- `investor`
- `visitor`

Optional future values:

- `contractor`
- `part_time`

### Why This Table

The employee archive is the correct source because:

- labor efficiency is an HR/business metric
- employee inclusion is a personnel fact
- the login system should remain independent

## API Changes

### HR Employee APIs

The following HR responses should expose `employee_identity_type`:

- employee list
- employee detail
- employee create
- employee update
- my profile response when applicable

### My Profile Auto-Creation Guard

When `/api/hr/me/profile` auto-creates a record, it must not default all users into counted employees.

Recommended behavior:

- if auto-creation remains enabled, default `employee_identity_type = 'visitor'`
- counted employee status should require explicit admin or HR confirmation

This prevents accidental denominator inflation.

## KPI and SQL Changes

### Legacy KPI SQL

Change labor-efficiency employee count from:

- `status = 'active'`

to:

- `status = 'active' AND employee_identity_type = 'employee'`

### PostgreSQL Runtime Chain

The PostgreSQL dashboard chain must stop hardcoding `labor_efficiency = 0`.

Recommended implementation direction:

1. compute counted employee count from `a_class.employees`
2. use the same business-overview period window as current GMV
3. divide aggregated GMV by counted employee count
4. preserve safe zero/null behavior when no counted employees exist

### Formula Behavior

Recommended formula:

- if counted employee count > 0: `round(gmv / employee_count, 2)`
- if counted employee count = 0: return `0`

This matches the historical pattern already used in the legacy KPI SQL.

## Migration Strategy

### Phase 1: Schema Preparation

- add `employee_identity_type`
- default existing rows to `employee`

### Phase 2: Data Backfill

- identify current investor and visitor employee rows
- update them to the correct identity type

### Phase 3: Runtime Cutover

- switch labor-efficiency SQL and PostgreSQL service logic to the new denominator

### Phase 4: Verification

- verify visitors do not count
- verify investors do not count
- verify active employees still count
- verify business-overview and annual-summary labor-efficiency values align

## Edge Cases

### Logged-In User Without HR Approval

If a user can log in but is not a true employee:

- they may still need an account
- they must not count in labor efficiency

This is exactly why identity must be separate from permission.

### Employee Leaves Company

If the employee archive status changes away from `active`, the person should stop counting automatically.

### Investor With Platform Visibility

An investor may hold reporting permissions but still must not affect labor-efficiency denominator.

## Testing Strategy

Add verification coverage for:

- active employee counted
- active investor excluded
- active visitor excluded
- inactive employee excluded
- business-overview labor-efficiency formula correctness
- annual-summary labor-efficiency formula correctness
- auto-created HR profile defaults to non-counted identity

## Success Criteria

This design is complete when:

- labor-efficiency denominator counts only `employee_identity_type = 'employee'`
- visitors and investors never count
- PostgreSQL business-overview KPI returns real labor-efficiency values instead of hardcoded `0`
- legacy and PostgreSQL dashboard paths follow the same business rule
- auto-created non-employee profiles cannot silently inflate the denominator
