# Snapshot Continuous Inventory Aging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the runtime inventory aging path with a company-level snapshot-continuous aging model driven by imported inventory snapshots instead of ledger/FIFO inventory layers.

**Architecture:** Reuse the existing snapshot chain through `semantic.fact_inventory_snapshot` and `mart.inventory_snapshot_history`, add a company-daily normalization layer plus two persisted mart tables for age history and current age state, and expose the result through the existing inventory aging routes. The implementation keeps a deterministic full rebuild path and an efficient incremental replay path from the earliest changed snapshot date for each affected SKU.

**Tech Stack:** PostgreSQL, SQL assets under `sql/semantic`, `sql/mart`, and `sql/api_modules`; Python 3.14; FastAPI; async SQLAlchemy; Pydantic; Vue 3; Element Plus; pytest.

---

## File Structure

### SQL Assets

- Create: `sql/mart/inventory_snapshot_company_daily.sql`
- Create: `sql/api_modules/inventory_age_list_module.sql`
- Create: `sql/api_modules/inventory_age_summary_module.sql`

### Refresh / Pipeline

- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Create: `backend/services/data_pipeline/inventory_age_refresh_service.py`
- Create: `scripts/rebuild_inventory_age_from_snapshots.py`

### Backend Contracts / Services / Routers

- Modify: `backend/schemas/inventory.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `backend/services/inventory/aging_service.py`
- Modify: `backend/services/inventory/__init__.py`
- Modify: `backend/routers/inventory_domain.py`

### Frontend

- Modify: `frontend/src/api/inventoryDomain.js`
- Modify: `frontend/src/views/inventory/InventoryAging.vue`

### Tests

- Create: `backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py`
- Modify: `backend/tests/data_pipeline/test_inventory_snapshot_change_module.py`
- Create: `backend/tests/data_pipeline/test_inventory_age_refresh_service.py`
- Modify: `backend/tests/test_inventory_aging_service.py`
- Modify: `backend/tests/test_inventory_aging_schema_contract.py`

### Documentation

- Create: `docs/superpowers/specs/2026-04-09-snapshot-continuous-inventory-aging-design.md`
- Create: `docs/superpowers/plans/2026-04-09-snapshot-continuous-inventory-aging.md`

---

## Implementation Notes

- Official runtime scope in this phase is `platform_code + sku_key`.
- `sku_key` resolution order: `platform_sku`, `product_sku`, `sku_id`, `product_id`.
- Official aging quantity is `available_stock`.
- Zero-stock rows do not appear in current aging state.
- `shop_id` is not an official partition key for this phase.
- Existing layer/FIFO objects stay in the codebase, but are no longer the official aging source.

---

### Task 1: Add the Company-Daily Snapshot SQL Asset

**Files:**
- Create: `backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py`
- Create: `sql/mart/inventory_snapshot_company_daily.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 1: Write the failing SQL asset test**

```python
from pathlib import Path


def test_inventory_snapshot_company_daily_sql_asset_exists():
    assert Path("sql/mart/inventory_snapshot_company_daily.sql").exists()
```

- [ ] **Step 2: Add a failing dependency registration test**

```python
from backend.services.data_pipeline.refresh_registry import SQL_TARGET_PATHS


def test_inventory_snapshot_company_daily_is_registered():
    assert SQL_TARGET_PATHS["mart.inventory_snapshot_company_daily"] == "sql/mart/inventory_snapshot_company_daily.sql"
```

- [ ] **Step 3: Run the test and verify it fails**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py -v`

Expected: FAIL because the SQL asset and registry entry do not exist yet.

- [ ] **Step 4: Create the company-daily SQL asset**

Create `sql/mart/inventory_snapshot_company_daily.sql` with logic that:

- reads `mart.inventory_snapshot_history`
- keeps the latest effective snapshot row per day and per raw inventory identity
- resolves `sku_key` with `COALESCE(platform_sku, product_sku, sku_id, product_id)`
- aggregates rows to `snapshot_date + platform_code + sku_key`
- sums `available_stock` into `available_qty`
- sums `on_hand_stock` into `on_hand_qty`
- sums `inventory_value`
- records `last_ingest_timestamp`

- [ ] **Step 5: Register the new mart target**

Update `backend/services/data_pipeline/refresh_registry.py` with:

- dependency order
- SQL path registration

- [ ] **Step 6: Run the test and verify it passes**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py sql/mart/inventory_snapshot_company_daily.sql backend/services/data_pipeline/refresh_registry.py
git commit -m "feat(inventory): add company daily snapshot mart asset"
```

