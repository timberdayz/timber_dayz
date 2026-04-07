# Inventory Ledger-First Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the inventory domain so that real inventory management is ledger-first, while the current snapshot/product page is renamed and isolated as inventory overview.

**Architecture:** The implementation splits inventory into two bounded contexts. The real inventory domain reads and writes only through finance-schema inventory models (`OpeningBalance`, `GRNHeader`, `GRNLine`, `InventoryLedger`, plus new adjustment models), while the overview domain serves read-only snapshot and SKU browsing from existing overview-oriented sources. Legacy `/api/inventory/*` and `/api/products/*` inventory misuse are removed instead of preserved.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic, PostgreSQL, Vue 3, Element Plus, Pinia, Vite, pytest, vue-tsc

---

## File Structure

### Backend Domain Files

- Create: `backend/schemas/inventory.py`
- Create: `backend/schemas/inventory_overview.py`
- Create: `backend/services/inventory/__init__.py`
- Create: `backend/services/inventory/balance_service.py`
- Create: `backend/services/inventory/ledger_service.py`
- Create: `backend/services/inventory/grn_service.py`
- Create: `backend/services/inventory/adjustment_service.py`
- Create: `backend/services/inventory/reconciliation_service.py`
- Create: `backend/services/inventory/overview_service.py`
- Create: `backend/routers/inventory_domain.py`
- Create: `backend/routers/inventory_overview.py`

### Backend SSOT Files

- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `backend/main.py`

### Backend Test Files

- Create: `backend/tests/test_inventory_domain_schema_contract.py`
- Create: `backend/tests/test_inventory_balance_service.py`
- Create: `backend/tests/test_inventory_grn_service.py`
- Create: `backend/tests/test_inventory_adjustment_service.py`
- Create: `backend/tests/test_inventory_reconciliation_service.py`
- Create: `backend/tests/test_inventory_overview_route.py`

### Frontend Files

- Create: `frontend/src/api/inventoryOverview.js`
- Create: `frontend/src/api/inventoryDomain.js`
- Create: `frontend/src/views/InventoryOverview.vue`
- Create: `frontend/src/views/inventory/InventoryBalances.vue`
- Create: `frontend/src/views/inventory/InventoryLedger.vue`
- Create: `frontend/src/views/inventory/InventoryAdjustments.vue`
- Create: `frontend/src/views/inventory/InventoryGrns.vue`
- Create: `frontend/src/views/inventory/InventoryAlerts.vue`
- Create: `frontend/src/views/inventory/InventoryReconciliation.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/common/SimpleSidebar.vue`
- Modify: `frontend/src/components/common/SimpleHeader.vue`
- Modify: `frontend/src/views/ProductQualityDashboard.vue`
- Modify: `frontend/src/views/SalesDashboard.vue`

### Legacy Removal Targets

- Delete: `backend/routers/inventory.py`
- Delete: `frontend/src/api/inventory.js`
- Delete: `frontend/src/stores/inventory.js`
- Delete or replace: `frontend/src/views/InventoryManagement.vue`

---

### Task 1: Add Inventory Adjustment SSOT Models And API Contracts

**Files:**
- Create: `backend/tests/test_inventory_domain_schema_contract.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`
- Create: `backend/schemas/inventory.py`
- Modify: `backend/schemas/__init__.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from modules.core.db import Base


def test_inventory_adjustment_tables_are_registered():
    assert "finance.inventory_adjustment_headers" in Base.metadata.tables
    assert "finance.inventory_adjustment_lines" in Base.metadata.tables
```

- [ ] **Step 2: Add a failing Pydantic contract test**

```python
from backend.schemas.inventory import InventoryAdjustmentCreateRequest


def test_inventory_adjustment_request_requires_lines():
    payload = InventoryAdjustmentCreateRequest(
        adjustment_date="2026-04-03",
        reason="stock_count",
        lines=[{"platform_code": "shopee", "shop_id": "s1", "platform_sku": "SKU1", "qty_delta": -2}],
    )
    assert payload.lines[0].platform_sku == "SKU1"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_inventory_domain_schema_contract.py -v`

Expected: FAIL because the adjustment models and inventory schemas do not exist yet.

- [ ] **Step 4: Add the new ORM models in the SSOT**

