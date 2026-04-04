# Miaoshou Inventory Snapshot And Backlog Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Miaoshou inventory snapshot ingestion and backlog dashboards the explicit running mainline, with snapshot history, snapshot-delta analysis, and honest backlog risk scoring.

**Architecture:** Treat inventory as a snapshot-analysis domain rather than a transaction domain. The pipeline keeps full snapshot history, derives a latest-snapshot view for current inventory pages, derives a snapshot-change view for stagnation analysis, and combines those views with recent sales to produce `estimated_turnover_days`, `stagnant_snapshot_count`, `estimated_stagnant_days`, `risk_level`, and `clearance_priority_score`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, PostgreSQL, SQL views/materialized views, Vue 3, Element Plus, Vite, pytest, vue-tsc

---

## File Structure

### SQL Assets

- Modify: `sql/mart/inventory_backlog_base.sql`
- Create: `sql/mart/inventory_snapshot_history.sql`
- Create: `sql/mart/inventory_snapshot_latest.sql`
- Create: `sql/mart/inventory_snapshot_change.sql`
- Create: `sql/api_modules/inventory_backlog_summary_module.sql`
- Modify: `sql/api_modules/clearance_ranking_module.sql`

### Backend

- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Modify: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Modify: `backend/schemas/inventory_overview.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `backend/services/inventory/overview_service.py`

### Backend Tests

- Create: `backend/tests/data_pipeline/test_inventory_snapshot_change_module.py`
- Create: `backend/tests/data_pipeline/test_inventory_backlog_summary_module.py`
- Modify: `backend/tests/data_pipeline/test_inventory_backlog_module.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`

### Frontend

- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/api/dashboard.js`
- Modify: `frontend/src/views/BusinessOverview.vue`
- Modify: `frontend/src/views/InventoryOverview.vue`

---

### Task 1: Add Snapshot History And Latest Snapshot SQL Assets

**Files:**
- Create: `backend/tests/data_pipeline/test_inventory_snapshot_change_module.py`
- Create: `sql/mart/inventory_snapshot_history.sql`
- Create: `sql/mart/inventory_snapshot_latest.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 1: Write the failing SQL asset test**

```python
from pathlib import Path


def test_inventory_snapshot_sql_assets_exist():
    assert Path("sql/mart/inventory_snapshot_history.sql").exists()
    assert Path("sql/mart/inventory_snapshot_latest.sql").exists()
```

- [ ] **Step 2: Add a failing refresh-registry contract test**

```python
from backend.services.data_pipeline.refresh_registry import REFRESH_DEPENDENCIES


def test_refresh_registry_tracks_inventory_snapshot_assets():
    assert "mart.inventory_snapshot_history" in REFRESH_DEPENDENCIES
    assert "mart.inventory_snapshot_latest" in REFRESH_DEPENDENCIES
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py -v`

Expected: FAIL because the SQL assets and registry entries do not exist yet.

- [ ] **Step 4: Create snapshot history SQL asset**

`sql/mart/inventory_snapshot_history.sql` should normalize the raw inventory snapshot rows into a stable history view with:
- `snapshot_date`
- `platform_code`
- `shop_id`
- `platform_sku`
- `warehouse_name`
- `available_stock`
- `on_hand_stock`
- `inventory_value`
- `source_file_id`
- `ingest_timestamp`

Use the existing inventory snapshot source chain rather than inventing a new source.

- [ ] **Step 5: Create latest snapshot SQL asset**

`sql/mart/inventory_snapshot_latest.sql` should select the latest row per `(platform_code, shop_id, platform_sku, warehouse_name)` from the history view.

- [ ] **Step 6: Register both SQL assets in the pipeline refresh registry**

Update `backend/services/data_pipeline/refresh_registry.py`:
- add dependencies
- add SQL path mapping

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_snapshot_change_module.py sql/mart/inventory_snapshot_history.sql sql/mart/inventory_snapshot_latest.sql backend/services/data_pipeline/refresh_registry.py
git commit -m "feat(snapshot): add inventory snapshot history and latest views"
```

### Task 2: Add Snapshot Change View For Stagnation Metrics

**Files:**
- Modify: `backend/tests/data_pipeline/test_inventory_snapshot_change_module.py`
- Create: `sql/mart/inventory_snapshot_change.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 1: Write the failing stagnation-view test**

```python
from pathlib import Path


def test_inventory_snapshot_change_sql_asset_exists():
    assert Path("sql/mart/inventory_snapshot_change.sql").exists()
```

- [ ] **Step 2: Add a failing SQL-content test**

```python
from pathlib import Path