### Task 2: Add Snapshot Aging Persistence And Refresh Service

**Files:**
- Create: `backend/tests/data_pipeline/test_inventory_age_refresh_service.py`
- Create: `backend/services/data_pipeline/inventory_age_refresh_service.py`
- Create: `scripts/rebuild_inventory_age_from_snapshots.py`

- [ ] **Step 1: Write the failing refresh-service test**

```python
from backend.services.data_pipeline.inventory_age_refresh_service import compute_age_transition


def test_stock_increase_resets_age_to_zero():
    result = compute_age_transition(
        previous_qty=1,
        current_qty=3,
        snapshot_date="2026-04-09",
        previous_anchor_date="2026-04-01",
    )
    assert result["age_days"] == 0
    assert result["reset_reason"] == "stock_increase"
```

- [ ] **Step 2: Add a failing zero-stock test**

```python
from backend.services.data_pipeline.inventory_age_refresh_service import compute_age_transition


def test_zero_stock_drops_current_state():
    result = compute_age_transition(
        previous_qty=2,
        current_qty=0,
        snapshot_date="2026-04-09",
        previous_anchor_date="2026-04-01",
    )
    assert result["is_active"] is False
    assert result["age_days"] is None
```

- [ ] **Step 3: Run the tests and verify they fail**

Run: `pytest backend/tests/data_pipeline/test_inventory_age_refresh_service.py -v`

Expected: FAIL because the refresh service does not exist yet.

- [ ] **Step 4: Implement the transition helper**

Create `compute_age_transition()` in `backend/services/data_pipeline/inventory_age_refresh_service.py` to cover:

- first positive
- reappeared after zero
- stock increase
- continued
- zero stock

- [ ] **Step 5: Implement the replay service**

Add a service class that:

- loads rows from `mart.inventory_snapshot_company_daily`
- identifies affected keys and earliest changed snapshot date
- rebuilds history rows for each key from that date forward
- upserts latest positive rows into current state

- [ ] **Step 6: Add the rebuild script**

Create `scripts/rebuild_inventory_age_from_snapshots.py` that can:

- full rebuild
- key-scoped rebuild
- date-scoped rebuild

- [ ] **Step 7: Run tests and verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_age_refresh_service.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_age_refresh_service.py backend/services/data_pipeline/inventory_age_refresh_service.py scripts/rebuild_inventory_age_from_snapshots.py
git commit -m "feat(inventory): add snapshot aging refresh service"
```

### Task 3: Add API Read Modules For Current List And Summary

**Files:**
- Modify: `backend/tests/data_pipeline/test_inventory_snapshot_change_module.py`
- Create: `sql/api_modules/inventory_age_list_module.sql`
- Create: `sql/api_modules/inventory_age_summary_module.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 1: Write the failing API SQL tests**

```python
from pathlib import Path


def test_inventory_age_list_module_exists():
    assert Path("sql/api_modules/inventory_age_list_module.sql").exists()


def test_inventory_age_summary_module_exists():
    assert Path("sql/api_modules/inventory_age_summary_module.sql").exists()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py -v`

Expected: FAIL because the API modules do not exist yet.

- [ ] **Step 3: Create the list module**

Create `sql/api_modules/inventory_age_list_module.sql` to expose:

- `platform_code`
- `sku_key`
- `platform_sku`
- `product_sku`
- `product_name`
- `current_qty`
- `age_anchor_date`
- `age_days`
- `reset_reason`
- `inventory_value`
- `bucket`
- `snapshot_date`

- [ ] **Step 4: Create the summary module**

Create `sql/api_modules/inventory_age_summary_module.sql` to expose:

- total positive SKU count
- total positive quantity
- total inventory value
- bucket rows

- [ ] **Step 5: Register dependencies**

Update `refresh_registry.py` so the API modules depend on the aging current/history outputs.

