# Dim Shops Core Canonical Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the runtime so `core.dim_shops` becomes the only canonical `DimShop` table without mixing in `public.dim_shops` cleanup.

**Architecture:** First lock the model/schema contract for `DimShop`, then verify the main ORM-backed read/write paths still function against `core`. Keep `public.dim_shops` retirement out of scope until the runtime alignment is proven.

**Tech Stack:** SQLAlchemy ORM, FastAPI, pytest, PostgreSQL

---

### Task 1: Lock `DimShop` model ownership to `core`

**Files:**
- Create: `backend/tests/test_dim_shops_core_canonical_contract.py`
- Modify: `modules/core/db/schema.py`

- [ ] **Step 1: Write the failing model contract test**

```python
from modules.core.db import DimShop


def test_dim_shop_model_is_bound_to_core_schema():
    assert DimShop.__table__.schema == "core"
    assert DimShop.__table__.fullname == "core.dim_shops"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
pytest backend\tests\test_dim_shops_core_canonical_contract.py -q
```

Expected:
- FAIL because `DimShop` currently resolves to `public`

- [ ] **Step 3: Write minimal schema binding**

Modify `modules/core/db/schema.py` so `DimShop` has explicit `{"schema": "core"}` in `__table_args__` while preserving indexes.

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
pytest backend\tests\test_dim_shops_core_canonical_contract.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add backend\tests\test_dim_shops_core_canonical_contract.py modules\core\db\schema.py
git commit -m "refactor(db): bind dim_shops to core schema"
```

### Task 2: Prove write paths still target `core.dim_shops`

**Files:**
- Create: `backend/tests/test_dim_shops_core_write_paths.py`
- Modify: `backend/services/shop_sync_service.py` only if required

- [ ] **Step 1: Write failing write-path tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement minimal fix if needed**
- [ ] **Step 4: Re-run test to verify it passes**
- [ ] **Step 5: Commit**

### Task 3: Prove key read paths still work through `DimShop`

**Files:**
- Create: `backend/tests/test_dim_shops_core_read_paths.py`
- Modify: relevant routers/services only if required

- [ ] **Step 1: Write failing read-path regression tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement minimal compatibility fixes**
- [ ] **Step 4: Re-run test to verify it passes**
- [ ] **Step 5: Commit**

### Task 4: Record alignment evidence and keep cleanup deferred

**Files:**
- Modify: `docs/reports/2026-03-28-dim-shops-runtime-alignment-investigation.md`
- Modify: `docs/reports/2026-03-28-schema-cleanup-inventory.md`

- [ ] **Step 1: Record model schema after the change**
- [ ] **Step 2: Record read/write test results**
- [ ] **Step 3: Re-state that `public.dim_shops` cleanup is still deferred**
- [ ] **Step 4: Commit**

### Task 5: Run focused verification before handoff

**Files:**
- No new files required

- [ ] **Step 1: Run focused dim_shops verification**

Run:
```powershell
pytest backend\tests\test_dim_shops_core_canonical_contract.py backend\tests\test_dim_shops_core_write_paths.py backend\tests\test_dim_shops_core_read_paths.py backend\tests\test_schema_cleanup_wave2_candidates.py -q
```

- [ ] **Step 2: Run existing schema cleanup regression set**

Run:
```powershell
pytest backend\tests\test_schema_cleanup_inventory.py backend\tests\test_schema_cleanup_low_risk_candidates.py backend\tests\test_schema_cleanup_wave1_preplan.py backend\tests\test_schema_cleanup_wave1_migration_contract.py backend\tests\test_schema_cleanup_rehearsal.py backend\tests\test_schema_cleanup_wave2_candidates.py -q
```

- [ ] **Step 3: Run syntax verification**

Run:
```powershell
python -m py_compile modules\core\db\schema.py backend\services\shop_sync_service.py
```

- [ ] **Step 4: Commit any final fixups**
