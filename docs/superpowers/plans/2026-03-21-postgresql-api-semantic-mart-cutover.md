# PostgreSQL API Semantic Mart Cutover Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用纯 PostgreSQL 的 `semantic` / `mart` / `api` 分层替代 Metabase 在线上主链路中的 Model/Question 职责，保留 `b_class` 原始 JSONB 层、现有 API 契约和前端页面行为。

**Architecture:** 保留 `b_class` 原始异构 JSONB 事实表作为数据落地区；新增 `semantic` 标准化层承接现有 Metabase Model 的字段归一、类型清洗、去重和主数据映射；新增 `mart` 汇总层承接高频复用聚合；新增 `api` 模块视图层替代 Metabase Question 作为前端模块级查询与排障入口。后端逐步从调用 Metabase Question API 切换为直接查询 PostgreSQL 的 `api.*` 视图，并通过特性开关完成双路校验和灰度切换。

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, JSONB, SQL Views/Materialized Views, Alembic, Redis, pytest

---

## File Structure

### New Database SQL
- Create: `sql/semantic/orders_atomic.sql`
- Create: `sql/semantic/analytics_atomic.sql`
- Create: `sql/semantic/products_atomic.sql`
- Create: `sql/semantic/inventory_snapshot.sql`
- Create: `sql/semantic/services_atomic.sql`
- Create: `sql/mart/shop_day_kpi.sql`
- Create: `sql/mart/shop_week_kpi.sql`
- Create: `sql/mart/shop_month_kpi.sql`
- Create: `sql/mart/platform_month_kpi.sql`
- Create: `sql/mart/product_day_kpi.sql`
- Create: `sql/mart/inventory_current.sql`
- Create: `sql/mart/inventory_backlog_base.sql`
- Create: `sql/mart/hr_shop_monthly_profit.sql`
- Create: `sql/mart/annual_summary_shop_month.sql`
- Create: `sql/api_modules/business_overview_kpi_module.sql`
- Create: `sql/api_modules/business_overview_comparison_module.sql`
- Create: `sql/api_modules/business_overview_shop_racing_module.sql`
- Create: `sql/api_modules/business_overview_inventory_backlog_module.sql`
- Create: `sql/api_modules/business_overview_operational_metrics_module.sql`
- Create: `sql/api_modules/clearance_ranking_module.sql`
- Create: `sql/api_modules/annual_summary_kpi_module.sql`
- Create: `sql/api_modules/annual_summary_trend_module.sql`
- Create: `sql/api_modules/annual_summary_platform_share_module.sql`
- Create: `sql/api_modules/annual_summary_by_shop_module.sql`
- Create: `sql/ops/create_pipeline_tables.sql`
- Create: `sql/ops/create_field_alias_rules.sql`

### New Backend Code
- Create: `backend/services/field_alias_rule_service.py`
- Create: `backend/services/postgresql_dashboard_service.py`
- Create: `backend/services/data_pipeline/refresh_registry.py`
- Create: `backend/services/data_pipeline/refresh_runner.py`
- Create: `backend/services/data_pipeline/sql_loader.py`
- Create: `backend/jobs/refresh_semantic_orders.py`
- Create: `backend/jobs/refresh_semantic_analytics.py`
- Create: `backend/jobs/refresh_semantic_products.py`
- Create: `backend/jobs/refresh_semantic_inventory.py`
- Create: `backend/jobs/refresh_semantic_services.py`
- Create: `backend/jobs/refresh_mart_business_overview.py`
- Create: `backend/jobs/refresh_mart_inventory.py`
- Create: `backend/jobs/refresh_mart_annual_summary.py`
- Create: `backend/routers/data_pipeline.py`

### Modified Backend Code
- Modify: `backend/routers/dashboard_api.py`
- Modify: `backend/services/cache_warmup_service.py`
- Modify: `backend/main.py`
- Modify: `backend/models/database.py`
- Modify: `backend/services/data_ingestion_service.py`
- Modify: `backend/services/raw_data_importer.py`
- Modify: `config/metabase_config.yaml`
- Modify: `.env.example`
- Modify: `env.development.example`
- Modify: `env.production.example`

### Tests
- Create: `backend/tests/data_pipeline/test_orders_semantic_mapping.py`
- Create: `backend/tests/data_pipeline/test_analytics_semantic_mapping.py`
- Create: `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`
- Create: `backend/tests/data_pipeline/test_business_overview_module_consistency.py`
- Create: `backend/tests/data_pipeline/test_inventory_backlog_module.py`
- Create: `backend/tests/data_pipeline/test_annual_summary_modules.py`
- Modify: `backend/tests/` existing dashboard contract tests as needed

