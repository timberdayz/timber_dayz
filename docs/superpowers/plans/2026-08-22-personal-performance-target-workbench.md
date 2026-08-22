# 个人绩效目标工作台 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-form personal performance inputs with a controlled monthly personal-target workbench and calculate formal personal performance as 80 points from store inheritance plus 20 points from personal targets.

**Architecture:** Add a separate personal-performance domain with a catalog, monthly rule plan, employee-scope snapshot, and structured entries. Keep the existing store operation workbench intact except for removing training from its catalog. Extend income calculation to compose the weighted formal store score with the personal 20-point score and persist an auditable breakdown.

**Tech Stack:** FastAPI, async SQLAlchemy, Pydantic, Alembic/PostgreSQL, Vue 3, Element Plus, Pinia, Vite, pytest, Node test runner.

---

## File Map

- `modules/core/db/schema_parts/business.py`: Personal catalog, plan with immutable calculation mode, scope, assignment snapshot, entry models and final score breakdown field.
- `modules/core/db/schema.py`: ORM exports.
- `current_migrations/versions/<revision>_personal_performance_target_workbench.py`: Personal tables, constraints, indexes, seed catalog, and downgrade.
- `current_migrations/versions/<revision>_operation_catalog_v3.py`: New future-only store catalog version without training; never edit an already-applied migration.
- `backend/services/personal_performance_workbench_service.py`: Rules, scope, entries, locking, scoring and snapshots.
- `backend/services/personal_performance_scoring_service.py`: Integer allocation and metric-specific scoring.
- `backend/services/hr_income_calculation_service.py`: Store 80-point contribution plus personal 20-point contribution; no V1 input override.
- `backend/services/payroll_period_lock_service.py`: Shared month-level transaction lock for performance writes and payroll confirmation.
- `backend/domains/business/routers/performance_management.py`: Personal workbench API routes and formal-readiness integration.
- `backend/domains/business/routers/hr_commission.py`: Reject V1 free-form input writes for new personal-workbench months.
- employee-shop-assignment and store-target write routers/services found by repository search: Share the period lock before changing inherited-score inputs.
- `backend/domains/business/routers/hr_employee.py`: Audit payload with score breakdown and one-decimal display-ready fields.
- `backend/schemas/hr.py` and `backend/schemas/target.py`: Typed workbench, entry, and audit contracts.
- `frontend/src/api/index.js`: Personal workbench API methods.
- `frontend/src/domains/business/views/target/TargetPersonalManagement.vue`: New three-step personal workbench.
- `frontend/src/domains/business/views/hr/PerformanceManagement.vue`: Remove daily free-form input maintenance for V1 months and show score composition.
- `frontend/src/domains/business/views/hr/IncomeAudit.vue`: Render score source and one-decimal values.
- `frontend/src/router/index.js`, `frontend/src/config/menuGroups.js`: Route and label integration.

### Task 1: Define personal-target contracts and persistence

**Files:**
- Modify: `modules/core/db/schema_parts/business.py`
- Modify: `modules/core/db/schema.py`
- Create: `current_migrations/versions/<revision>_personal_performance_target_workbench.py`
- Modify: `backend/schemas/hr.py`
- Modify: `backend/schemas/target.py`
- Test: `backend/tests/test_personal_performance_target_schema.py`
- Test: `backend/tests/test_personal_performance_target_migration_contract.py`

- [ ] Write schema tests for catalog uniqueness, immutable `calculation_mode`, employee-scope uniqueness, assignment-snapshot uniqueness, structured-entry uniqueness, optional exclusion notes, and required historical snapshots.
- [ ] Run the new tests and confirm they fail before models/migration exist.
- [ ] Add the four personal target models, immutable rule/scope snapshots, and typed request/response contracts.
- [ ] Create a reversible migration after the current head. Seed only the four approved personal V1 metrics; do not migrate old free-form rows or alter the existing store catalog.
- [ ] Run focused schema tests, migration upgrade/downgrade validation, and commit `feat: add personal performance target contracts`.

