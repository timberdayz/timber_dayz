# Project Simplification Phase 5 Schema SSOT Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status
- Status: complete (merged to `main`)

**Goal:** Decompose `modules/core/db/schema.py` internally into smaller, domain-aligned modules while preserving the SSOT contract and all existing import paths/ORM behavior.

**Architecture:** Keep `modules/core/db/schema.py` as the single public SSOT import surface, but move model definitions into submodules under `modules/core/db/schema_parts/**` (name flexible). `schema.py` becomes an aggregator that imports and re-exports the same symbols. Migrate incrementally in small batches with import/metadata verification after each batch.

**Tech Stack:** SQLAlchemy ORM, Python modules/packages, pytest

---

## Scope

In scope:
- internal refactor of `modules/core/db/schema.py` into smaller modules
- preserving `modules.core.db.schema` import compatibility (same symbol names)
- preserving SQLAlchemy `Base` / metadata behavior
- adding minimal regression tests focused on “import + model identity + table names”

Out of scope:
- changing table names, columns, constraints, indexes
- changing runtime query logic
- changing migrations
- changing DB engine/session configuration

## Phase 5 Exit Criteria

- `modules/core/db/schema.py` is significantly smaller and mostly acts as a re-export surface.
- All existing imports from `modules.core.db` and `modules.core.db.schema` continue to work.
- SQLAlchemy metadata contains the same tables as before (no missing/duplicate tables).
- Targeted backend regression tests pass (at minimum the Phase 3 verification suite plus schema import checks).

---

## Decomposition Strategy (suggested)

Create a new package:
- `modules/core/db/schema_parts/`

Suggested slices (adjust to match actual content):
- `base.py` (Base, metadata helpers, common mixins)
- `dimensions/` (Dim* tables)
- `facts/` (Fact* tables)
- `mart/` (mart models, if any)
- `platform/` (auth/user/session/notification)
- `collection/` (collection-related models)
- `data_platform/` (pipeline/field-mapping/template models)
- `business/` (HR, finance, inventory)

Rule:
- No slice may import `modules.core.db.schema` (one-way dependency into parts).
- Cross-slice relationships should use string-based relationship targets where needed to avoid import cycles.

---

### Task 1: Baseline snapshot + guard tests (before moving anything)

**Files:**
- Modify/Create: `backend/tests/test_schema_ssot_import_contract.py`
- Read: `modules/core/db/schema.py`

- [ ] **Step 1: Write a failing test that asserts the SSOT import path**

Create `backend/tests/test_schema_ssot_import_contract.py`:
```python
def test_schema_module_imports():
    import modules.core.db.schema as schema  # noqa: F401
```

- [ ] **Step 2: Add a “table name presence” smoke**

Pick 5–10 representative table names that must exist (from reading the current schema).

- [ ] **Step 3: Run the schema contract test**

Run:
```powershell
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS (baseline).

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/test_schema_ssot_import_contract.py
git commit -m "test: add schema ssot import contract"
```

---

### Task 2: Introduce `schema_parts/` package + move “base” definitions

**Files:**
- Create: `modules/core/db/schema_parts/__init__.py`
- Create: `modules/core/db/schema_parts/base.py`
- Modify: `modules/core/db/schema.py`

- [ ] **Step 1: Create `schema_parts` package**

- [ ] **Step 2: Move Base/metadata utilities to `base.py`**

Ensure the `Base` object identity used by all models remains unchanged after refactor.

- [ ] **Step 3: Update `schema.py` to import/re-export Base and helpers**

- [ ] **Step 4: Run py_compile on affected modules**

Run:
```powershell
python -m py_compile modules/core/db/schema.py modules/core/db/schema_parts/base.py
```
Expected: no output.

- [ ] **Step 5: Run schema contract test**

Run:
```powershell
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add modules/core/db/schema.py modules/core/db/schema_parts
git commit -m "refactor(schema): introduce schema_parts base module"
```

---

### Task 3: Move models in small batches (start with lowest-coupled slice)

Repeat this task for each batch.

**Files:**
- Create: `modules/core/db/schema_parts/<slice>.py` (or subpackage)
- Modify: `modules/core/db/schema.py`
- Modify (if needed): any relationship strings/imports to avoid cycles

- [ ] **Step 1: Choose a batch of 5–20 models**

Prefer models with minimal cross-references first.

- [ ] **Step 2: Move model classes into a slice module**

Do not change:
- `__tablename__`
- columns
- constraints
- relationship semantics

- [ ] **Step 3: Re-export symbols from `schema.py`**

Keep the public names identical.

- [ ] **Step 4: Run targeted verification**

Run:
```powershell
python -m py_compile modules/core/db/schema.py modules/core/db/schema_parts/<slice>.py
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add modules/core/db/schema.py modules/core/db/schema_parts
git commit -m "refactor(schema): move <slice> models into schema_parts"
```

---

### Task 4: Add a metadata equivalence sanity check

**Files:**
- Modify: `backend/tests/test_schema_ssot_import_contract.py`

- [ ] **Step 1: Add a test that asserts “no duplicate table keys”**

Example idea:
- `len(set(Base.metadata.tables.keys())) == len(Base.metadata.tables)`

- [ ] **Step 2: Add a test that asserts representative tables still exist**

Update the representative list if it changed.

- [ ] **Step 3: Run tests**

Run:
```powershell
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/test_schema_ssot_import_contract.py
git commit -m "test: strengthen schema metadata contract"
```

---

### Task 5: Phase 5 regression suite

**Files:**
- (none)

- [ ] **Step 1: Run the Phase 3 verification subset**

Run:
```powershell
python -m pytest backend/tests/test_domain_route_registration.py backend/tests/test_runtime_mode_route_registration.py -q
python -m pytest backend/tests/data_pipeline/test_dashboard_router_switch.py backend/tests/data_pipeline/test_dashboard_rollout_docs.py backend/tests/data_pipeline/test_postgresql_dashboard_immediate_cleanup.py backend/tests/data_pipeline/test_postgresql_dashboard_entrypoints.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/test_task_center_collection_projection.py tests/test_collection_resume_api.py backend/tests/test_employee_task_notifications.py backend/tests/test_user_registration_api.py backend/tests/test_users_admin_routes.py -q
```
Expected: PASS.

- [ ] **Step 2: Run schema contract tests**

Run:
```powershell
python -m pytest backend/tests/test_schema_ssot_import_contract.py -q
```
Expected: PASS.

---

## Risks and Controls

- Risk: import cycles appear after splitting
  - Control: move in small batches; use relationship strings; avoid cross-imports back to `schema.py`
- Risk: `Base` identity accidentally changes
  - Control: explicitly keep Base creation in one place (`schema_parts/base.py`) and re-export; verify metadata behavior via tests
- Risk: missing table registrations
  - Control: keep `schema.py` importing every slice module so models are imported at module import time (metadata population remains complete)
