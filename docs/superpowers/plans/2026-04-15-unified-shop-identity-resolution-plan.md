# Unified Shop Identity Resolution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `orders` 和 `analytics` 在进入 semantic 层时先映射到统一店铺主档，后续 `mart/api` 只使用统一后的标准店铺键，消除业务概览中的重复店铺和伪未匹配店铺。

**Architecture:** 以 `core.shop_accounts` 为唯一店铺身份证主表，统一解析顺序为“平台店铺ID -> 店铺账号ID -> 激活别名 -> 店铺名称弱匹配 -> 未解析”。`orders` 与 `analytics` 共用同一套解析规则，并在 semantic 层输出统一 `shop_id` 与解析元数据；`mart.shop_*_kpi`、`api.business_overview_*` 等聚合层只消费统一后的 `shop_id`。

**Tech Stack:** PostgreSQL views, FastAPI backend, SQLAlchemy async tests, pytest, data pipeline refresh runner

---

## File Map

**Create:**
- `sql/semantic/shop_identity_resolution_candidates.sql`
- `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`
- `backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py`

**Modify:**
- `sql/semantic/analytics_atomic.sql`
- `sql/semantic/analytics_monthly_atomic.sql`
- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic.sql`
- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`
- `sql/api_modules/business_overview_shop_racing_module.sql`
- `sql/api_modules/business_overview_traffic_ranking_module.sql`
- `backend/services/data_pipeline/refresh_registry.py`
- `backend/domains/collection/routers/shop_account_aliases.py`
- `frontend/src/views/BusinessOverview.vue`

**Reference:**
- `modules/core/db/schema.py`
- `backend/services/postgresql_dashboard_service.py`

## Design Rules

- 统一标准店铺键继续使用 `shop_id`
- semantic 层新增解析元数据字段：
  - `resolved_shop_account_id`
  - `resolution_method`
  - `identity_source_value`
- 统一解析优先级：
  1. `platform_shop_id`
  2. `shop_account_id`
  3. `shop_account_aliases.alias_normalized`
  4. `shop_accounts.store_name` 弱匹配
  5. unresolved
- unresolved 需要区分：
  - `missing_identity`: 原始数据没有可用身份字段
  - `unclaimed_identity`: 有值但主档未认领
- 页面端只展示统一后的店铺；若仍 unresolved，显示明确原因，不与正常店铺并排混淆

## Task 1: Build Shared Shop Identity Resolution Layer

**Files:**
- Create: `sql/semantic/shop_identity_resolution_candidates.sql`
- Test: `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`

- [ ] **Step 1: Write the failing SQL asset test**

```python
def test_shop_identity_resolution_sql_asset():
    text = Path("sql/semantic/shop_identity_resolution_candidates.sql").read_text(encoding="utf-8")
    assert "core.shop_accounts" in text
    assert "core.shop_account_aliases" in text
    assert "platform_shop_id" in text
    assert "shop_account_id" in text
    assert "resolution_method" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/data_pipeline/test_shop_identity_resolution_sql.py -q`
Expected: FAIL because the SQL file does not exist yet

- [ ] **Step 3: Create the shared resolution SQL**

Implementation requirements:
- produce a reusable view that takes normalized candidate identity values
- join `core.shop_accounts`
- join `core.shop_account_aliases`
- expose:
  - `platform_code`
  - `candidate_platform_shop_id`
  - `candidate_shop_account_id`
  - `candidate_store_label`
  - `resolved_shop_id`
  - `resolved_shop_account_id`
  - `resolution_method`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/data_pipeline/test_shop_identity_resolution_sql.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/semantic/shop_identity_resolution_candidates.sql backend/tests/data_pipeline/test_shop_identity_resolution_sql.py
git commit -m "feat: add shared shop identity resolution sql"
```

## Task 2: Align Analytics Semantic Layer to Shop Accounts

**Files:**
- Modify: `sql/semantic/analytics_atomic.sql`
- Modify: `sql/semantic/analytics_monthly_atomic.sql`
- Test: `backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py`

- [ ] **Step 1: Write the failing analytics alignment test**

```python
@pytest.mark.asyncio
async def test_analytics_semantic_prefers_account_identity_over_raw_store_name():
    # seed core.shop_accounts + core.shop_account_aliases
    # seed analytics raw rows with platform_shop_id/shop_account_id/store_name variants
    # assert semantic output shop_id equals canonical shop account mapping
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py -q`
Expected: FAIL because analytics semantic still keeps raw shop labels

- [ ] **Step 3: Implement analytics identity resolution**

Implementation requirements:
- normalize raw analytics identity candidates:
  - `platform_shop_id`
  - `shop_account_id`
  - `store_label_raw`
- resolve against shared identity rules
- replace current direct `shop_id` assignment with resolved canonical `shop_id`
- preserve raw values in side fields for audit/debug

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/semantic/analytics_atomic.sql sql/semantic/analytics_monthly_atomic.sql backend/tests/data_pipeline/test_analytics_shop_identity_alignment.py
git commit -m "feat: align analytics semantic shop identity to accounts"
```