### Docs
- Create: `docs/superpowers/specs/2026-03-21-postgresql-api-semantic-mart-cutover-design.md` only if a refreshed design doc is required later
- Create: `docs/development/POSTGRESQL_API_LAYER_GUIDE.md`
- Create: `docs/development/DATA_PIPELINE_REFRESH_GUIDE.md`
- Modify: `docs/SEMANTIC_LAYER_DESIGN.md`
- Modify: `docs/DATA_SYNC_ARCHITECTURE.md`

---

## Task 1: Freeze API Contracts And Cutover Scope

**Files:**
- Modify: `backend/routers/dashboard_api.py`
- Create: `docs/development/POSTGRESQL_API_LAYER_GUIDE.md`
- Test: `backend/tests/data_pipeline/test_business_overview_module_consistency.py`

- [ ] **Step 1: Inventory all Metabase-backed dashboard endpoints**

Read and list exact endpoint-to-question mappings from `backend/routers/dashboard_api.py`.
Expected mapping includes:
- `business_overview_kpi`
- `business_overview_comparison`
- `business_overview_shop_racing`
- `business_overview_traffic_ranking`
- `business_overview_inventory_backlog`
- `business_overview_operational_metrics`
- `clearance_ranking`
- `annual_summary_kpi`
- `annual_summary_trend`
- `annual_summary_platform_share`
- `annual_summary_by_shop`

- [ ] **Step 2: Capture current response contract as tests**

Create contract tests that assert key response shapes for representative endpoints.

```python
def test_business_overview_kpi_contract_shape():
    payload = {
        "gmv": 0,
        "order_count": 0,
        "visitor_count": 0,
        "conversion_rate": 0,
        "avg_order_value": 0,
        "attach_rate": 0,
        "labor_efficiency": 0,
    }
    for key in payload:
        assert key in payload
```

- [ ] **Step 3: Run contract tests to establish baseline**

Run: `pytest backend/tests/data_pipeline/test_business_overview_module_consistency.py -q`
Expected: tests pass and define the response shape that PostgreSQL-backed services must keep.

- [ ] **Step 4: Document scope freeze**

Write in `docs/development/POSTGRESQL_API_LAYER_GUIDE.md`:
- first-wave endpoints
- not-in-scope endpoints
- response compatibility rule: no frontend-breaking changes during cutover

- [ ] **Step 5: Commit**

```bash
git add backend/tests/data_pipeline/test_business_overview_module_consistency.py docs/development/POSTGRESQL_API_LAYER_GUIDE.md
git commit -m "docs: freeze dashboard API cutover scope"
```

---

## Task 2: Create Ops Tables For Refresh, Freshness, And Lineage

**Files:**
- Create: `sql/ops/create_pipeline_tables.sql`
- Create: `backend/routers/data_pipeline.py`
- Test: `backend/tests/data_pipeline/test_pipeline_metadata_tables.py`

- [ ] **Step 1: Write failing metadata-table test**

```python
def test_pipeline_tables_exist(sqlalchemy_inspector):
    expected = {
        "pipeline_run_log",
        "pipeline_step_log",
        "data_freshness_log",
        "data_lineage_registry",
    }
    existing = set(sqlalchemy_inspector.get_table_names(schema="ops"))
    assert expected.issubset(existing)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_pipeline_metadata_tables.py -q`
Expected: FAIL because schema/tables are not created yet.

- [ ] **Step 3: Create SQL for `ops` metadata tables**

Create `sql/ops/create_pipeline_tables.sql` with:
- schema creation
- `ops.pipeline_run_log`
- `ops.pipeline_step_log`
- `ops.data_freshness_log`
- `ops.data_lineage_registry`
- indexes on `run_id`, `target_name`, `status`, `updated_at`

- [ ] **Step 4: Add lightweight status router**

Create `backend/routers/data_pipeline.py` with read-only endpoints:
- `GET /api/data-pipeline/status`
- `GET /api/data-pipeline/freshness`
- `GET /api/data-pipeline/lineage`

- [ ] **Step 5: Run tests again**

Run: `pytest backend/tests/data_pipeline/test_pipeline_metadata_tables.py -q`
Expected: PASS after applying migration/test setup.

- [ ] **Step 6: Commit**

```bash
git add sql/ops/create_pipeline_tables.sql backend/routers/data_pipeline.py backend/tests/data_pipeline/test_pipeline_metadata_tables.py
git commit -m "feat: add pipeline metadata tables and status router"
```

---

## Task 3: Assetize Field Alias Rules