- [ ] **Step 6: Run tests and verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add sql/api_modules/inventory_age_list_module.sql sql/api_modules/inventory_age_summary_module.sql backend/services/data_pipeline/refresh_registry.py backend/tests/data_pipeline/test_inventory_snapshot_change_module.py
git commit -m "feat(inventory): add inventory age api sql modules"
```

### Task 4: Replace Aging Backend Contracts And Service Logic

**Files:**
- Modify: `backend/tests/test_inventory_aging_schema_contract.py`
- Modify: `backend/tests/test_inventory_aging_service.py`
- Modify: `backend/schemas/inventory.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `backend/services/inventory/aging_service.py`
- Modify: `backend/services/inventory/__init__.py`

- [ ] **Step 1: Write the failing schema contract update**

```python
from backend.schemas.inventory import InventoryAgingRowResponse


def test_inventory_aging_row_response_tracks_anchor_and_reset_reason():
    row = InventoryAgingRowResponse(
        platform_code="miaoshou",
        sku_key="SKU-A",
        platform_sku="SKU-A",
        product_name="Product A",
        current_qty=2,
        age_anchor_date="2026-04-01",
        age_days=8,
        reset_reason="continued",
        inventory_value=10.0,
        bucket="0-30",
        snapshot_date="2026-04-09",
    )
    assert row.reset_reason == "continued"
```

- [ ] **Step 2: Write the failing service test**

```python
async def test_aging_service_reads_current_snapshot_age_rows(monkeypatch):
    ...
    assert result[0].age_days == 61
```

- [ ] **Step 3: Run tests and verify they fail**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py backend/tests/test_inventory_aging_service.py -v`

Expected: FAIL because the schemas and service still represent the old FIFO layer model.

- [ ] **Step 4: Replace the aging response schemas**

Update `backend/schemas/inventory.py` so aging schemas represent snapshot-continuous aging fields:

- remove old layer-specific response semantics from the main route contract
- add `sku_key`
- add `age_anchor_date`
- add `reset_reason`
- add `bucket`
- make `shop_id` non-required or remove it from the aging contract

- [ ] **Step 5: Replace the aging service**

Update `backend/services/inventory/aging_service.py` so it reads from:

- `api.inventory_age_list_module`
- `api.inventory_age_summary_module`

instead of reading `InventoryLayer`.

- [ ] **Step 6: Export the new symbols**

Update `backend/schemas/__init__.py` and `backend/services/inventory/__init__.py`.

- [ ] **Step 7: Run tests and verify they pass**

Run: `pytest backend/tests/test_inventory_aging_schema_contract.py backend/tests/test_inventory_aging_service.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/test_inventory_aging_schema_contract.py backend/tests/test_inventory_aging_service.py backend/schemas/inventory.py backend/schemas/__init__.py backend/services/inventory/aging_service.py backend/services/inventory/__init__.py
git commit -m "feat(inventory): switch aging service to snapshot aging"
```

### Task 5: Adapt Inventory Aging Routes

**Files:**
- Modify: `backend/routers/inventory_domain.py`

- [ ] **Step 1: Write the failing route contract test**

Add or update a router test so `/api/inventory/aging` returns snapshot-age fields and `/api/inventory/aging/buckets` returns current bucket summary fields.

- [ ] **Step 2: Run the route test and verify it fails**

Run: `pytest backend/tests/test_api_startup.py backend/tests/test_inventory_aging_service.py -v`

Expected: FAIL because the route still reflects the old aging shape.

- [ ] **Step 3: Update the route wiring**

Keep the current route paths:

- `GET /api/inventory/aging`
- `GET /api/inventory/aging/buckets`

but wire them to the new snapshot-age service methods.

- [ ] **Step 4: Deprecate shop-scoped assumptions**

Ensure the route does not require `shop_id` semantics for correctness in this phase.

- [ ] **Step 5: Run tests and verify they pass**

Run: `pytest backend/tests/test_api_startup.py backend/tests/test_inventory_aging_service.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/inventory_domain.py backend/tests/test_api_startup.py backend/tests/test_inventory_aging_service.py
git commit -m "feat(inventory): expose snapshot aging through inventory routes"
```

### Task 6: Update the Inventory Aging Frontend

**Files:**
- Modify: `frontend/src/api/inventoryDomain.js`
- Modify: `frontend/src/views/inventory/InventoryAging.vue`

- [ ] **Step 1: Write the failing frontend contract assertion**

Add a frontend contract or lightweight test note that the page expects:

- `sku_key`
- `current_qty`
- `age_days`
- `age_anchor_date`
- `reset_reason`
- `inventory_value`

- [ ] **Step 2: Run the relevant frontend validation and verify it fails**

Run: `npm run build`

Expected: FAIL or page mismatch because the existing component expects FIFO-style fields such as oldest/youngest/weighted average age.

- [ ] **Step 3: Update the API client if needed**

Keep using the existing route family, but align any client assumptions with the new response shapes.

- [ ] **Step 4: Replace the page columns and summary cards**

Update `InventoryAging.vue` to show:

- total positive SKU count
- total positive quantity
- total inventory value
- bucket distribution
- per-SKU rows with `age_days`, `age_anchor_date`, `reset_reason`, `snapshot_date`

- [ ] **Step 5: Remove old FIFO-specific UI language**

Delete or rename labels like:

- oldest age
- youngest age
- weighted average age

if they imply the old layer model.

- [ ] **Step 6: Run frontend validation and verify it passes**

Run: `npm run build`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/inventoryDomain.js frontend/src/views/inventory/InventoryAging.vue
git commit -m "feat(frontend): update inventory aging page for snapshot aging"
```

