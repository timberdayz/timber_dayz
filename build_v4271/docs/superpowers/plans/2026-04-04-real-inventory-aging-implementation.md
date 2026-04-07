# Real Inventory Aging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add true inventory aging to the ledger-first inventory domain so aging is derived from remaining inbound layers instead of estimated turnover days.

**Architecture:** Keep `InventoryLedger` as the quantity-change source of truth and add two supporting models: inbound inventory layers and layer-consumption records. Inbound actions create layers, outbound actions consume layers in FIFO order, and read models aggregate the remaining layers into real aging metrics and bucket summaries for inventory management and reporting.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic, PostgreSQL, Vue 3, Element Plus, Vite, pytest, vue-tsc

---

## File Structure

### Backend SSOT / Contracts

- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`
- Modify: `backend/schemas/inventory.py`
- Modify: `backend/schemas/__init__.py`

### Backend Services / Routes

- Create: `backend/services/inventory/inbound_layer_service.py`
- Create: `backend/services/inventory/layer_consumption_service.py`
- Create: `backend/services/inventory/aging_service.py`
- Modify: `backend/services/inventory/grn_service.py`
- Modify: `backend/services/inventory/adjustment_service.py`
- Modify: `backend/services/inventory/__init__.py`
- Modify: `backend/routers/inventory_domain.py`

### Backend Tests / Scripts

- Create: `backend/tests/test_inventory_aging_schema_contract.py`
- Create: `backend/tests/test_inventory_inbound_layer_service.py`
- Create: `backend/tests/test_inventory_layer_consumption_service.py`
- Create: `backend/tests/test_inventory_aging_service.py`
- Create: `scripts/bootstrap_inventory_aging_tables.py`

### Frontend

- Modify: `frontend/src/api/inventoryDomain.js`
- Create: `frontend/src/views/inventory/InventoryAging.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/components/common/SimpleHeader.vue`

---

### Task 1: Add Inventory Aging SSOT Models

**Files:**
- Create: `backend/tests/test_inventory_aging_schema_contract.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from modules.core.db import Base


def test_inventory_aging_tables_are_registered():
    assert "finance.inventory_layers" in Base.metadata.tables
    assert "finance.inventory_layer_consumptions" in Base.metadata.tables
```

- [ ] **Step 2: Add a failing OpeningBalance enhancement test**

```python
from modules.core.db import OpeningBalance


def test_opening_balance_tracks_received_date_or_age():
    columns = OpeningBalance.__table__.columns.keys()
    assert "received_date" in columns or "opening_age_days" in columns
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py -v`

Expected: FAIL because the aging models and OpeningBalance enhancement do not exist yet.

- [ ] **Step 4: Add `InventoryLayer` ORM model**

Add a finance-schema model with at least:

```python
class InventoryLayer(Base):
    __tablename__ = "inventory_layers"
    layer_id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(32), nullable=False)
    source_id = Column(String(64), nullable=False)
    source_line_id = Column(String(64), nullable=True)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    warehouse = Column(String(64), nullable=True)
    received_date = Column(Date, nullable=False)
    original_qty = Column(Integer, nullable=False, default=0)
    remaining_qty = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Add `InventoryLayerConsumption` ORM model**

Add a finance-schema model with at least:

```python
class InventoryLayerConsumption(Base):
    __tablename__ = "inventory_layer_consumptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    outbound_ledger_id = Column(Integer, ForeignKey("finance.inventory_ledger.ledger_id"), nullable=False)
    layer_id = Column(Integer, ForeignKey("finance.inventory_layers.layer_id"), nullable=False)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    consumed_qty = Column(Integer, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=False)
    age_days_at_consumption = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 6: Enhance `OpeningBalance`**

Add one of these fields, preferring `received_date`:

```python
received_date = Column(Date, nullable=True)
```

Optional helper fallback:

```python
opening_age_days = Column(Integer, nullable=True)
```

- [ ] **Step 7: Export new models**

Update:
- `modules/core/db/__init__.py`
- `backend/models/database.py`

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_inventory_aging_schema_contract.py modules/core/db/schema.py modules/core/db/__init__.py backend/models/database.py
git commit -m "feat(inventory): add inventory aging layer models"
```

