# Labor Efficiency Employee Identity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make labor efficiency count only active real employees, exclude visitors and investors, and restore real labor-efficiency calculation in the PostgreSQL dashboard chain.

**Architecture:** Add an HR-owned employee identity field to `a_class.employees`, expose it through HR schemas and routers, harden auto-created HR profiles to default to a non-counted identity, and update both legacy SQL assets and PostgreSQL runtime code so labor efficiency uses the same denominator rule everywhere.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, PostgreSQL SQL assets, Vue 3 frontend contract consumers, pytest

---

## File Map

### Schema and migrations

- Modify: `modules/core/db/schema.py`
- Modify: `migrations/` newest Alembic revision or add a new migration file for `a_class.employees.employee_identity_type`

### Backend schemas and routers

- Modify: `backend/schemas/hr.py`
- Modify: `backend/domains/business/routers/hr_employee.py`

### Dashboard runtime and SQL assets

- Modify: `sql/metabase_questions/business_overview_kpi.sql`
- Modify: `sql/metabase_questions/annual_summary_kpi.sql`
- Modify: `sql/api_modules/business_overview_kpi_module.sql` only if module shape must expose employee count metadata
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/domains/business/routers/dashboard_api_postgresql.py` only if response contract needs extra fields

### Tests

- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Modify: `backend/tests/test_hr_income_di.py` only if schema/model imports require it
- Add: `backend/tests/test_hr_employee_identity.py`
- Add: `backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py`

### Planning and docs

- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

## Task 1: Add Employee Identity Field To HR Model

**Files:**
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_hr_employee_identity.py`

- [ ] **Step 1: Write the failing model contract test**

```python
from modules.core.db import Employee


def test_employee_model_exposes_identity_type():
    assert hasattr(Employee, "employee_identity_type")
    column = Employee.__table__.c["employee_identity_type"]
    assert column.nullable is False
    assert str(column.default.arg) == "employee"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_model_exposes_identity_type -v`
Expected: FAIL because `employee_identity_type` does not exist yet

- [ ] **Step 3: Add minimal schema field**

Add to `Employee` in `modules/core/db/schema.py`:

```python
employee_identity_type = Column(
    String(32),
    nullable=False,
    default="employee",
    server_default=text("'employee'"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_model_exposes_identity_type -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/core/db/schema.py backend/tests/test_hr_employee_identity.py
git commit -m "feat: add employee identity type field"
```

## Task 2: Add Database Migration For Employee Identity Type

**Files:**
- Create or Modify: `migrations/<new_revision>_add_employee_identity_type.py`
- Test: `backend/tests/test_hr_employee_identity.py`

- [ ] **Step 1: Write the failing migration contract test**

```python
from pathlib import Path


def test_employee_identity_migration_exists():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("migrations").rglob("*.py")
    )
    assert "employee_identity_type" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_identity_migration_exists -v`
Expected: FAIL if no migration references the new field

- [ ] **Step 3: Add migration**

Migration responsibilities:
- add `a_class.employees.employee_identity_type`
- set server default to `'employee'`
- backfill existing rows to `'employee'`
- keep downgrade reversible if repository migration policy allows

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_identity_migration_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations backend/tests/test_hr_employee_identity.py
git commit -m "feat: add employee identity migration"
```

## Task 3: Expose Employee Identity Through HR Schemas

**Files:**
- Modify: `backend/schemas/hr.py`
- Test: `backend/tests/test_hr_employee_identity.py`

- [ ] **Step 1: Write failing schema serialization test**

```python
from backend.schemas.hr import EmployeeResponse


def test_employee_response_includes_identity_type():
    payload = EmployeeResponse(
        employee_code="EMP260001",
        name="Alice",
        status="active",
        employee_identity_type="employee",
    )
    assert payload.employee_identity_type == "employee"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_response_includes_identity_type -v`
Expected: FAIL because schema does not include the field yet

- [ ] **Step 3: Update HR schemas**

Add `employee_identity_type` to:
- `EmployeeCreate`
- `EmployeeUpdate`
- `EmployeeResponse`

Keep default behavior:

```python
employee_identity_type: str = "employee"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_employee_response_includes_identity_type -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/hr.py backend/tests/test_hr_employee_identity.py
git commit -m "feat: expose employee identity in hr schemas"
```

## Task 4: Harden HR Auto-Creation And CRUD Logic

**Files:**
- Modify: `backend/domains/business/routers/hr_employee.py`
- Test: `backend/tests/test_hr_employee_identity.py`

- [ ] **Step 1: Write failing auto-profile test**

```python
async def test_me_profile_auto_created_record_defaults_to_visitor(...):
    response = await client.get("/api/hr/me/profile")
    assert response.status_code == 200
    assert response.json()["employee_identity_type"] == "visitor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_hr_employee_identity.py::test_me_profile_auto_created_record_defaults_to_visitor -v`
Expected: FAIL because auto-created records currently behave like counted employees

- [ ] **Step 3: Update HR router logic**

Required changes:
- auto-created `/api/hr/me/profile` records default to `employee_identity_type="visitor"`
- employee create path accepts explicit `employee_identity_type`
- employee update path allows changing `employee_identity_type`
- response payload always returns the field

- [ ] **Step 4: Add duplicate-binding guard test**

