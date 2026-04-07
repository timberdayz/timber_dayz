# Production Readiness

**Version**: v4.20.0
**Standard**: SLO / SLA / Capacity Planning / Release Governance / Disaster Recovery

---

## Part A: Performance SLOs & Capacity Baseline (D1)

### API Performance Targets

| API Category | p95 Latency Target | p99 Latency Target | Examples |
|---|---|---|---|
| Critical read endpoints | < 300ms | < 800ms | User list, Target list, Performance list |
| Critical write endpoints | < 800ms | < 2s | Create order, Submit performance, Update target |
| Complex reports / exports | < 3s | < 8s | Income summary, Financial reports, Dashboard |

### Page Load Targets

| Scenario | Target |
|---|---|
| First screen with data (including API requests) | < 2s |
| Filter/refresh response | < 1.5s |
| Form submit feedback | < 1s |

### Capacity Baseline (50-100 concurrent users)

| Component | Parameter | Value |
|---|---|---|
| PostgreSQL connection pool | `pool_size` | 20 |
| PostgreSQL connection pool | `max_overflow` | 30 |
| Redis connections | max concurrent | < 50 |
| Celery workers | minimum instances | >= 4 |
| Task queue backlog | alert threshold | > 100 pending |

### Slow Query Gate

- Any single query exceeding **1s** must include a justification and optimization plan in the PR description.
- New endpoints without a defined performance expectation are **not allowed to merge**.

---

## Part B: Load Testing Gate (D2)

### Tool

`k6` — lightweight, script-based, CI-friendly.

Location: `scripts/load_test/`

### Minimum Test Scenarios

| Scenario | Type |
|---|---|
| Login | Write |
| User list (paginated) | Read |
| Target / Performance / Income list | Read |
| Create / Update operations | Write |
| Collection task trigger | Write |

### Pass Criteria

| Metric | Threshold |
|---|---|
| Concurrent users | 50 users sustained for 2 minutes |
| Error rate | < 1% |
| p95 latency | Within D1 limits per endpoint category |
| Database connections | No pool overflow |

### Trigger Conditions

Load testing is **required** before deployment when any of the following occur:

- Database schema change
- Connection pool or cache configuration change
- New complex query or report endpoint
- Critical service refactor

---

## Part C: Release & Migration Governance (D3)

### Database Migration Pre-run Protocol

1. All Alembic migrations must be executed on **staging** before production.
2. High-risk migrations (data changes / column drops / table renames) require:
   - Backup confirmation
   - Rollback steps documented
   - Execution time window defined
   - Responsible person identified
3. Migration PR must include:
   - Idempotency statement (is the migration safe to re-run?)
   - Rollback statement (how to revert)
   - Data impact statement (rows affected, estimated duration)

### Canary / Phased Release Rules

- Features involving UI changes or core flow changes **must** use a feature flag.
- Feature flag lifecycle: **<= 30 days**; expired flags must be cleaned up.
- Flag naming convention: `ff_{domain}_{feature}_{YYYYMMDD}` (e.g., `ff_hr_new_salary_calc_20260301`)

### Rollback Strategy (Layered)

| Level | Trigger | Action |
|---|---|---|
| Code rollback | Functional bug or performance regression | `git revert` + redeploy |
| Migration rollback | Database change causes failure | `alembic downgrade <target>` + maintenance window |
| Data remediation | Data corruption or accidental deletion | Restore from backup + incremental replay |

---

## Part D: Disaster Recovery (D4)

### RPO / RTO Targets

| Metric | Target |
|---|---|
| RPO (Maximum tolerable data loss) | <= 15 minutes |
| RTO (Time to restore service) | <= 2 hours |

### Backup Strategy

| Data | Frequency | Method |
|---|---|---|
| PostgreSQL full backup | Daily (once) | pg_dump / Barman |
| PostgreSQL WAL archive | Continuous | WAL streaming |
| Redis | Daily | AOF persistence + RDB snapshot |
| File storage (collection downloads) | Daily incremental | rsync / object storage versioning |

### Recovery Drill

- **Frequency**: Once per month
- **Scope**: Must cover at minimum PostgreSQL full restore + critical table validation
- **Validation script**: `scripts/verify_restore.py`
- **Pass criteria**: Key table row counts correct, latest record timestamps within expected window, referential integrity maintained

---

## Part E: ERP Business Acceptance Standards (D7)

### Amount Precision Rules

| Context | Rule |
|---|---|
| CNY amounts | `Decimal`, 2 decimal places; database uses `Numeric(15, 2)` |
| Exchange rates / fee rates | 4 decimal places |
| Percentages | Stored as decimal in database (e.g., `0.15` not `15`); multiply by 100 for display |
| Rounding mode | `ROUND_HALF_UP` (standard rounding) |

### Time Convention Rules

| Rule | Detail |
|---|---|
| Server timezone | UTC only (`datetime.now(timezone.utc)`); `datetime.utcnow()` is **prohibited** |
| Display | Frontend converts to user's local timezone |
| "Month" default | Natural calendar month unless explicitly labeled as fiscal month |
| Cross-month data ownership | Attributed by **event/order occurrence time**, not ingestion time |

### Key Domain Acceptance Checklists

#### Income Module (MyIncome)

- [ ] Monthly income = Base salary + Commission + Bonus - Deductions
- [ ] Sum of all components equals the total amount
- [ ] Each income line item has a source and calculation formula traceable
- [ ] Currency conversion uses the recorded exchange rate for that month
- [ ] Deduction items have individual explanations; no silent negative values

#### Performance Module

- [ ] Score formula result matches manual calculation for sample cases
- [ ] Rankings have no tied positions without explicit tie-breaking rule
- [ ] Score is recalculated and stable (same inputs produce same outputs)
- [ ] Score updates propagate correctly to dependent modules (income, ranking)
- [ ] Historical scores are immutable after submission

#### Target Module

- [ ] Monthly target = Sum of daily breakdown targets
- [ ] Completion rate = Actual / Target * 100 (percentage displayed rounded to 2 decimal places)
- [ ] Targets with 0 denominator display "N/A" not division errors
- [ ] Target propagation (from annual to monthly to daily) uses correct proration
- [ ] Target modification creates an audit record

#### Financial Report Module

- [ ] Revenue - Expenses = Profit (tolerance: 0)
- [ ] Current month + Previous month cumulative = Running total
- [ ] Cost items are classified correctly and not double-counted
- [ ] GMV and net income figures align with order data source
- [ ] Report period boundaries are inclusive/exclusive consistently

---

## Part F: Feature Flag Standards

### Naming Convention

```
ff_{domain}_{feature}_{YYYYMMDD}
```

Examples:
- `ff_hr_new_salary_calc_20260301`
- `ff_finance_annual_summary_20260315`
- `ff_collection_new_scheduler_20260401`

### Lifecycle Rules

1. Flag is created when feature development starts.
2. Flag must be cleaned up within **30 days** of feature GA (general availability).
3. Flag removal requires: remove flag code + tests updated + PR reviewed.
4. Expired flags (>30 days past GA) are treated as tech debt and block new flag creation in the same domain.

### Current Implementation

Feature flags are currently implemented via system configuration (`config_management` table). Use `SystemConfigService.get_config()` to read flag values.