### Task 2: Add Aging API Contracts And Bootstrap Script

**Files:**
- Modify: `backend/schemas/inventory.py`
- Modify: `backend/schemas/__init__.py`
- Create: `scripts/bootstrap_inventory_aging_tables.py`

- [ ] **Step 1: Write the failing contract test**

Add to `backend/tests/test_inventory_aging_schema_contract.py`:

```python
import backend.schemas as schemas


def test_inventory_aging_contracts_are_exported():
    assert hasattr(schemas, "InventoryAgingRowResponse")
    assert hasattr(schemas, "InventoryAgingBucketResponse")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py -v`

Expected: FAIL because the new schemas are not exported yet.

- [ ] **Step 3: Add aging request/response schemas**

In `backend/schemas/inventory.py`, add:
- `InventoryAgingRowResponse`
- `InventoryAgingBucketResponse`
- `InventoryAgingSummaryResponse`

Suggested response shape:

```python
class InventoryAgingRowResponse(BaseModel):
    platform_code: str
    shop_id: str
    platform_sku: str
    remaining_qty: int
    oldest_age_days: int
    youngest_age_days: int
    weighted_avg_age_days: float
```

- [ ] **Step 4: Export schema symbols**

Update `backend/schemas/__init__.py`.

- [ ] **Step 5: Add bootstrap script**

Create `scripts/bootstrap_inventory_aging_tables.py` that creates:
- `finance.inventory_layers`
- `finance.inventory_layer_consumptions`

Use the same root-path bootstrap style already applied in `scripts/bootstrap_inventory_adjustment_tables.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/schemas/inventory.py backend/schemas/__init__.py scripts/bootstrap_inventory_aging_tables.py backend/tests/test_inventory_aging_schema_contract.py
git commit -m "feat(inventory): add inventory aging api contracts"
```

### Task 3: Build Inbound Layer Creation

**Files:**
- Create: `backend/tests/test_inventory_inbound_layer_service.py`
- Create: `backend/services/inventory/inbound_layer_service.py`
- Modify: `backend/services/inventory/grn_service.py`
- Modify: `backend/services/inventory/adjustment_service.py`
- Modify: `backend/services/inventory/__init__.py`

- [ ] **Step 1: Write the failing inbound-layer test**

```python
from backend.services.inventory.inbound_layer_service import build_layer_record


def test_build_layer_record_uses_received_date_and_original_qty():
    layer = build_layer_record(
        source_type="grn",
        source_id="GRN-001",
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        received_date="2026-04-04",
        qty=10,
        unit_cost=5.0,
    )
    assert layer["original_qty"] == 10
    assert layer["remaining_qty"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_inventory_inbound_layer_service.py -v`

Expected: FAIL because the service does not exist yet.

- [ ] **Step 3: Implement pure layer builder**

Create `build_layer_record()` in `backend/services/inventory/inbound_layer_service.py`.

- [ ] **Step 4: Implement async inbound-layer service**

Add service methods to create layers from:
- opening balance
- GRN posting
- adjustment increase

- [ ] **Step 5: Integrate with GRN posting**

Modify `backend/services/inventory/grn_service.py` so each posted GRN line creates an `InventoryLayer`.

- [ ] **Step 6: Integrate with positive adjustment posting**

Modify `backend/services/inventory/adjustment_service.py` so positive deltas create inbound layers.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_inbound_layer_service.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_inventory_inbound_layer_service.py backend/services/inventory/inbound_layer_service.py backend/services/inventory/grn_service.py backend/services/inventory/adjustment_service.py backend/services/inventory/__init__.py
git commit -m "feat(inventory): create inbound inventory layers"
```

### Task 4: Build FIFO Layer Consumption

**Files:**
- Create: `backend/tests/test_inventory_layer_consumption_service.py`
- Create: `backend/services/inventory/layer_consumption_service.py`
- Modify: `backend/services/inventory/adjustment_service.py`
- Modify: `backend/services/inventory/__init__.py`

- [ ] **Step 1: Write the failing FIFO test**

```python
from backend.services.inventory.layer_consumption_service import consume_layers_fifo


