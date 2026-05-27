# C-Class Employee Metrics English Column Migration Design

## Goal

Standardize the two C-class HR metric tables onto English column names so the XiHong ERP repository no longer depends on long-term dual-track compatibility between:

- Chinese-column physical tables
- English-column ORM models
- fallback SQL compatibility logic

Target tables:

- `c_class.employee_performance`
- `c_class.employee_commissions`

## Why This Is Needed

Current repository state is mixed:

- ORM and most service-layer code expect English fields such as `employee_code`, `year_month`, `performance_score`, and `commission_amount`
- the real PostgreSQL database still stores these two tables with Chinese physical column names
- multiple runtime paths already need fallback logic to survive schema mismatch

This creates three problems:

1. new code is easy to write incorrectly because it appears the ORM is the source of truth
2. any path without fallback can fail at runtime
3. maintenance cost rises because every read/write path must reason about both schemas

## Current Real Database State

### `c_class.employee_performance`

Current physical columns:

- `id`
- `员工编号`
- `年月`
- `实际销售额`
- `达成率`
- `绩效得分`
- `计算时间`

### `c_class.employee_commissions`

Current physical columns:

- `id`
- `员工编号`
- `年月`
- `销售额`
- `提成金额`
- `提成比例`
- `计算时间`

## Current Code State

### Already Compatible Paths

- `backend/services/hr_income_calculation_service.py`
- `backend/domains/business/routers/performance_management.py`
- `backend/domains/business/routers/hr_commission.py`
- `backend/services/payroll_generation_service.py`

These paths now include fallback behavior and can survive the current Chinese-column database state.

### Structural Problem Remains

The repository still treats English-column ORM definitions as the long-term target shape. Compatibility fallbacks reduce runtime risk, but they are not the desired steady state.

## Recommended Approach

Use a **phased in-place migration** on the existing two tables.

Do not immediately drop or rename the Chinese columns. Instead:

1. add English physical columns
2. backfill data from Chinese columns into English columns
3. switch application writes to English columns
4. keep fallback paths temporarily for safety
5. verify all critical runtime flows
6. remove Chinese columns and fallback code only after stabilization

This is lower risk than a single hard cutover.

## Options Considered

### Option A: Keep permanent dual-schema fallback

Pros:

- lowest immediate effort
- avoids risky migration work

Cons:

- permanent technical debt
- every new code path risks runtime mismatch
- schema truth remains ambiguous

### Option B: Hard cutover rename in one step

Pros:

- fastest path to clean schema

Cons:

- highest operational risk
- easy to miss one reader/writer
- poor rollback ergonomics

### Option C: Add English columns, backfill, then cut over gradually

Pros:

- safest migration path
- supports phased verification
- reversible during rollout
- aligns database and ORM without immediate destructive change

Cons:

- temporarily increases schema width
- requires migration and verification discipline

### Recommendation

Adopt **Option C**.

## Target Column Mapping

### `c_class.employee_performance`

- `员工编号 -> employee_code`
- `年月 -> year_month`
- `实际销售额 -> actual_sales`
- `达成率 -> achievement_rate`
- `绩效得分 -> performance_score`
- `计算时间 -> calculated_at`

### `c_class.employee_commissions`

- `员工编号 -> employee_code`
- `年月 -> year_month`
- `销售额 -> sales_amount`
- `提成金额 -> commission_amount`
- `提成比例 -> commission_rate`
- `计算时间 -> calculated_at`

## Target End State

After migration:

- both tables physically expose English columns
- ORM field definitions match the real database
- all critical readers and writers run without fallback
- Chinese legacy columns are removed after a safe stabilization window

## Scope

### In Scope

- database migration for both tables
- backfill from Chinese columns to English columns
- verification of all critical read/write flows
- temporary compatibility retention during rollout
- final cleanup plan for Chinese columns and fallback code

### Out Of Scope

- redesign of HR performance formulas
- redesign of commission formulas
- schema changes for unrelated C-class tables
- changes to employee identity semantics

## Affected Runtime Flows

### Write Paths

- HR income recalculation writes `employee_performance` and `employee_commissions`
- payroll generation reads both tables
- performance calculation reads `employee_performance`

### Read Paths

- employee performance list
- employee commission list
- payroll refresh and payroll generation
- any profit/personnel views depending on generated payroll

## Migration Plan

### Phase 1: Add English Columns

Add English columns to both tables without removing existing Chinese columns.

For `employee_performance`:

- `employee_code`
- `year_month`
- `actual_sales`
- `achievement_rate`
- `performance_score`
- `calculated_at`

For `employee_commissions`:

- `employee_code`
- `year_month`
- `sales_amount`
- `commission_amount`
- `commission_rate`
- `calculated_at`

### Phase 2: Backfill Existing Data

Populate English columns from Chinese columns for all existing rows.

Backfill must be idempotent and safe to re-run.

### Phase 3: Add Constraints And Indexes

Add the English-column equivalents of current logical constraints:

For `employee_performance`:

- unique `(employee_code, year_month)`
- indexes on `employee_code`
- indexes on `year_month`

For `employee_commissions`:

- unique `(employee_code, year_month)`
- indexes on `employee_code`
- indexes on `year_month`

### Phase 4: Prefer English Writes

Application writes should target English columns first.

During this phase:

- fallback logic may remain
- verification focuses on ensuring newly written rows correctly populate English columns

### Phase 5: Runtime Verification Window

Run verification over the critical flows:

- employee income recalculation
- employee performance list
- employee commission list
- payroll single refresh
- payroll monthly generation
- personal income page

### Phase 6: Cleanup

Only after verification and soak time:

- remove Chinese-column fallback logic
- drop Chinese legacy columns

## Rollback Strategy

If issues appear during phases 1 to 5:

- keep Chinese columns intact
- keep compatibility code active
- roll application code back if needed
- do not drop legacy columns until rollout confidence is high

This is why cleanup must be a separate final phase rather than part of the initial migration.

## Verification Checklist

### Database Verification

- English columns exist in both tables
- backfill copied all existing rows
- English-column unique constraints are in place
- English-column indexes are in place

### Application Verification

- HR income recalculation succeeds
- performance list endpoint succeeds
- employee commission list endpoint succeeds
- payroll single refresh succeeds
- payroll monthly generation succeeds
- my income endpoint succeeds

### Data Verification

For a sample employee/month pair:

- Chinese-column values and English-column values match exactly during transition
- payroll generated from English columns matches prior payroll generated from Chinese-column fallback

## Risks

### Risk 1: Partial Cutover

Some code paths may still silently depend on Chinese-column fallback.

Mitigation:

- explicit path inventory
- staged verification
- separate cleanup phase

### Risk 2: Constraint Drift

The new English columns may be added without proper unique/index parity.

Mitigation:

- include constraints and indexes in the migration plan

### Risk 3: Backfill Gaps

Null or malformed historical rows may leave English columns incomplete.

Mitigation:

- add post-backfill audits for nulls and row counts

## Success Criteria

This migration is complete when:

- both tables physically store English columns
- critical readers and writers run successfully without relying on fallback
- English columns have the expected constraints and indexes
- Chinese legacy columns are retired only after verified stability