### Task 2: Build integer scoring and monthly workbench services

**Files:**
- Create: `backend/services/personal_performance_scoring_service.py`
- Create: `backend/services/personal_performance_workbench_service.py`
- Test: `backend/tests/test_personal_performance_scoring.py`
- Test: `backend/tests/test_personal_performance_workbench.py`

- [ ] Write failing tests for 1-4 metric allocation, fixed `7/7/6`, `ROUND_HALF_UP`, attendance/goal percentages, training counts, special-task note validation, and incomplete status.
- [ ] Run the tests and confirm failure before service implementation.
- [ ] Implement the pure scoring service without float-rounding dependencies.
- [ ] Implement atomic creation of a `controlled_targets_v1` month only when no active legacy personal inputs or adjustments exist; otherwise retain `legacy_inputs` behavior.
- [ ] Implement rule save, all-active-employee candidate load, store-assignment eligibility, optional exclusion note, scope confirmation/revoke, frozen assignment/positive-sales-target snapshots, structured entry save/read, optimistic locking, and payroll lock guard.
- [ ] Run focused tests and commit `feat: add personal performance target workbench service`.

### Task 3: Add API routes and legacy write protection

**Files:**
- Modify: `backend/domains/business/routers/performance_management.py`
- Modify: `backend/domains/business/routers/hr_commission.py`
- Test: `backend/tests/test_personal_performance_workbench_api.py`
- Test: `backend/tests/test_hr_commission_personal_input_compatibility.py`

- [ ] Write failing API tests for rule-mode creation, legacy-mode rejection, scope, entries, stale versions, unassigned employee rejection, zero-target rejection, revoke behavior, and lock-period rejection.
- [ ] Write failing compatibility tests that old personal-input and performance-adjustment CRUD cannot mutate a controlled month.
- [ ] Add typed admin-only routes and use `response_model` for typed payloads.
- [ ] Preserve old-month read compatibility and return a clear V1 guidance error for forbidden input or adjustment writes.
- [ ] Run focused route tests and commit `feat: expose personal performance workbench api`.

### Task 4: Compose final personal performance and income readiness

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/performance_readiness_service.py`
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/domains/business/routers/hr_employee.py`
- Test: `backend/tests/test_hr_income_calculation_service.py`
- Test: `backend/tests/test_personal_performance_income_readiness.py`
- Test: `backend/tests/test_hr_income_audit_route.py`

- [ ] Add failing tests proving an old personal input or adjustment cannot replace or alter the store-plus-personal score for a controlled month.
- [ ] Add failing tests for `final = store_base * 0.8 + personal_score`, frozen assignment weights, final range, `partial` blocking, and non-participating/unassigned employees.
- [ ] Define that `not_participating` employees receive base payroll and independent store commission but no personal performance salary or personal ranking; test that they do not block other employees' payroll.
- [ ] Persist an auditable calculation breakdown and ensure income/payroll consume only complete final records.
- [ ] Return score source, raw store base, 80-point contribution, personal 20-point contribution, metric items, and final score from the audit route.
- [ ] Round API presentation values to one decimal without changing internal payroll calculation precision.
- [ ] Run focused income, payroll, readiness, and audit tests; commit `feat: compose personal and store performance scores`.

### Task 5: Separate store and personal metric catalogs without rewriting history

**Files:**
- Create: `current_migrations/versions/<revision>_operation_catalog_v3.py`
- Modify: `backend/services/operation_performance_workbench_service.py`
- Modify: `backend/services/operation_performance_scoring_service.py`
- Test: `backend/tests/test_operation_performance_scoring.py`
- Test: `backend/tests/test_personal_performance_catalog_separation.py`