def test_inventory_snapshot_change_sql_mentions_stock_delta_and_stagnant_days():
    sql_text = Path("sql/mart/inventory_snapshot_change.sql").read_text(encoding="utf-8")
    assert "stock_delta" in sql_text
    assert "estimated_stagnant_days" in sql_text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py -v`

Expected: FAIL because the change view does not exist yet.

- [ ] **Step 4: Create snapshot change SQL asset**

`sql/mart/inventory_snapshot_change.sql` should compare current vs previous snapshot for each inventory key and derive:
- `stock_delta`
- `inventory_value_delta`
- `is_stagnant`
- `snapshot_gap_days`
- `estimated_stagnant_days`
- `stagnant_snapshot_count` (or the seed fields needed to derive it upstream)

Use actual snapshot date differences rather than assuming daily cadence.

- [ ] **Step 5: Add it to refresh registry**

Update the dependency graph and SQL path map.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_snapshot_change_module.py sql/mart/inventory_snapshot_change.sql backend/services/data_pipeline/refresh_registry.py
git commit -m "feat(snapshot): add inventory snapshot change view"
```

### Task 3: Upgrade Inventory Backlog SQL To Include Honest Risk Fields

**Files:**
- Modify: `backend/tests/data_pipeline/test_inventory_backlog_module.py`
- Modify: `sql/mart/inventory_backlog_base.sql`
- Create: `sql/api_modules/inventory_backlog_summary_module.sql`
- Modify: `sql/api_modules/clearance_ranking_module.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`

- [ ] **Step 1: Write the failing backlog SQL asset test**

Add assertions for these fields:
- `estimated_turnover_days`
- `stagnant_snapshot_count`
- `estimated_stagnant_days`
- `risk_level`
- `clearance_priority_score`

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_inventory_backlog_module.py -v`

Expected: FAIL because the current SQL does not expose all required fields.

- [ ] **Step 3: Extend `inventory_backlog_base`**

Modify `sql/mart/inventory_backlog_base.sql` to incorporate:
- current snapshot values from latest snapshot view
- recent sales data
- snapshot-change-derived stagnation metrics

- [ ] **Step 4: Add backlog summary SQL asset**

Create `sql/api_modules/inventory_backlog_summary_module.sql` that aggregates:
- total inventory value
- 30/60/90 threshold values
- bucket counts by risk level

- [ ] **Step 5: Upgrade clearance ranking SQL**

Modify `sql/api_modules/clearance_ranking_module.sql` so ranking is not just inventory value + turnover, but also uses:
- `estimated_stagnant_days`
- `stagnant_snapshot_count`
- `risk_level`
- `clearance_priority_score`

- [ ] **Step 6: Register new SQL asset**

Update `backend/services/data_pipeline/refresh_registry.py`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_inventory_backlog_module.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/tests/data_pipeline/test_inventory_backlog_module.py sql/mart/inventory_backlog_base.sql sql/api_modules/inventory_backlog_summary_module.sql sql/api_modules/clearance_ranking_module.sql backend/services/data_pipeline/refresh_registry.py
git commit -m "feat(backlog): add stagnation-aware inventory backlog metrics"
```

### Task 4: Upgrade PostgreSQL Dashboard Service

**Files:**
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`
- Modify: `backend/services/postgresql_dashboard_service.py`

- [ ] **Step 1: Write the failing service test**

Add test coverage that expects service rows to include:
- `estimated_turnover_days`
- `stagnant_snapshot_count`
- `estimated_stagnant_days`
- `risk_level`
- `clearance_priority_score`

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py -v`

Expected: FAIL because the service currently ranks mostly by turnover and value only.

- [ ] **Step 3: Update backlog ranking logic**

Refine `rank_inventory_backlog_rows()` in `backend/services/postgresql_dashboard_service.py`:
- keep `estimated_turnover_days` as the primary gating metric
- incorporate stagnation metrics
- compute or preserve `risk_level`
- compute or preserve `clearance_priority_score`

- [ ] **Step 4: Add helper functions if needed**

Keep them focused and testable, for example:
- `classify_backlog_risk_level()`
- `score_clearance_priority()`

- [ ] **Step 5: Update service summary methods**

Ensure service methods that return inventory backlog payloads can also produce:
- `summary`
- `top_products`

without frontend-side guesswork.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_service.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/data_pipeline/test_postgresql_dashboard_service.py backend/services/postgresql_dashboard_service.py
git commit -m "feat(backlog): add stagnation-aware service ranking"
```

### Task 5: Upgrade Dashboard Router Responses

**Files:**
- Modify: `backend/tests/data_pipeline/test_postgresql_dashboard_router.py`
- Modify: `backend/routers/dashboard_api_postgresql.py`
- Modify: `backend/schemas/inventory_overview.py`
- Modify: `backend/schemas/__init__.py`

- [ ] **Step 1: Write the failing router contract test**

Add tests for:
- `/api/dashboard/business-overview/inventory-backlog`
- `/api/dashboard/clearance-ranking`

Assert the payload can surface:
- `summary`
- `top_products` or ranked rows
- backlog risk fields

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_router.py -v`