Add `InventoryAdjustmentHeader` and `InventoryAdjustmentLine` to `modules/core/db/schema.py`.

Suggested shape:

```python
class InventoryAdjustmentHeader(Base):
    __tablename__ = "inventory_adjustment_headers"
    adjustment_id = Column(String(64), primary_key=True)
    adjustment_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    reason = Column(String(64), nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=False, default="system")
```

```python
class InventoryAdjustmentLine(Base):
    __tablename__ = "inventory_adjustment_lines"
    adjustment_line_id = Column(Integer, primary_key=True, autoincrement=True)
    adjustment_id = Column(String(64), ForeignKey("finance.inventory_adjustment_headers.adjustment_id", ondelete="CASCADE"), nullable=False)
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    qty_delta = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
```

- [ ] **Step 5: Export the new models through normal import paths**

Update:
- `modules/core/db/__init__.py`
- `backend/models/database.py`

so the new models are available everywhere inventory code expects them.

- [ ] **Step 6: Add inventory Pydantic contracts**

Create `backend/schemas/inventory.py` with:
- balance query responses
- ledger row responses
- GRN create/post contracts
- adjustment create/post contracts
- alert and reconciliation responses

Follow the response-model pattern already used in `backend/schemas/target.py`.

- [ ] **Step 7: Export schema symbols**

Update `backend/schemas/__init__.py` so the inventory contracts are available from the package boundary.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_domain_schema_contract.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_inventory_domain_schema_contract.py modules/core/db/schema.py modules/core/db/__init__.py backend/models/database.py backend/schemas/inventory.py backend/schemas/__init__.py
git commit -m "feat(inventory): add adjustment ssot models and api contracts"
```

### Task 2: Build Balance And Ledger Read Services With Typed Domain Routes

**Files:**
- Create: `backend/tests/test_inventory_balance_service.py`
- Create: `backend/services/inventory/__init__.py`
- Create: `backend/services/inventory/balance_service.py`
- Create: `backend/services/inventory/ledger_service.py`
- Create: `backend/routers/inventory_domain.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing balance calculation test**

```python
from backend.services.inventory.balance_service import compute_balance_summary


def test_compute_balance_summary_uses_opening_plus_movements():
    summary = compute_balance_summary(
        opening_qty=10,
        ledger_rows=[
            {"qty_in": 5, "qty_out": 0},
            {"qty_in": 0, "qty_out": 3},
        ],
    )
    assert summary["current_qty"] == 12
```

- [ ] **Step 2: Write the failing router contract test**

```python
from backend.routers.inventory_domain import router


def test_inventory_domain_router_exposes_balance_and_ledger_routes():
    paths = {route.path for route in router.routes}
    assert "/api/inventory/balances" in paths
    assert "/api/inventory/ledger" in paths
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/test_inventory_balance_service.py -v`

Expected: FAIL because the services and router do not exist yet.

- [ ] **Step 4: Implement the pure balance helper first**

Create `compute_balance_summary()` in `backend/services/inventory/balance_service.py`.

Suggested shape:

```python
def compute_balance_summary(opening_qty: int, ledger_rows: list[dict]) -> dict:
    qty_in = sum(row["qty_in"] for row in ledger_rows)
    qty_out = sum(row["qty_out"] for row in ledger_rows)
    return {
        "opening_qty": opening_qty,
        "qty_in": qty_in,
        "qty_out": qty_out,
        "current_qty": opening_qty + qty_in - qty_out,
    }
```

- [ ] **Step 5: Implement async query services**

Build:
- `InventoryBalanceService`
- `InventoryLedgerService`

Rules:
- use `AsyncSession`
- query only finance-schema sources
- do not read `FactProductMetric` or `b_class` tables here

- [ ] **Step 6: Add typed read endpoints**

In `backend/routers/inventory_domain.py`, add:
- `GET /api/inventory/balances`
- `GET /api/inventory/balances/{platform}/{shop_id}/{sku}`
- `GET /api/inventory/ledger`

Every endpoint must declare `response_model`.

- [ ] **Step 7: Wire the router into the app**