- [ ] Write tests asserting training exists only in the personal catalog and no personal V1 metric appears in the store catalog.
- [ ] Create store catalog V3 with customer satisfaction, complaint count, reply timeliness, and special operation check only. Never modify the prior V2 migration or delete its data.
- [ ] Update store-workbench catalog selection so new months select V3 while existing/confirmed months resolve their persisted catalog version and rule snapshot.
- [ ] Preserve existing confirmed store rule snapshots and V2 historical replay unchanged.
- [ ] Run focused catalog and regression tests; commit `feat: separate store and personal performance metrics`.

### Task 6: Build the personal target workbench UI

**Files:**
- Modify: `frontend/src/api/index.js`
- Create: `frontend/src/domains/business/views/target/TargetPersonalManagement.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagement.vue`
- Test: `frontend/scripts/personalPerformanceWorkbench.test.mjs`

- [ ] Write frontend tests for integer allocation, three-step request payloads, range eligibility, all four input controls, incomplete states, and controlled-month hiding of legacy input/adjustment writes.
- [ ] Add `/target-management/personal` with the same sequential rule/scope/entry interaction as the store workbench, but employee identity and assignment state.
- [ ] Replace V1 free-form personal-input maintenance with a link to the new workbench. In controlled months hide or disable all legacy input and performance-adjustment create/edit/deactivate controls; preserve old-month records as read-only display.
- [ ] Render accessible statuses, independent save feedback, required task explanation, optional exclusion notes, and no free score fields.
- [ ] Run Node tests, `npm run type-check`, and build; commit `feat: add personal performance target workbench ui`.

### Task 7: Make performance and audit explanations consistent

**Files:**
- Modify: `frontend/src/domains/business/views/hr/IncomeAudit.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagement.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceDisplay.vue`
- Test: `frontend/scripts/personalPerformanceAudit.test.mjs`

- [ ] Write tests for one-decimal score rendering and the displayed composition formula.
- [ ] Display store inherited base, 80-point contribution, personal metric items, personal 20-point score, final personal score, and `partial` blockers.
- [ ] Remove raw floating-point score output and the ambiguous empty-input presentation.
- [ ] Run frontend tests, type check, and build; commit `fix: clarify personal performance audit`.

### Task 8: Close the payroll-lock race

**Files:**
- Modify: `backend/services/payroll_period_lock_service.py`
- Modify: payroll-confirmation router/service found by repository search
- Modify: `backend/services/personal_performance_workbench_service.py`
- Modify: `backend/services/operation_performance_workbench_service.py`
- Modify: employee-shop-assignment and store-target write routers/services found by repository search
- Test: `backend/tests/test_payroll_period_lock_service.py`
- Test: `backend/tests/test_personal_performance_concurrency.py`

- [ ] Write concurrency tests showing that personal scope/entry, store workbench entry, employee-store assignment, and sales-target writes cannot commit after payroll confirmation for the same month starts.
- [ ] Add a single transaction-scoped month lock abstraction using a PostgreSQL advisory lock; retain a test-double-compatible fallback only in tests.
- [ ] Require personal and store workbench writes, employee-store assignment writes, store-target writes, performance recalculation, and payroll confirmation to acquire the same lock and recheck locked payroll status immediately before commit.
- [ ] Run focused concurrency and payroll lock tests; commit `fix: serialize personal performance and payroll writes`.

### Task 9: Verify release readiness

**Files:**
- Modify: `docs/superpowers/specs/2026-08-22-personal-performance-target-workbench-design.md` only if implementation reveals an approved contract correction.

- [ ] Run backend workbench, performance, income, payroll, and migration suites.
- [ ] Run migration upgrade/downgrade against an isolated local database.
- [ ] Run frontend workbench/audit tests, type check, and production build.
- [ ] Run `python scripts/verify_architecture_ssot.py` and `python scripts/verify_utf8_source_hygiene.py`; record any pre-existing failures separately.
- [ ] Run manual acceptance: configure 3 personal metrics, confirm two assigned employees, enter manual results, verify `7+7+6`, verify `store x 0.8 + personal`, then confirm partial and payroll-lock rejection.
- [ ] Perform security review for new write APIs and commit `test: verify personal performance target workflow` if test-only changes remain.