**Files:**
- Create: `sql/ops/create_field_alias_rules.sql`
- Create: `backend/services/field_alias_rule_service.py`
- Test: `backend/tests/data_pipeline/test_field_alias_rule_service.py`

- [ ] **Step 1: Write failing field-alias test**

```python
def test_orders_sales_amount_alias_resolution(rule_service):
    aliases = rule_service.get_aliases(platform_code="tiktok", data_domain="orders", standard_field="sales_amount")
    assert "销售金额" in aliases
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_field_alias_rule_service.py -q`
Expected: FAIL because rule table/service does not exist.

- [ ] **Step 3: Create alias-rule table**

Add SQL defining `core.field_alias_rules` with fields:
- `platform_code`
- `data_domain`
- `sub_domain`
- `source_field_name`
- `standard_field_name`
- `parser_type`
- `priority`
- `active`

- [ ] **Step 4: Implement alias-rule service**

Create service methods:
- `get_aliases(platform_code, data_domain, standard_field, sub_domain=None)`
- `get_rules_for_domain(platform_code, data_domain, sub_domain=None)`
- `group_rules_by_standard_field(...)`

- [ ] **Step 5: Seed first-wave rule set**

Seed at least for:
- `orders`
- `analytics`
- `inventory`
- `products`

using alias names currently embedded in Metabase Models.

- [ ] **Step 6: Run tests again**

Run: `pytest backend/tests/data_pipeline/test_field_alias_rule_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sql/ops/create_field_alias_rules.sql backend/services/field_alias_rule_service.py backend/tests/data_pipeline/test_field_alias_rule_service.py
git commit -m "feat: assetize field alias rules"
```

---

## Task 4: Build `semantic.fact_orders_atomic`

**Files:**
- Create: `sql/semantic/orders_atomic.sql`
- Modify: `backend/services/data_ingestion_service.py`
- Test: `backend/tests/data_pipeline/test_orders_semantic_mapping.py`

- [ ] **Step 1: Write failing semantic-orders test**

```python
def test_orders_atomic_exposes_standard_fields(db_session):
    row = db_session.execute(text("select * from semantic.fact_orders_atomic limit 1")).mappings().first()
    assert row is not None
    assert "sales_amount" in row
    assert "paid_amount" in row
    assert "order_id" in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/data_pipeline/test_orders_semantic_mapping.py -q`
Expected: FAIL because `semantic.fact_orders_atomic` does not exist.

- [ ] **Step 3: Create semantic SQL**

Use `orders_model.sql` as source logic, but move into PostgreSQL-owned SQL and structure it as:
- source unions from `b_class.fact_*_orders_*`
- field alias resolution
- numeric/date cleaning
- deduplication
- shop/account mapping
- stable typed output

- [ ] **Step 4: Add refresh entrypoint**

Implement a callable refresh job that:
- creates/replaces the semantic relation
- records run metadata into `ops.pipeline_*`
- updates freshness log

- [ ] **Step 5: Run test again**

Run: `pytest backend/tests/data_pipeline/test_orders_semantic_mapping.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sql/semantic/orders_atomic.sql backend/tests/data_pipeline/test_orders_semantic_mapping.py
git commit -m "feat: add semantic orders atomic layer"
```

---

## Task 5: Build `semantic.fact_analytics_atomic`

**Files:**
- Create: `sql/semantic/analytics_atomic.sql`
- Test: `backend/tests/data_pipeline/test_analytics_semantic_mapping.py`

- [ ] **Step 1: Write failing analytics semantic test**
- [ ] **Step 2: Run it and verify failure**
- [ ] **Step 3: Create `semantic.fact_analytics_atomic` using current `analytics_model.sql` logic**
- [ ] **Step 4: Add refresh job registration**
- [ ] **Step 5: Re-run tests and verify pass**
- [ ] **Step 6: Commit**

Run:
`pytest backend/tests/data_pipeline/test_analytics_semantic_mapping.py -q`

---

## Task 6: Build Remaining Semantic Atomic Relations

**Files:**
- Create: `sql/semantic/products_atomic.sql`
- Create: `sql/semantic/inventory_snapshot.sql`
- Create: `sql/semantic/services_atomic.sql`
- Test: `backend/tests/data_pipeline/test_products_semantic_mapping.py`
- Test: `backend/tests/data_pipeline/test_inventory_semantic_mapping.py`
- Test: `backend/tests/data_pipeline/test_services_semantic_mapping.py`

- [ ] **Step 1: Write failing tests for products/inventory/services semantic layers**
- [ ] **Step 2: Run tests and verify they fail**
- [ ] **Step 3: Port current Metabase Model logic into PostgreSQL semantic SQL files**
- [ ] **Step 4: Register refresh jobs for all three domains**
- [ ] **Step 5: Re-run tests**
- [ ] **Step 6: Commit**

