# C-Class Employee Metrics Cleanup Phase Design

## Goal

Define the final cleanup phase for:

- `c_class.employee_performance`
- `c_class.employee_commissions`

after the English-column migration has already been applied and verified.

The cleanup phase removes:

- legacy Chinese physical columns
- runtime fallback logic that reads or writes legacy Chinese columns

## Current State

The repository is now in a healthy transition state:

- both tables physically contain English columns
- historical Chinese columns still exist
- runtime readers and writers prefer English paths where available
- fallback logic still exists as a safety net

This is the correct state for short-term stability, but not the desired steady state.

## Why Cleanup Must Be Separate

Cleanup should not be coupled to the initial migration because that would create unnecessary deployment risk.

Keeping cleanup separate provides:

- rollback safety
- time to observe real runtime behavior
- confidence that all remaining readers/writers are truly using English columns

## Cleanup Preconditions

The cleanup phase should not start until all of the following are true:

1. English columns exist in both tables in the target environment
2. backfill has completed successfully
3. no critical runtime flows depend on Chinese fallback anymore
4. recent operational runs show no fallback-triggered warnings
5. targeted regression tests pass against the migrated schema

## Cleanup Scope

### In Scope

- remove Chinese-column fallback logic from runtime code
- remove Chinese physical columns from:
  - `c_class.employee_performance`
  - `c_class.employee_commissions`
- retain English-column constraints and indexes
- add verification proving all critical paths still work

### Out Of Scope

- redesign of performance scoring
- redesign of commission calculations
- changes to payroll business rules
- changes to employee identity rules

## Tables And Legacy Columns To Remove

### `c_class.employee_performance`

Legacy columns to remove:

- `员工编号`
- `年月`
- `实际销售额`
- `达成率`
- `绩效得分`
- `计算时间`

Retained English columns:

- `employee_code`
- `year_month`
- `actual_sales`
- `achievement_rate`
- `performance_score`
- `calculated_at`

### `c_class.employee_commissions`

Legacy columns to remove:

- `员工编号`
- `年月`
- `销售额`
- `提成金额`
- `提成比例`
- `计算时间`

Retained English columns:

- `employee_code`
- `year_month`
- `sales_amount`
- `commission_amount`
- `commission_rate`
- `calculated_at`

## Runtime Code To Clean Up

### Reader Cleanup

Remove temporary Chinese-column fallback logic from:

- `backend/routers/hr_commission.py`
- `backend/routers/performance_management.py`
- `backend/services/payroll_generation_service.py`

Only remove fallback after tests confirm English columns are used successfully.

### Writer Cleanup

Remove Chinese fallback write SQL from:

- `backend/services/hr_income_calculation_service.py`

After cleanup, this service should only use English ORM writes.

## Recommended Cleanup Sequence

### Phase 1: Verify Fallback Is No Longer Needed

Add or run verification proving:

- employee performance list works using English columns
- employee commission list works using English columns
- payroll single refresh works using English columns
- payroll monthly generation works using English columns
- HR income recalculation writes through English ORM path only

### Phase 2: Remove Fallback Code

Delete transitional Chinese-column compatibility logic from runtime paths while keeping the Chinese database columns intact for one short verification cycle.

This creates a clean testable state:

- code depends only on English columns
- database still allows emergency rollback if needed

### Phase 3: Run Regression Verification

Run the full targeted test set and verify critical runtime flows in the local PostgreSQL database.

Expected result:

- no fallback code remains
- all flows still pass

### Phase 4: Drop Chinese Columns

Only after code-only cleanup passes:

- run a dedicated migration that drops the Chinese columns from both tables

### Phase 5: Final Verification

Re-run:

- migration verification
- payroll verification
- performance/commission query verification
- personal income verification

## Rollback Strategy

### Before Column Drop

If issues appear after removing fallback code but before dropping Chinese columns:

- restore the previous code version
- keep database unchanged

This is low risk.

### After Column Drop

If issues appear after dropping Chinese columns:

- rollback requires restoring the dropped columns from migration rollback or backup

This is why dropping columns must be the final step.

## Verification Checklist

### Code Verification

- no runtime fallback helper remains for the two C-class tables
- no Chinese-column SQL remains in active runtime paths

### Database Verification

- English columns still exist and are populated
- Chinese columns are removed only in the final phase
- English unique constraints and indexes remain intact

### Business Flow Verification

- employee performance list works
- employee commission list works
- payroll refresh works
- payroll monthly generation works
- my income works
- performance recalculation works

## Risks

### Risk 1: Hidden Unscanned Read Path

A low-frequency route, admin tool, or script may still depend on the Chinese columns.

Mitigation:

- run repository-wide grep before cleanup
- review production-facing routes and scheduled jobs

### Risk 2: Tests Pass But Real Database Differs

Local or mocked tests may not reflect real production schema quirks.

Mitigation:

- rehearse cleanup in the same PostgreSQL-style environment used for runtime

### Risk 3: Cleanup Happens Too Early

If fallback is removed before enough observation time, rollback risk rises.

Mitigation:

- require an observation window before cleanup

## Success Criteria

Cleanup is complete when:

- active runtime code no longer contains Chinese-column fallback for these two tables
- the two tables physically contain only English business columns
- all targeted payroll, performance, commission, and income flows still pass
- the repository no longer needs dual-schema reasoning for these tables