Update `backend/main.py` to include the new inventory domain router.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_balance_service.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_inventory_balance_service.py backend/services/inventory/__init__.py backend/services/inventory/balance_service.py backend/services/inventory/ledger_service.py backend/routers/inventory_domain.py backend/main.py
git commit -m "feat(inventory): add ledger-first balance and ledger read routes"
```

### Task 3: Add GRN Posting Flow Into InventoryLedger

**Files:**
- Create: `backend/tests/test_inventory_grn_service.py`
- Create: `backend/services/inventory/grn_service.py`
- Modify: `backend/routers/inventory_domain.py`

- [ ] **Step 1: Write the failing GRN posting test**

```python
from backend.services.inventory.grn_service import build_receipt_ledger_entry


def test_build_receipt_ledger_entry_sets_receipt_quantities():
    entry = build_receipt_ledger_entry(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        qty_before=10,
        avg_cost_before=5.0,
        qty_received=4,
        unit_cost=6.0,
        grn_id="GRN-001",
    )
    assert entry["movement_type"] == "receipt"
    assert entry["qty_in"] == 4
    assert entry["qty_after"] == 14
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_inventory_grn_service.py -v`

Expected: FAIL because the GRN service does not exist yet.

- [ ] **Step 3: Implement the receipt-entry builder**

Create `build_receipt_ledger_entry()` in `backend/services/inventory/grn_service.py`.

Suggested shape:

```python
def build_receipt_ledger_entry(...):
    qty_after = qty_before + qty_received
    avg_cost_after = ((qty_before * avg_cost_before) + (qty_received * unit_cost)) / qty_after
    return {
        "movement_type": "receipt",
        "qty_in": qty_received,
        "qty_out": 0,
        "qty_before": qty_before,
        "qty_after": qty_after,
        "avg_cost_before": avg_cost_before,
        "avg_cost_after": avg_cost_after,
        "link_grn_id": grn_id,
    }
```

- [ ] **Step 4: Implement async GRN posting service**

Add an async service method that:
- validates the GRN exists
- loads its lines
- appends one receipt ledger row per line
- prevents duplicate posting of the same GRN

- [ ] **Step 5: Add typed GRN routes**

In `backend/routers/inventory_domain.py`, add:
- `GET /api/inventory/grns`
- `POST /api/inventory/grns`
- `POST /api/inventory/grns/{grn_id}/post`

If full GRN creation is too large for the first pass, at minimum implement listing plus posting for existing GRNs and document the creation gap in code comments or TODOs.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_grn_service.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_inventory_grn_service.py backend/services/inventory/grn_service.py backend/routers/inventory_domain.py
git commit -m "feat(inventory): add grn posting into inventory ledger"
```

### Task 4: Add Inventory Adjustment Posting Flow

**Files:**
- Create: `backend/tests/test_inventory_adjustment_service.py`
- Create: `backend/services/inventory/adjustment_service.py`
- Modify: `backend/routers/inventory_domain.py`

- [ ] **Step 1: Write the failing adjustment posting test**

```python
from backend.services.inventory.adjustment_service import build_adjustment_ledger_entry


def test_build_adjustment_ledger_entry_moves_negative_delta_to_qty_out():
    entry = build_adjustment_ledger_entry(
        platform_code="shopee",
        shop_id="shop-1",
        platform_sku="SKU1",
        qty_before=20,
        avg_cost_before=5.0,
        qty_delta=-3,
        unit_cost=5.0,
        adjustment_id="ADJ-001",
    )
    assert entry["movement_type"] == "adjustment"
    assert entry["qty_in"] == 0
    assert entry["qty_out"] == 3
    assert entry["qty_after"] == 17
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_inventory_adjustment_service.py -v`

Expected: FAIL because the adjustment service does not exist yet.

- [ ] **Step 3: Implement the pure adjustment-entry builder**

Create `build_adjustment_ledger_entry()` that translates positive deltas to `qty_in` and negative deltas to `qty_out`.

- [ ] **Step 4: Implement async adjustment posting**

Add service methods that:
- create draft adjustment headers/lines
- validate lines before posting
- post each line into `InventoryLedger`
- prevent re-posting

- [ ] **Step 5: Add typed adjustment routes**