```python
async def test_create_employee_can_mark_investor_identity(...):
    ...
    assert response.json()["employee_identity_type"] == "investor"
```

- [ ] **Step 5: Run focused tests**

Run: `pytest backend/tests/test_hr_employee_identity.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/domains/business/routers/hr_employee.py backend/tests/test_hr_employee_identity.py
git commit -m "feat: harden hr identity defaults"
```

## Task 5: Update Legacy Labor-Efficiency SQL Assets

**Files:**
- Modify: `sql/metabase_questions/business_overview_kpi.sql`
- Modify: `sql/metabase_questions/annual_summary_kpi.sql`
- Test: `backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py`

- [ ] **Step 1: Write failing SQL asset tests**

```python
from pathlib import Path


def test_business_overview_kpi_sql_filters_identity_type():
    sql_text = Path("sql/metabase_questions/business_overview_kpi.sql").read_text(encoding="utf-8")
    assert "employee_identity_type = 'employee'" in sql_text


def test_annual_summary_kpi_sql_filters_identity_type():
    sql_text = Path("sql/metabase_questions/annual_summary_kpi.sql").read_text(encoding="utf-8")
    assert "employee_identity_type = 'employee'" in sql_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py -v`
Expected: FAIL because SQL assets only filter by `status = 'active'`

- [ ] **Step 3: Update SQL**

Change employee count CTE filter to:

```sql
WHERE status = 'active'
  AND employee_identity_type = 'employee'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/metabase_questions/business_overview_kpi.sql sql/metabase_questions/annual_summary_kpi.sql backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py
git commit -m "fix: narrow labor efficiency sql denominator"
```

## Task 6: Restore PostgreSQL Labor-Efficiency Calculation

**Files:**
- Modify: `backend/services/postgresql_dashboard_service.py`
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`

- [ ] **Step 1: Write failing service test for employee identity denominator**

```python
async def test_get_business_overview_kpi_uses_active_employee_identity_denominator(...):
    result = await service.get_business_overview_kpi("2026-03-01", None)
    assert result["labor_efficiency"] == 5000.0
```

Use fixture rows that imply:
- GMV = `10000`
- counted employees = `2`
- active investor rows exist but must not count

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py::test_get_business_overview_kpi_uses_active_employee_identity_denominator -v`
Expected: FAIL because service currently returns `labor_efficiency = 0`

- [ ] **Step 3: Implement minimal service logic**

Implementation should:
- keep current GMV aggregation logic
- query counted employees from `a_class.employees`
- filter by `status='active'` and `employee_identity_type='employee'`
- compute `round(gmv / employee_count, 2)` when employee count > 0

- [ ] **Step 4: Add annual-summary parity test if annual summary reuses same chain**

```python
async def test_annual_summary_kpi_uses_same_employee_identity_denominator(...):
    ...
```

- [ ] **Step 5: Run focused tests**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py -k labor_efficiency -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py
git commit -m "fix: compute postgresql labor efficiency from employee identity"
```

## Task 7: Verify Router Contract Compatibility

**Files:**
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Modify: `backend/domains/business/routers/dashboard_api_postgresql.py` only if needed

- [ ] **Step 1: Write or update router contract test**

```python
async def test_business_overview_kpi_router_returns_labor_efficiency(...):
    payload = ...
    assert payload["data"]["labor_efficiency"] == 5000.0
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k labor_efficiency -v`
Expected: FAIL if router tests still assume zero or omit new behavior

- [ ] **Step 3: Update test fixtures or router mapping**

Keep response shape unchanged unless a real contract gap forces a response-model change.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_router.py -k labor_efficiency -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/domains/business/routers/dashboard_api_postgresql.py
git commit -m "test: align router labor efficiency contract"
```

## Task 8: Run End-To-End Verification

**Files:**
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run focused HR tests**

Run: `pytest backend/tests/test_hr_employee_identity.py -v`
Expected: PASS

- [ ] **Step 2: Run focused dashboard tests**

Run: `pytest backend/tests/data_pipeline/test_labor_efficiency_employee_identity_sql.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py -v`
Expected: PASS

- [ ] **Step 3: Run any existing related smoke tests**

Run: `pytest backend/tests/data_pipeline/test_business_overview_module_consistency.py -v`
Expected: PASS

- [ ] **Step 4: Update planning files**

Record:
- files changed
- tests run
- any residual risks

- [ ] **Step 5: Final commit**

```bash
git add task_plan.md progress.md findings.md
git commit -m "docs: record labor efficiency identity rollout verification"
```

## Risks To Watch

- existing employee records for investors or visitors may need manual backfill before KPI results look correct
- frontend HR pages may implicitly assume every employee is a counted employee
- annual summary may need the same denominator logic even if it uses a separate query path
- auto-created visitor profiles may affect any unrelated HR UI filters if those screens expect only real employees

## Definition Of Done

- `Employee` model includes `employee_identity_type`
- migration exists and backfills current rows
- HR APIs expose and preserve the identity type
- auto-created `/api/hr/me/profile` records default to `visitor`
- legacy SQL assets filter labor-efficiency denominator to `employee_identity_type='employee'`
- PostgreSQL business-overview KPI computes real labor efficiency instead of returning `0`
- visitors and investors never count toward labor efficiency