def test_consume_layers_fifo_uses_oldest_layer_first():
    layers = [
        {"layer_id": 1, "remaining_qty": 10, "age_days": 20},
        {"layer_id": 2, "remaining_qty": 8, "age_days": 5},
    ]
    consumptions = consume_layers_fifo(layers=layers, requested_qty=12)
    assert consumptions[0]["layer_id"] == 1
    assert consumptions[0]["consumed_qty"] == 10
    assert consumptions[1]["layer_id"] == 2
    assert consumptions[1]["consumed_qty"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_inventory_layer_consumption_service.py -v`

Expected: FAIL because the service does not exist yet.

- [ ] **Step 3: Implement the pure FIFO helper**

Create `consume_layers_fifo()` in `backend/services/inventory/layer_consumption_service.py`.

- [ ] **Step 4: Implement async persistence for consumptions**

Add methods that:
- load open layers ordered by oldest `received_date`
- decrement `remaining_qty`
- create `inventory_layer_consumptions`

- [ ] **Step 5: Integrate with negative adjustments**

Modify `backend/services/inventory/adjustment_service.py` so negative deltas consume layers instead of only writing ledger.

- [ ] **Step 6: Leave a clear integration seam for future sales-outflow**

Add a focused service method like:

```python
async def consume_for_outbound_ledger(...)
```

so sales posting can reuse the same FIFO logic later.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_layer_consumption_service.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_inventory_layer_consumption_service.py backend/services/inventory/layer_consumption_service.py backend/services/inventory/adjustment_service.py backend/services/inventory/__init__.py
git commit -m "feat(inventory): add fifo layer consumption"
```

### Task 5: Build Aging Read Service And Domain Routes

**Files:**
- Create: `backend/tests/test_inventory_aging_service.py`
- Create: `backend/services/inventory/aging_service.py`
- Modify: `backend/routers/inventory_domain.py`

- [ ] **Step 1: Write the failing aging-summary test**

```python
from backend.services.inventory.aging_service import compute_weighted_avg_age_days


def test_weighted_avg_age_days_uses_remaining_qty_weights():
    value = compute_weighted_avg_age_days(
        rows=[
            {"remaining_qty": 10, "age_days": 30},
            {"remaining_qty": 20, "age_days": 60},
        ]
    )
    assert round(value, 2) == 50.0
```

- [ ] **Step 2: Add a failing bucket test**

```python
from backend.services.inventory.aging_service import bucket_age_days


def test_bucket_age_days_maps_91_to_180_plus_correctly():
    assert bucket_age_days(95) == "91-180"
```

- [ ] **Step 3: Add a failing route exposure test**

```python
from backend.routers.inventory_domain import router


def test_inventory_domain_router_exposes_aging_routes():
    paths = {route.path for route in router.routes}
    assert "/api/inventory/aging" in paths
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest backend/tests/test_inventory_aging_service.py -v`

Expected: FAIL because the service and routes do not exist yet.

- [ ] **Step 5: Implement pure aging helpers**

Create in `backend/services/inventory/aging_service.py`:
- `bucket_age_days()`
- `compute_weighted_avg_age_days()`

- [ ] **Step 6: Implement async aging query service**

Add service methods that return:
- SKU aging rows
- bucket summaries
- top old inventory rows by remaining value

The service should read from remaining layers, not from overview snapshots.

- [ ] **Step 7: Add typed routes**

Add to `backend/routers/inventory_domain.py`:
- `GET /api/inventory/aging`
- `GET /api/inventory/aging/buckets`

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_aging_service.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_inventory_aging_service.py backend/services/inventory/aging_service.py backend/routers/inventory_domain.py
git commit -m "feat(inventory): add real inventory aging queries"
```

### Task 6: Add Frontend Aging Page

**Files:**
- Modify: `frontend/src/api/inventoryDomain.js`
- Create: `frontend/src/views/inventory/InventoryAging.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/components/common/SimpleHeader.vue`

- [ ] **Step 1: Add API client methods**

In `frontend/src/api/inventoryDomain.js`, add:
- `getAging`
- `getAgingBuckets`

- [ ] **Step 2: Create the aging page**

`frontend/src/views/inventory/InventoryAging.vue` should show:
- SKU aging table
- oldest age
- weighted average age
- bucket distribution

- [ ] **Step 3: Add route and navigation**

Update:
- `frontend/src/router/index.js`
- `frontend/src/config/menuGroups.js`
- `frontend/src/components/common/SimpleHeader.vue`

- [ ] **Step 4: Run frontend verification**

Run:
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected:
- type-check succeeds
- build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/inventoryDomain.js frontend/src/views/inventory/InventoryAging.vue frontend/src/router/index.js frontend/src/config/menuGroups.js frontend/src/components/common/SimpleHeader.vue
git commit -m "feat(frontend): add real inventory aging page"
```

### Task 7: Add Real-DB Bootstrap And Read-Only Validation

**Files:**
- Modify: `scripts/bootstrap_inventory_adjustment_tables.py`
- Create: `scripts/bootstrap_inventory_aging_tables.py`
- Modify: `progress.md` if present in the execution workspace

- [ ] **Step 1: Create the table bootstrap script**

Create `scripts/bootstrap_inventory_aging_tables.py` that:
- resolves project root
- imports the new ORM models
- creates the two new finance tables with `checkfirst=True`

- [ ] **Step 2: Execute the bootstrap against the test database**

Run: `python scripts/bootstrap_inventory_aging_tables.py`

Expected: both tables are created or confirmed present.

- [ ] **Step 3: Run read-only DB validation**

Run an inline async script that verifies:
- `SELECT COUNT(*) FROM finance.inventory_layers`
- `SELECT COUNT(*) FROM finance.inventory_layer_consumptions`
- `InventoryOpeningBalanceService.list_opening_balances()`
- `InventoryAgingService` read methods

Expected:
- table reads succeed
- services return rows or empty results without errors

- [ ] **Step 4: Commit**

```bash
git add scripts/bootstrap_inventory_aging_tables.py
git commit -m "chore(inventory): add inventory aging table bootstrap"
```

### Task 8: Final Verification

**Files:**
- Update any planning/progress artifacts if present

- [ ] **Step 1: Run all aging-focused backend tests**

Run:

```bash
pytest backend/tests/test_inventory_aging_schema_contract.py backend/tests/test_inventory_inbound_layer_service.py backend/tests/test_inventory_layer_consumption_service.py backend/tests/test_inventory_aging_service.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run broader inventory backend verification**

Run:

```bash
pytest backend/tests/test_inventory_domain_schema_contract.py backend/tests/test_inventory_balance_service.py backend/tests/test_inventory_opening_balance_service.py backend/tests/test_inventory_grn_service.py backend/tests/test_inventory_adjustment_service.py backend/tests/test_inventory_reconciliation_service.py backend/tests/test_inventory_overview_route.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Expected: both exit 0.

- [ ] **Step 4: Run old-path grep guard**

Run:

```bash
git grep -n -e "/products/products" -e "/inventory/list" -e "InventoryManagement.vue" -- backend frontend
```

Expected: no active inventory callers remain.

- [ ] **Step 5: Commit final integration**

```bash
git add -A
git commit -m "feat(inventory): add real inventory aging"
```

---

## Notes For Execution

- Do not try to solve “future sales posting” and “real inventory aging” in one giant refactor. Add the reusable FIFO consumption seam now, then wire sales to it in a later focused change if outbound sales posting is not yet stable.
- Prefer `received_date` over `opening_age_days` for `OpeningBalance`; only keep `opening_age_days` if historical data constraints force it.
- Keep true aging and `estimated_turnover_days` side by side. Do not silently relabel one as the other.