Run:
`pytest backend/tests/data_pipeline/test_products_semantic_mapping.py backend/tests/data_pipeline/test_inventory_semantic_mapping.py backend/tests/data_pipeline/test_services_semantic_mapping.py -q`

---

## Task 7: Build Reusable `mart` Aggregate Layer

**Files:**
- Create: `sql/mart/shop_day_kpi.sql`
- Create: `sql/mart/shop_week_kpi.sql`
- Create: `sql/mart/shop_month_kpi.sql`
- Create: `sql/mart/platform_month_kpi.sql`
- Create: `sql/mart/product_day_kpi.sql`
- Create: `sql/mart/inventory_current.sql`
- Create: `sql/mart/inventory_backlog_base.sql`
- Create: `sql/mart/hr_shop_monthly_profit.sql`
- Create: `sql/mart/annual_summary_shop_month.sql`
- Test: `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`

- [ ] **Step 1: Write failing aggregation tests**

Include assertions such as:
- monthly KPI rows aggregate from semantic facts
- inventory current keeps latest snapshot per sku/shop/platform
- annual summary uses month grain consistently

- [ ] **Step 2: Run tests to confirm failure**
- [ ] **Step 3: Implement `mart` SQL relations with indexes/materialization strategy**
- [ ] **Step 4: Add refresh dependencies (`semantic` -> `mart`)**
- [ ] **Step 5: Run aggregation tests again**
- [ ] **Step 6: Commit**

Run:
`pytest backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py -q`

---

## Task 8: Build `api` Module Views To Replace Questions

**Files:**
- Create: `sql/api_modules/business_overview_kpi_module.sql`
- Create: `sql/api_modules/business_overview_comparison_module.sql`
- Create: `sql/api_modules/business_overview_shop_racing_module.sql`
- Create: `sql/api_modules/business_overview_inventory_backlog_module.sql`
- Create: `sql/api_modules/business_overview_operational_metrics_module.sql`
- Create: `sql/api_modules/clearance_ranking_module.sql`
- Create: `sql/api_modules/annual_summary_kpi_module.sql`
- Create: `sql/api_modules/annual_summary_trend_module.sql`
- Create: `sql/api_modules/annual_summary_platform_share_module.sql`
- Create: `sql/api_modules/annual_summary_by_shop_module.sql`
- Test: `backend/tests/data_pipeline/test_inventory_backlog_module.py`
- Test: `backend/tests/data_pipeline/test_annual_summary_modules.py`

- [ ] **Step 1: Write failing page-module tests**
- [ ] **Step 2: Run tests and verify failure**
- [ ] **Step 3: Port each Question into PostgreSQL module SQL, but make each module depend only on `mart`/`semantic`**
- [ ] **Step 4: Ensure each module can be queried directly for debugging**
- [ ] **Step 5: Re-run tests**
- [ ] **Step 6: Commit**

Run:
`pytest backend/tests/data_pipeline/test_inventory_backlog_module.py backend/tests/data_pipeline/test_annual_summary_modules.py -q`

---

## Task 9: Implement Backend Direct PostgreSQL Query Service

**Files:**
- Create: `backend/services/postgresql_dashboard_service.py`
- Modify: `backend/routers/dashboard_api.py`
- Modify: `backend/services/cache_warmup_service.py`
- Test: `backend/tests/data_pipeline/test_dashboard_postgresql_service.py`

- [ ] **Step 1: Write failing backend service tests**

```python
async def test_dashboard_service_reads_business_overview_kpi_module(service):
    result = await service.get_business_overview_kpi(month="2026-03-01", platform=None)
    assert "gmv" in result
```

- [ ] **Step 2: Run tests and verify failure**
- [ ] **Step 3: Implement PostgreSQL-backed dashboard service**
- [ ] **Step 4: Wire router to feature flag**

Feature flag recommendation:
- `USE_POSTGRESQL_DASHBOARD_API=true|false`

- [ ] **Step 5: Update cache warmup to use PostgreSQL path when enabled**
- [ ] **Step 6: Re-run tests**
- [ ] **Step 7: Commit**

Run:
`pytest backend/tests/data_pipeline/test_dashboard_postgresql_service.py -q`

---

## Task 10: Add Refresh Runner And Dependency Graph