Expected: FAIL because the router currently mirrors the old service payload shape.

- [ ] **Step 3: Add or update Pydantic response shapes**

In `backend/schemas/inventory_overview.py`, add response models for:
- backlog summary
- backlog product row
- clearance ranking row

- [ ] **Step 4: Update router payload normalization**

Modify `backend/routers/dashboard_api_postgresql.py` so the backlog and clearance endpoints return stable, explicit payloads that match the frontend expectations.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/data_pipeline/test_postgresql_dashboard_router.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/routers/dashboard_api_postgresql.py backend/schemas/inventory_overview.py backend/schemas/__init__.py
git commit -m "feat(backlog): stabilize dashboard router payloads"
```

### Task 6: Upgrade Business Overview Frontend Backlog Module

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/api/dashboard.js`
- Modify: `frontend/src/views/BusinessOverview.vue`

- [ ] **Step 1: Write the frontend acceptance target before editing**

Define expected UI fields:
- `预计周转天数`
- `连续积压快照次数`
- `估算积压天数`
- `滞销风险等级`
- `清理优先级`

- [ ] **Step 2: Update API wrappers if needed**

Ensure `frontend/src/api/index.js` and/or `frontend/src/api/dashboard.js` can consume the upgraded backlog and clearance payloads cleanly.

- [ ] **Step 3: Update backlog summary cards**

In `frontend/src/views/BusinessOverview.vue`, keep:
- total inventory value
- 30/60/90 threshold values

But rename any misleading “真实库龄” style wording to:
- `预计周转天数`
- `估算积压天数`

- [ ] **Step 4: Update backlog product table**

Add columns or badges for:
- `estimated_turnover_days`
- `stagnant_snapshot_count`
- `estimated_stagnant_days`
- `risk_level`
- `clearance_priority_score`

- [ ] **Step 5: Update clearance ranking cards/tables**

Ensure ranking clearly communicates “清理优先级” rather than pretending to be true inventory age.

- [ ] **Step 6: Run frontend verification**

Run:
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/index.js frontend/src/api/dashboard.js frontend/src/views/BusinessOverview.vue
git commit -m "feat(frontend): upgrade backlog dashboard with snapshot stagnation metrics"
```

### Task 7: Upgrade Inventory Overview Snapshot Page

**Files:**
- Modify: `frontend/src/views/InventoryOverview.vue`
- Modify: `frontend/src/api/inventoryOverview.js`

- [ ] **Step 1: Add frontend target fields**

Show on the overview page:
- current snapshot
- latest snapshot date
- change vs previous snapshot
- stagnation indicators

- [ ] **Step 2: Update overview API client if needed**

Add methods or params required to fetch snapshot-change-driven data.

- [ ] **Step 3: Update the page copy**

Do not use “真实库龄”.
Use:
- `库存快照`
- `快照变化`
- `连续积压`

- [ ] **Step 4: Run frontend verification**

Run:
- `npm --prefix frontend run type-check`
- `npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/InventoryOverview.vue frontend/src/api/inventoryOverview.js
git commit -m "feat(frontend): add snapshot change metrics to inventory overview"
```

### Task 8: Real Database Refresh And Read-Only Verification

**Files:**
- Optional: update progress artifacts if used

- [ ] **Step 1: Refresh SQL assets in the target database**

Run the project-appropriate SQL refresh/bootstrap path for:
- snapshot history
- latest snapshot
- snapshot change
- backlog summary
- clearance ranking

- [ ] **Step 2: Run read-only verification against the test database**

Verify:
- snapshot history row count
- latest snapshot row count
- snapshot change row count
- backlog summary query succeeds
- clearance ranking query succeeds

- [ ] **Step 3: Run backend verification**

Run:

```bash
pytest backend/tests/data_pipeline/test_inventory_snapshot_change_module.py backend/tests/data_pipeline/test_inventory_backlog_module.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py -v
```

Expected: PASS

- [ ] **Step 4: Run frontend verification**

Run:

```bash
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(backlog): finalize miaoshou snapshot backlog mainline"
```

---

## Notes For Execution

- Keep the current mainline explicitly snapshot-driven. Do not reintroduce real-time sales-driven inventory refresh into this plan.
- If snapshot cadence is 3-7 days, derive stagnation from actual snapshot gaps, not assumed daily intervals.
- Never label these metrics as true inventory age. Preserve the distinction between:
  - `estimated_turnover_days`
  - `stagnant_snapshot_count`
  - `estimated_stagnant_days`
  - true inventory age (future capability)