## Task 3: Refactor Orders Semantic Layer to Use the Same Resolution Rules

**Files:**
- Modify: `sql/semantic/orders_atomic.sql`
- Modify: `sql/semantic/orders_monthly_atomic.sql`
- Test: `backend/tests/data_pipeline/test_orders_semantic_mapping.py`

- [ ] **Step 1: Extend/adjust failing tests for direct account-first behavior**

Add cases that prove:
- when order row includes direct platform/account identity, it should resolve without alias
- alias remains valid fallback
- unresolved rows distinguish missing identity vs unclaimed identity

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_orders_semantic_mapping.py -q`
Expected: FAIL on new assertions

- [ ] **Step 3: Implement orders shared identity resolution**

Implementation requirements:
- keep current alias behavior as fallback only
- attempt account identity resolution before alias
- emit the same metadata fields as analytics semantic

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python -m pytest backend/tests/data_pipeline/test_orders_semantic_mapping.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/semantic/orders_atomic.sql sql/semantic/orders_monthly_atomic.sql backend/tests/data_pipeline/test_orders_semantic_mapping.py
git commit -m "refactor: unify orders shop identity resolution"
```

## Task 4: Rebuild Mart Shop KPI Layers on Canonical Shop IDs

**Files:**
- Modify: `sql/mart/shop_day_kpi.sql`
- Modify: `sql/mart/shop_week_kpi.sql`
- Modify: `sql/mart/shop_month_kpi.sql`
- Test: `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`
- Test: `backend/tests/data_pipeline/test_granularity_alignment_sql.py`

- [ ] **Step 1: Add failing mart regression test**

Target behavior:
- same logical shop from orders + analytics collapses into one row
- raw analytics-only labels no longer produce duplicate shop KPI rows

- [ ] **Step 2: Run targeted mart tests and verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`
Expected: FAIL on new duplicate-collapse assertions

- [ ] **Step 3: Update mart views**

Implementation requirements:
- consume unified semantic `shop_id`
- keep FULL OUTER JOIN behavior only across canonical shop ids
- do not allow raw label-only shop ids to bypass canonical mapping

- [ ] **Step 4: Run mart tests to verify pass**

Run: `python -m pytest backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py backend/tests/data_pipeline/test_granularity_alignment_sql.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/mart/shop_day_kpi.sql sql/mart/shop_week_kpi.sql sql/mart/shop_month_kpi.sql backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py backend/tests/data_pipeline/test_granularity_alignment_sql.py
git commit -m "refactor: rebuild shop mart kpis on canonical shop ids"
```

## Task 5: Fix Dashboard API Modules That Surface Duplicate Shops

**Files:**
- Modify: `sql/api_modules/business_overview_shop_racing_module.sql`
- Modify: `sql/api_modules/business_overview_traffic_ranking_module.sql`
- Modify: `backend/services/data_pipeline/refresh_registry.py`
- Test: `backend/tests/data_pipeline/test_remaining_dashboard_modules.py`
- Test: `backend/tests/data_pipeline/test_postgresql_dashboard_service.py`

- [ ] **Step 1: Write failing dashboard regression test**

Target behavior:
- `shop-racing` returns canonical shop rows only
- `traffic-ranking` returns canonical shop rows only
- unresolved rows, if any, carry explicit unresolved reason

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_remaining_dashboard_modules.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py -k "shop_racing or traffic_ranking" -q`
Expected: FAIL on duplicate/unresolved assertions

- [ ] **Step 3: Implement API module alignment**