### Task 7: Add Incremental Replay Verification

**Files:**
- Modify: `backend/tests/data_pipeline/test_inventory_age_refresh_service.py`
- Modify: `scripts/rebuild_inventory_age_from_snapshots.py`

- [ ] **Step 1: Write the failing replay-equivalence test**

```python
def test_full_rebuild_matches_incremental_replay():
    ...
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest backend/tests/data_pipeline/test_inventory_age_refresh_service.py -v`

Expected: FAIL because replay equivalence is not proven yet.

- [ ] **Step 3: Implement rebuild equivalence safeguards**

Ensure the rebuild script and refresh service both use the same transition helper and key resolution logic.

- [ ] **Step 4: Run tests and verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_age_refresh_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_age_refresh_service.py scripts/rebuild_inventory_age_from_snapshots.py backend/services/data_pipeline/inventory_age_refresh_service.py
git commit -m "test(inventory): verify snapshot aging replay equivalence"
```

### Task 8: Final Verification And Documentation Alignment

**Files:**
- Modify: `README.md`
- Modify: any inventory aging docs referenced by the inventory page or API docs

- [ ] **Step 1: Update inventory aging terminology**

Replace misleading runtime wording that implies FIFO batch aging is the official current model.

- [ ] **Step 2: Run backend verification**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_company_daily_module.py backend/tests/data_pipeline/test_inventory_age_refresh_service.py backend/tests/test_inventory_aging_schema_contract.py backend/tests/test_inventory_aging_service.py -v`

Expected: PASS

- [ ] **Step 3: Run frontend verification**

Run: `npm run build`

Expected: PASS

- [ ] **Step 4: Run targeted pipeline verification**

Run the new rebuild command in a safe environment:

```bash
python scripts/rebuild_inventory_age_from_snapshots.py --dry-run
```

Expected: exit `0` with a clear summary of keys and dates that would be rebuilt.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-09-snapshot-continuous-inventory-aging-design.md docs/superpowers/plans/2026-04-09-snapshot-continuous-inventory-aging.md
git commit -m "docs(inventory): document snapshot continuous aging rollout"
```

---

## Execution Order Summary

1. Build company-daily snapshot normalization.
2. Build aging replay service and rebuild script.
3. Publish API read modules.
4. Switch backend aging contracts and service logic.
5. Rewire routes.
6. Update frontend.
7. Prove incremental replay matches full rebuild.
8. Align docs and verify end to end.

## Notes For Implementers

- Do not use `InventoryLayer` as the official source for the runtime aging endpoints after this migration.
- Keep the transition helper as the single algorithm source so SQL, script, and service logic do not drift.
- Do not silently include zero-stock rows in current-state views.
- Treat missing `sku_key` as a data-quality issue, not a normal row.
- Keep the design future-ready by isolating scope logic so shop-level aging can be added later without rewriting the reset algorithm.