In `backend/routers/inventory_domain.py`, add:
- `GET /api/inventory/adjustments`
- `POST /api/inventory/adjustments`
- `POST /api/inventory/adjustments/{adjustment_id}/post`

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_adjustment_service.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_inventory_adjustment_service.py backend/services/inventory/adjustment_service.py backend/routers/inventory_domain.py
git commit -m "feat(inventory): add adjustment posting flow"
```

### Task 5: Add Alerts And Reconciliation Services

**Files:**
- Create: `backend/tests/test_inventory_reconciliation_service.py`
- Create: `backend/services/inventory/reconciliation_service.py`
- Modify: `backend/routers/inventory_domain.py`

- [ ] **Step 1: Write the failing reconciliation test**

```python
from backend.services.inventory.reconciliation_service import compute_snapshot_delta


def test_compute_snapshot_delta_compares_internal_and_external_stock():
    result = compute_snapshot_delta(internal_qty=12, external_qty=9)
    assert result["delta_qty"] == 3
    assert result["status"] == "mismatch"
```

- [ ] **Step 2: Add a failing alert test**

```python
from backend.services.inventory.reconciliation_service import classify_inventory_alert


def test_classify_inventory_alert_marks_zero_stock_as_out_of_stock():
    alert = classify_inventory_alert(current_qty=0, safety_stock=5)
    assert alert == "out_of_stock"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest backend/tests/test_inventory_reconciliation_service.py -v`

Expected: FAIL because the service does not exist yet.

- [ ] **Step 4: Implement pure helper functions first**

Create:
- `compute_snapshot_delta()`
- `classify_inventory_alert()`

in `backend/services/inventory/reconciliation_service.py`.

- [ ] **Step 5: Implement async reconciliation and alert queries**

Add methods that:
- derive internal stock from ledger-based balance logic
- join or compare against overview/snapshot data
- return structured alert rows and reconciliation rows

- [ ] **Step 6: Add typed routes**

In `backend/routers/inventory_domain.py`, add:
- `GET /api/inventory/alerts`
- `GET /api/inventory/reconciliation`

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_reconciliation_service.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_inventory_reconciliation_service.py backend/services/inventory/reconciliation_service.py backend/routers/inventory_domain.py
git commit -m "feat(inventory): add alerts and reconciliation services"
```

### Task 6: Split Overview Logic Out Of Legacy Product Inventory Router

**Files:**
- Create: `backend/tests/test_inventory_overview_route.py`
- Create: `backend/services/inventory/overview_service.py`
- Create: `backend/schemas/inventory_overview.py`
- Create: `backend/routers/inventory_overview.py`
- Modify: `backend/main.py`
- Modify or replace: `backend/routers/inventory_management.py`

- [ ] **Step 1: Write the failing overview route test**

```python
from backend.routers.inventory_overview import router


def test_inventory_overview_router_exposes_summary_and_product_routes():
    paths = {route.path for route in router.routes}
    assert "/api/inventory-overview/summary" in paths
    assert "/api/inventory-overview/products" in paths
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_inventory_overview_route.py -v`

Expected: FAIL because the overview router does not exist yet.

- [ ] **Step 3: Extract overview service responsibilities**

Move the overview-only logic out of `backend/routers/inventory_management.py` into `backend/services/inventory/overview_service.py`.

The service may continue to read:
- `b_class` inventory snapshot tables
- `FactProductMetric`
- `ProductImage`

But it must remain read-only.

- [ ] **Step 4: Add typed overview schemas**

Create `backend/schemas/inventory_overview.py` for:
- summary response
- product list item
- product detail response
- platform breakdown

- [ ] **Step 5: Add overview router**

Create `backend/routers/inventory_overview.py` with:
- `GET /api/inventory-overview/summary`
- `GET /api/inventory-overview/products`
- `GET /api/inventory-overview/products/{sku}`
- `GET /api/inventory-overview/platform-breakdown`
- `GET /api/inventory-overview/alerts`
- `GET /api/inventory-overview/reconciliation-snapshot`

- [ ] **Step 6: Rewire app routing**

Update `backend/main.py`:
- add the new overview router
- stop using `/api/products/*` as the inventory entry point

- [ ] **Step 7: Decide the fate of `backend/routers/inventory_management.py`**

Do one of these, not both:
- remove it entirely if all behavior moved out
- leave only a tiny deprecation stub that is deleted later in Task 9