**Files:**
- Create: `backend/services/data_pipeline/refresh_registry.py`
- Create: `backend/services/data_pipeline/refresh_runner.py`
- Create: `backend/services/data_pipeline/sql_loader.py`
- Create: `backend/jobs/refresh_semantic_orders.py`
- Create: `backend/jobs/refresh_semantic_analytics.py`
- Create: `backend/jobs/refresh_mart_business_overview.py`
- Test: `backend/tests/data_pipeline/test_refresh_runner.py`

- [ ] **Step 1: Write failing refresh-runner test**
- [ ] **Step 2: Run and confirm failure**
- [ ] **Step 3: Implement refresh registry with dependency order**

Required dependency order:
- `b_class raw` -> `semantic.*` -> `mart.*` -> `api.*`

- [ ] **Step 4: Implement runner with logging, freshness update, retry hooks**
- [ ] **Step 5: Re-run tests**
- [ ] **Step 6: Commit**

Run:
`pytest backend/tests/data_pipeline/test_refresh_runner.py -q`

---

## Task 11: Dual-Run Validation Against Current Metabase Outputs

**Files:**
- Modify: `backend/routers/dashboard_api.py`
- Create: `backend/tests/data_pipeline/test_metabase_postgresql_parity.py`
- Create: `scripts/compare_metabase_vs_postgresql_modules.py`

- [ ] **Step 1: Write parity tests for first-wave modules**
- [ ] **Step 2: Run to capture current mismatches**
- [ ] **Step 3: Fix semantic/mart/api SQL until parity reaches agreed threshold**
- [ ] **Step 4: Produce comparison report**
- [ ] **Step 5: Commit**

Run:
`pytest backend/tests/data_pipeline/test_metabase_postgresql_parity.py -q`

---

## Task 12: Cut Over, Observe, And Retire Metabase Main Path

**Files:**
- Modify: `backend/main.py`
- Modify: `.env.example`
- Modify: `env.development.example`
- Modify: `env.production.example`
- Modify: `config/metabase_config.yaml`
- Create: `docs/development/DATA_PIPELINE_REFRESH_GUIDE.md`
- Modify: `docs/SEMANTIC_LAYER_DESIGN.md`
- Modify: `docs/DATA_SYNC_ARCHITECTURE.md`

- [ ] **Step 1: Enable PostgreSQL path in non-production**
- [ ] **Step 2: Run full regression**

Run:
`pytest backend/tests/data_pipeline -q`

- [ ] **Step 3: Verify freshness/status endpoints**
- [ ] **Step 4: Update deployment docs and runbook**
- [ ] **Step 5: Disable Metabase for primary dashboard API path**
- [ ] **Step 6: Keep Metabase only for optional internal BI, or remove it entirely if no longer used**
- [ ] **Step 7: Commit**

```bash
git add backend/main.py .env.example env.development.example env.production.example config/metabase_config.yaml docs/development/DATA_PIPELINE_REFRESH_GUIDE.md docs/SEMANTIC_LAYER_DESIGN.md docs/DATA_SYNC_ARCHITECTURE.md
git commit -m "feat: cut over dashboard pipeline to postgresql semantic mart api layers"
```

---

## Verification Checklist

- [ ] `raw -> semantic` mapping tests pass
- [ ] `semantic -> mart` aggregation tests pass
- [ ] `mart/api_module -> backend response` contract tests pass
- [ ] PostgreSQL path matches Metabase outputs for first-wave modules
- [ ] Redis cache still works with PostgreSQL-backed API
- [ ] Refresh logs and freshness endpoints show valid data
- [ ] Frontend pages render without contract changes

## Rollout Strategy

1. Build `semantic` for `orders` and `analytics`
2. Build `mart` + `api` modules for business overview
3. Add backend direct-query path behind feature flag
4. Run Metabase/PostgreSQL parity checks
5. Cut over business overview
6. Repeat for inventory/clearance/annual summary
7. Retire Metabase from production main path

## Non-Goals

- Rewriting raw ingestion storage format
- Removing JSONB from raw layer
- Full BI/self-service replacement in this phase
- Large frontend redesign

## Risks And Mitigations

- **Risk:** semantic logic diverges from current Metabase outputs  
  **Mitigation:** dual-run parity test before cutover

- **Risk:** refresh jobs block online traffic  
  **Mitigation:** asynchronous refresh runner, incremental refresh where possible

- **Risk:** alias rules remain embedded in SQL and drift over time  
  **Mitigation:** move first-wave aliases into `core.field_alias_rules`

- **Risk:** debugging becomes harder after Metabase removal  
  **Mitigation:** preserve page-aligned `api.*_module` views as the new inspection surface

---

Plan complete and saved to `docs/superpowers/plans/2026-03-21-postgresql-api-semantic-mart-cutover.md`. Ready to execute?