Implementation requirements:
- keep API modules thin; do not reintroduce raw label logic
- let display name come from canonical shop/account metadata
- if unresolved rows remain, mark them clearly and do not merge with canonical rows

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/data_pipeline/test_remaining_dashboard_modules.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py -k "shop_racing or traffic_ranking" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/api_modules/business_overview_shop_racing_module.sql sql/api_modules/business_overview_traffic_ranking_module.sql backend/services/data_pipeline/refresh_registry.py backend/tests/data_pipeline/test_remaining_dashboard_modules.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py
git commit -m "fix: remove duplicate shops from dashboard modules"
```

## Task 6: Improve Unmatched Alias Diagnostics

**Files:**
- Modify: `backend/domains/collection/routers/shop_account_aliases.py`
- Modify: `frontend/src/views/BusinessOverview.vue`
- Test: `backend/tests/test_shop_account_aliases_api.py`

- [ ] **Step 1: Write failing API contract test**

Target behavior:
- unmatched endpoint returns reason category:
  - `missing_identity`
  - `unclaimed_identity`
- endpoint can optionally include analytics-origin unresolved items

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python -m pytest backend/tests/test_shop_account_aliases_api.py -q`
Expected: FAIL on new response shape

- [ ] **Step 3: Implement diagnostics changes**

Implementation requirements:
- keep backward-compatible fields if frontend depends on them
- add explicit unresolved source and reason
- in `BusinessOverview.vue`, unmatched dialog should show the reason instead of only raw alias text

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/test_shop_account_aliases_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/collection/routers/shop_account_aliases.py frontend/src/views/BusinessOverview.vue backend/tests/test_shop_account_aliases_api.py
git commit -m "feat: classify unmatched shop identities"
```

## Task 7: Refresh Pipeline and Run End-to-End Validation

**Files:**
- Modify: none required unless validation exposes gaps
- Test: existing pipeline/dashboard tests

- [ ] **Step 1: Refresh affected SQL targets**

Run:

```bash
python - <<'PY'
import asyncio
from backend.models.database import AsyncSessionLocal
from backend.services.data_pipeline.refresh_runner import execute_sql_target

TARGETS = [
    "semantic.fact_orders_atomic",
    "semantic.fact_orders_monthly_atomic",
    "semantic.fact_analytics_atomic",
    "semantic.fact_analytics_monthly_atomic",
    "mart.shop_day_kpi",
    "mart.shop_week_kpi",
    "mart.shop_month_kpi",
    "api.business_overview_shop_racing_module",
    "api.business_overview_traffic_ranking_module",
]

async def main():
    async with AsyncSessionLocal() as session:
        for target in TARGETS:
            await execute_sql_target(session, target)
        await session.commit()

asyncio.run(main())
PY
```

Expected: all targets refresh successfully

- [ ] **Step 2: Run end-to-end targeted tests**

Run:

```bash
python -m pytest backend/tests/data_pipeline/test_business_overview_module_consistency.py backend/tests/data_pipeline/test_postgresql_dashboard_router.py backend/tests/data_pipeline/test_postgresql_dashboard_service.py -k "comparison or shop_racing or traffic_ranking or kpi" -q
```

Expected: PASS

- [ ] **Step 3: Run real-data inspection queries**

Check:
- duplicated logical shops disappear from `api.business_overview_shop_racing_module`
- analytics-only raw labels no longer produce separate canonical rows
- unresolved rows only remain for true missing/unclaimed identities

- [ ] **Step 4: Capture results in progress files**

Document:
- how many duplicate shops disappeared
- how many unresolved rows remain
- which unresolved rows are true source-data gaps

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: unify shop identity resolution across orders and analytics"
```

## Validation Checklist

- [ ] Same logical shop no longer appears once as canonical ID and once as raw analytics name
- [ ] `shop-racing` no longer shows 0-GMV duplicate rows caused by analytics raw labels
- [ ] unresolved rows are explicitly classified
- [ ] `orders` alias mapping still works
- [ ] `analytics` direct account mapping works
- [ ] KPI/comparison/traffic/shop-racing tests remain green

## Risks

- `analytics` raw data may not consistently expose stable account identifiers across all platforms
- existing dashboards may rely on current raw label behavior for some edge-case rows
- dropping/recreating semantic/api views can break refresh ordering if registry is incomplete

## Rollback Strategy

- restore previous semantic SQL for orders/analytics
- refresh affected mart/api targets in dependency order
- verify dashboard contract tests return to previous shape

Plan complete and saved to `docs/superpowers/plans/2026-04-15-unified-shop-identity-resolution-plan.md`. Ready to execute?

