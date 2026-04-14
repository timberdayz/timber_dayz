# Operating Costs Physical Column Migration Design

## Goal

Physically rename the legacy operating-cost column currently exposed as `salary` / `"工资"` to the new business meaning `marketing_fee` / `"营销费用"` across the XiHong ERP repository and database schema, while preserving a safe rollout path and a reversible migration.

This design addresses a semantic mismatch that has already been corrected in the public application contract:

- Employee payroll costs now belong exclusively to the payroll chain.
- Expense management now represents marketing spend rather than employee salary.

The remaining inconsistency is physical storage and query naming in the database layer and SQL assets.

## Current State

The current public application chain already uses:

- `marketing_fee`
- `total_marketing_fee`

However, the database and a number of SQL assets still depend on:

- English column name `salary`
- Chinese column name `"工资"`

This legacy naming still appears in:

- ORM mapping for `a_class.operating_costs`
- expense-management router SQL
- dashboard service fallback SQL
- SQL API modules
- mart SQL
- metabase question SQL
- migration/bootstrap SQL
- deployment/reference docs

## Scope

### In Scope

- Physical rename design for `a_class.operating_costs`
- Repository code changes required to align with the renamed column
- Forward migration SQL
- Rollback migration SQL
- Verification checklist after migration
- Documentation alignment for active docs

### Out of Scope

- Payroll schema changes
- Historical archive cleanup under `docs/archive/`
- Broader HR `salary` terminology unrelated to `operating_costs`
- New expense-category redesign beyond this single column rename

## Recommended Approach

Use a **two-stage rollout**:

1. Prepare and merge code, SQL, migration scripts, and validation assets in the repository.
2. Execute the physical database rename during a controlled maintenance window.

This avoids a dangerous state where the live database is renamed before the application, dashboard SQL, and fallback queries are aligned.

## Options Considered

### Option A: Prepare-first, execute-later

Update repository assets first, ship a reversible migration script, then run the DB rename in a scheduled window.

Pros:

- Lowest operational risk
- Clear reviewable change set
- Easier rollback planning
- Prevents partial cutover

Cons:

- Requires a deliberate second execution step in the target database

### Option B: Immediate hard cutover

Rename the database column first and fix application code afterward.

Pros:

- Faster if nothing breaks

Cons:

- High runtime risk
- Easy to miss dependent SQL or fallback paths
- Poor rollback ergonomics

### Recommendation

Adopt **Option A**.

## Target End State

After migration, the operating-costs chain should use:

- English physical name: `marketing_fee`
- Chinese physical name: `"营销费用"`

The repository should no longer treat `salary` / `"工资"` as the active column for `a_class.operating_costs`.

Employee payroll semantics remain unchanged elsewhere in the system.

## Affected Areas

### Database Layer

- `a_class.operating_costs`
- initial create-table SQL
- schema-separation / deployment SQL
- future migration scripts

### ORM / Backend

- `modules/core/db/schema.py`
- `backend/routers/expense_management.py`
- `backend/services/postgresql_dashboard_service.py`

### SQL Assets

- `sql/api_modules/business_overview_operational_metrics_module.sql`
- `sql/mart/annual_summary_shop_month.sql`
- `sql/metabase_questions/business_overview_operational_metrics.sql`
- `sql/metabase_questions/annual_summary_trend.sql`
- `sql/metabase_questions/annual_summary_by_shop.sql`

### Documentation

- active cost/data docs
- deployment guidance
- phase summaries still used as live references

## Database Migration Design

### Forward Migration

Conceptually perform:

1. Rename English physical column `salary` -> `marketing_fee` where present.
2. Rename Chinese physical column `"工资"` -> `"营销费用"` where present.
3. Update any generated expressions, comments, or triggers that reference the old column.
4. Update table comments and column comments so business meaning is explicit.

The exact SQL may vary by environment because this repository has both English-column and Chinese-column forms in historical scripts. The migration should defensively support whichever variant exists in the target schema.

### Rollback Migration

Provide the inverse:

1. `marketing_fee` -> `salary`
2. `"营销费用"` -> `"工资"`
3. Restore dependent comments and expressions

Rollback should only be used if validation fails immediately after cutover.

## Repository Refactor Rules

### Public Contract

Keep only:

- `marketing_fee`
- `total_marketing_fee`

No reintroduction of:

- `salary`
- `total_salary`

inside the expense-management public chain.

### Internal SQL

All active SQL should reference the new physical column name after the migration branch is complete.

### Payroll Separation

Do not touch HR payroll `salary` semantics outside the `operating_costs` chain. Those are different domains and should remain intact.

## Implementation Steps

### Step 1: Inventory and replace active repository references

Update all active code and SQL that still reference the legacy operating-cost column.

### Step 2: Add forward and rollback migration SQL

Create dedicated migration files for the physical column rename.

### Step 3: Update ORM mapping

Point the `OperatingCost` model at the new physical column while preserving existing business behavior.

### Step 4: Update dashboard and aggregation SQL

Replace old column references in:

- API modules
- mart SQL
- metabase question SQL
- Python fallback SQL

### Step 5: Update docs

Align active documentation with the new physical name and rollout guidance.

### Step 6: Verify

Run tests and post-migration SQL checks before calling the migration ready.

## Risks

### Risk 1: Hidden SQL dependencies

Some runtime path may still reference `"工资"` or `salary`.

Mitigation:

- Broad repository grep before completion
- Update all active SQL assets
- Add verification grep/checklist

### Risk 2: Environment drift

Different environments may have slightly different table forms.

Mitigation:

- Write defensive migration SQL
- Verify actual target schema before execution

### Risk 3: Dashboard breakage

Materialized/module SQL may fail if the column rename is incomplete.

Mitigation:

- Update all active SQL assets in the same branch
- Run dashboard-related checks after rename

## Validation Plan

Before DB execution:

- Repository grep shows no active expense-management references to old public fields
- ORM and SQL assets compile/read correctly
- Relevant backend/frontend tests pass

After DB execution:

- `a_class.operating_costs` exposes only the new physical column
- expense management page loads and saves successfully
- annual/business overview queries still compute A-class cost correctly
- no runtime SQL errors referencing old column names

## Suggested Verification Checklist

1. Run repository grep for active `operating_costs` references.
2. Run targeted backend tests for expense management and dashboard cost paths.
3. Run targeted frontend tests for expense-management terminology/compatibility.
4. Inspect the target database schema before executing migration.
5. Execute forward migration in a controlled environment.
6. Re-run smoke checks against expense management and dashboard pages.
7. Keep rollback SQL available until validation completes.

## Decision

Proceed with a prepare-first migration branch that:

- fully updates repository code and SQL,
- adds forward/rollback migrations,
- and defers actual database execution to an explicit maintenance step.