Because this is test environment refactor work, prefer deletion over long-lived compatibility.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest backend/tests/test_inventory_overview_route.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_inventory_overview_route.py backend/services/inventory/overview_service.py backend/schemas/inventory_overview.py backend/routers/inventory_overview.py backend/main.py backend/routers/inventory_management.py
git commit -m "refactor(inventory): split overview router from domain inventory"
```

### Task 7: Rename The Frontend Overview Page And Switch It To Overview APIs

**Files:**
- Create: `frontend/src/api/inventoryOverview.js`
- Create: `frontend/src/views/InventoryOverview.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/common/SimpleSidebar.vue`
- Modify: `frontend/src/components/common/SimpleHeader.vue`
- Modify: `frontend/src/views/ProductQualityDashboard.vue`
- Modify: `frontend/src/views/SalesDashboard.vue`
- Delete or replace: `frontend/src/views/InventoryManagement.vue`

- [ ] **Step 1: Write the failing type-check expectation**

Define the target before editing:
- no references to `/products/products`
- route label is `库存总览`
- page component name is `InventoryOverview`

- [ ] **Step 2: Create the new overview API client**

Add `frontend/src/api/inventoryOverview.js` with methods:
- `getSummary`
- `getProducts`
- `getProductDetail`
- `getPlatformBreakdown`
- `getAlerts`

- [ ] **Step 3: Move the old page into the overview context**

Copy or rename `InventoryManagement.vue` into `InventoryOverview.vue` and update:
- title text
- API paths
- semantic naming from management to overview

- [ ] **Step 4: Update router and menu labels**

In `frontend/src/router/index.js` and sidebar/header components:
- rename the old inventory page route to overview
- keep the menu text aligned with the new architecture

- [ ] **Step 5: Update dependent dashboards**

Replace old `/api/products/*` calls in:
- `frontend/src/views/ProductQualityDashboard.vue`
- `frontend/src/views/SalesDashboard.vue`

with overview API usage.

- [ ] **Step 6: Run frontend verification**

Run:
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected:
- type-check succeeds
- Vite build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/inventoryOverview.js frontend/src/views/InventoryOverview.vue frontend/src/router/index.js frontend/src/components/common/SimpleSidebar.vue frontend/src/components/common/SimpleHeader.vue frontend/src/views/ProductQualityDashboard.vue frontend/src/views/SalesDashboard.vue frontend/src/views/InventoryManagement.vue
git commit -m "refactor(frontend): rename inventory management page to inventory overview"
```

### Task 8: Build Frontend Pages For Real Inventory Domain

**Files:**
- Create: `frontend/src/api/inventoryDomain.js`
- Create: `frontend/src/views/inventory/InventoryBalances.vue`
- Create: `frontend/src/views/inventory/InventoryLedger.vue`
- Create: `frontend/src/views/inventory/InventoryAdjustments.vue`
- Create: `frontend/src/views/inventory/InventoryGrns.vue`
- Create: `frontend/src/views/inventory/InventoryAlerts.vue`
- Create: `frontend/src/views/inventory/InventoryReconciliation.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/common/SimpleSidebar.vue`

- [ ] **Step 1: Create the inventory domain API client**

Add `frontend/src/api/inventoryDomain.js` with methods:
- `getBalances`
- `getBalanceDetail`
- `getLedger`
- `getAdjustments`
- `createAdjustment`
- `postAdjustment`
- `getGrns`
- `postGrn`
- `getAlerts`
- `getReconciliation`

- [ ] **Step 2: Build the balances page first**

Create `frontend/src/views/inventory/InventoryBalances.vue`.

It should:
- list current balance rows
- support platform/shop/SKU filters
- navigate to ledger detail

- [ ] **Step 3: Build the ledger page**

Create `frontend/src/views/inventory/InventoryLedger.vue`.

It should:
- display movement history
- support movement-type and date filters
- show before/after quantities

- [ ] **Step 4: Build the adjustment page**

Create `frontend/src/views/inventory/InventoryAdjustments.vue`.

It should:
- list draft/posted adjustments
- create draft adjustments
- post approved adjustments

- [ ] **Step 5: Build the GRN page**

Create `frontend/src/views/inventory/InventoryGrns.vue`.

It should:
- list GRNs
- support posting to ledger

- [ ] **Step 6: Build alerts and reconciliation pages**

Create:
- `InventoryAlerts.vue`
- `InventoryReconciliation.vue`

These are read-only operational pages backed by the new domain routes.

- [ ] **Step 7: Add routes and navigation**

Update router/sidebar so `库存管理` becomes the parent concept for the new domain pages.

- [ ] **Step 8: Run frontend verification**

Run:
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected:
- type-check succeeds
- build succeeds

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/inventoryDomain.js frontend/src/views/inventory/InventoryBalances.vue frontend/src/views/inventory/InventoryLedger.vue frontend/src/views/inventory/InventoryAdjustments.vue frontend/src/views/inventory/InventoryGrns.vue frontend/src/views/inventory/InventoryAlerts.vue frontend/src/views/inventory/InventoryReconciliation.vue frontend/src/router/index.js frontend/src/components/common/SimpleSidebar.vue
git commit -m "feat(frontend): add ledger-first inventory domain pages"
```

### Task 9: Delete Legacy Inventory Paths And Add Regression Guards

**Files:**
- Delete: `backend/routers/inventory.py`
- Delete: `frontend/src/api/inventory.js`
- Delete: `frontend/src/stores/inventory.js`
- Modify: `backend/main.py`
- Modify: any remaining callers discovered by grep

- [ ] **Step 1: Write the failing legacy-reference regression test**

```python
from pathlib import Path


def test_legacy_inventory_router_file_is_removed():
    assert not Path("backend/routers/inventory.py").exists()
```

- [ ] **Step 2: Add a frontend grep-based cleanup check**

Before deleting files, confirm there are no remaining references to:
- `/inventory/list`
- `/inventory/detail`
- `/products/products`

- [ ] **Step 3: Delete the old backend router**

Remove `backend/routers/inventory.py` and any include-router wiring that references it.

- [ ] **Step 4: Delete old frontend API/store**

Remove:
- `frontend/src/api/inventory.js`
- `frontend/src/stores/inventory.js`

- [ ] **Step 5: Replace or remove all remaining legacy callers**

Use targeted grep and update every caller to either:
- domain inventory API
- overview inventory API

- [ ] **Step 6: Run backend and frontend verification**

Run:
- `pytest backend/tests/test_inventory_* -v`
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected:
- backend inventory tests pass
- frontend type-check passes
- frontend build passes

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(inventory): remove legacy inventory paths"
```

### Task 10: Final End-To-End Verification

**Files:**
- Modify: `progress.md`
- Modify: `task_plan.md`
- Optional: `findings.md`

- [ ] **Step 1: Run the full targeted backend verification**

Run:

```bash
pytest backend/tests/test_inventory_domain_schema_contract.py backend/tests/test_inventory_balance_service.py backend/tests/test_inventory_grn_service.py backend/tests/test_inventory_adjustment_service.py backend/tests/test_inventory_reconciliation_service.py backend/tests/test_inventory_overview_route.py -v
```

Expected: all targeted inventory tests PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Expected:
- `vue-tsc` exits 0
- Vite build exits 0

- [ ] **Step 3: Run a quick route wiring grep**

Run:

```bash
git grep -n -e "/api/products" -e "/inventory/list" -e "/inventory/detail" -- backend frontend
```

Expected: no live inventory callers remain, except historical docs or archived content intentionally left untouched.

- [ ] **Step 4: Update planning files with evidence**

Record:
- implemented tasks
- test commands executed
- failures encountered and resolutions

- [ ] **Step 5: Commit the final integrated refactor**

```bash
git add -A
git commit -m "refactor(inventory): cut over to ledger-first inventory domain"
```

---

## Notes For Execution

- Follow `systematic-debugging` whenever any route, query, or build step fails.
- Follow `test-driven-development` strictly: every backend slice starts with a failing test.
- Do not preserve `/api/products/*` inventory semantics as compatibility unless a human explicitly reopens that decision.
- Use `AsyncSession` and `get_async_db()` everywhere in new backend runtime code.
- Keep `FactProductMetric` and snapshot tables strictly inside overview/read-only code.
- Keep all new API contracts in `backend/schemas/`, not inside routers.
