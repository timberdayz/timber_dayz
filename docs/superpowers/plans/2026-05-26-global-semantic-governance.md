# Global Semantic Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a stable, explicit semantic field governance system across all sync domains, and fully land the first-domain `analytics` rules in semantic SQL and tests without violating the raw-first contract.

**Architecture:** Keep raw ingestion unchanged after the contract-alignment work, and move all business-semantic field merge/split behavior into explicit semantic-layer assets. Use `docs/architecture/SEMANTIC_FIELD_RULES.md` as the design baseline, implement the first concrete SQL closure in `analytics_atomic.sql` and `analytics_monthly_atomic.sql`, then extend the same method to `orders`, `products`, `services`, and `inventory` in later tasks.

**Tech Stack:** PostgreSQL SQL views, FastAPI backend, pytest, async SQLAlchemy, architecture docs

---

## File Structure

- Modify: `docs/architecture/SEMANTIC_FIELD_RULES.md`
  - Expand from first-wave notes into a domain-by-domain active governance reference.
- Modify: `sql/semantic/analytics_atomic.sql`
  - Replace implicit same-file merge behavior with explicit split/merge outputs.
- Modify: `sql/semantic/analytics_monthly_atomic.sql`
  - Align monthly analytics semantic fields to the same rule set as daily analytics.
- Create: `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`
  - New focused tests for analytics split-vs-merge behavior.
- Modify: `backend/tests/data_pipeline/test_analytics_semantic_mapping.py`
  - Extend asset and field coverage assertions.
- Modify: `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`
  - Keep downstream mart expectations aligned with the retained canonical fields.
- Modify: `docs/superpowers/specs/2026-05-26-global-semantic-governance-design.md`
  - Update only if implementation reveals a missing decision.

## Task 1: Lock Analytics Semantic Split Rules With Failing SQL Tests

**Files:**
- Create: `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`
- Test: `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`

- [ ] **Step 1: Write the failing asset-level test for analytics split outputs**

```python
from pathlib import Path


def test_analytics_atomic_sql_exposes_split_fields_for_tiktok_same_file_metrics():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "sku_order_count" in sql_text
    assert "total_transaction_amount" in sql_text
    assert "product_visitor_count" in sql_text
```

- [ ] **Step 2: Write the failing test that `SKU 订单数` no longer feeds `order_count_raw`**

```python
def test_analytics_atomic_sql_does_not_merge_sku_order_count_into_order_count():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'SKU 订单数'" not in sql_text.split("AS order_count_raw")[0]
```
```

- [ ] **Step 3: Write the failing test that `总成交额` no longer feeds `gmv_raw`**

```python
def test_analytics_atomic_sql_does_not_merge_total_transaction_amount_into_gmv():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'总成交额'" not in sql_text.split("AS gmv_raw")[0]
```

- [ ] **Step 4: Write the failing test that `商品访客数` no longer feeds `visitor_count_raw`**

```python
def test_analytics_atomic_sql_does_not_merge_product_visitor_count_into_visitor_count():
    sql_text = Path("sql/semantic/analytics_atomic.sql").read_text(encoding="utf-8")

    assert "raw_data->>'商品访客数'" not in sql_text.split("AS visitor_count_raw")[0]
```

- [ ] **Step 5: Run tests to verify failure**

Run: `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py -v`
Expected: FAIL because the current SQL still performs implicit merges.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py
git commit -m "test: lock analytics semantic split rules"
```

## Task 2: Implement Analytics Daily Semantic Split/Merge Rules

**Files:**
- Modify: `sql/semantic/analytics_atomic.sql`
- Test: `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`
- Test: `backend/tests/data_pipeline/test_analytics_semantic_mapping.py`

- [ ] **Step 1: Split `order_count` and `sku_order_count` in `mapped` CTE**

Update `mapped` so:

```sql
COALESCE(
    raw_data->>'订单数',
    raw_data->>'订单数量',
    raw_data->>'order_count',
    raw_data->>'Order Count'
) AS order_count_raw,
COALESCE(
    raw_data->>'SKU 订单数',
    raw_data->>'sku_order_count',
    raw_data->>'SKU Order Count'
) AS sku_order_count_raw,
```

Do not include `SKU 订单数` in `order_count_raw`.

- [ ] **Step 2: Split `gmv` and `total_transaction_amount` in `mapped` CTE**

Update `mapped` so:

```sql
COALESCE(
    raw_data->>'GMV',
    raw_data->>'gmv'
) AS gmv_raw,
COALESCE(
    raw_data->>'总成交额',
    raw_data->>'成交金额',
    raw_data->>'sales_amount'
) AS total_transaction_amount_raw,
```

Do not let `总成交额` feed `gmv_raw`.

- [ ] **Step 3: Split `visitor_count` and `product_visitor_count` in `mapped` CTE**

Update `mapped` so:

```sql
COALESCE(
    raw_data->>'访客数',
    raw_data->>'独立访客',
    raw_data->>'uv',
    raw_data->>'visitor_count'
) AS visitor_count_raw,
COALESCE(
    raw_data->>'商品访客数',
    raw_data->>'product_visitor_count',
    raw_data->>'Product Visitor Count'
) AS product_visitor_count_raw,
```

Do not let `商品访客数` feed `visitor_count_raw`.

- [ ] **Step 4: Add cleaned numeric projections and final output columns**

Add:

```sql
CASE ... END AS sku_order_count,
CASE ... END AS total_transaction_amount,
CASE ... END AS product_visitor_count,
```

and include them in the final `SELECT`.

- [ ] **Step 5: Extend analytics asset test**

In `backend/tests/data_pipeline/test_analytics_semantic_mapping.py`, extend the expected field list with:

```python
"sku_order_count",
"total_transaction_amount",
"product_visitor_count",
```

- [ ] **Step 6: Run focused tests**

Run:
- `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py -v`
- `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_mapping.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add sql/semantic/analytics_atomic.sql backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py backend/tests/data_pipeline/test_analytics_semantic_mapping.py
git commit -m "feat: make analytics semantic split same-file metrics explicitly"
```

## Task 3: Align Analytics Monthly Semantic View To The Same Rules

**Files:**
- Modify: `sql/semantic/analytics_monthly_atomic.sql`
- Test: `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`
- Test: `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`

- [ ] **Step 1: Add missing monthly analytics semantic fields**

`analytics_monthly_atomic.sql` currently only exposes traffic-oriented monthly fields. Extend it to expose:

- `gmv`
- `order_count`
- `sku_order_count`
- `total_transaction_amount`
- `product_visitor_count`

using the same explicit split-vs-merge rules as daily analytics.

- [ ] **Step 2: Preserve existing canonical fields consumed downstream**

Keep these monthly fields intact:

- `visitor_count`
- `page_views`

This prevents downstream mart breakage.

- [ ] **Step 3: Extend monthly asset tests**

In `backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py`, update the analytics monthly asset assertion to require:

```python
"gmv",
"order_count",
"sku_order_count",
"total_transaction_amount",
"product_visitor_count",
```

- [ ] **Step 4: Add/extend SQL text assertions**

In `backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py`, add a monthly companion assertion:

```python
def test_analytics_monthly_atomic_sql_exposes_split_fields():
    sql_text = Path("sql/semantic/analytics_monthly_atomic.sql").read_text(encoding="utf-8")
    for field_name in ("gmv", "order_count", "sku_order_count", "total_transaction_amount", "product_visitor_count"):
        assert field_name in sql_text
```

- [ ] **Step 5: Run focused tests**

Run:
- `python -m pytest backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py -v`
- `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add sql/semantic/analytics_monthly_atomic.sql backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py
git commit -m "feat: align analytics monthly semantic rules with global governance"
```

## Task 4: Update Semantic Field Rule Documentation For Analytics Closure

**Files:**
- Modify: `docs/architecture/SEMANTIC_FIELD_RULES.md`
- Modify: `docs/superpowers/specs/2026-05-26-global-semantic-governance-design.md`

- [ ] **Step 1: Mark analytics split rules as implemented**

Add a short implementation note under analytics rules:

```markdown
Status: Implemented in `sql/semantic/analytics_atomic.sql` and `sql/semantic/analytics_monthly_atomic.sql` on 2026-05-26.
```

- [ ] **Step 2: Update the design spec only if SQL implementation required rule clarification**

Do not expand scope. Only clarify what the implementation forced you to state explicitly.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/SEMANTIC_FIELD_RULES.md docs/superpowers/specs/2026-05-26-global-semantic-governance-design.md
git commit -m "docs: record analytics semantic governance closure"
```

## Task 5: Write The Orders Domain Closure Plan Stub

**Files:**
- Modify: `docs/architecture/SEMANTIC_FIELD_RULES.md`
- Modify: `docs/superpowers/specs/2026-05-26-global-semantic-governance-design.md`

- [ ] **Step 1: Add an explicit “next domain” section for orders**

Document that orders remains next because:

- it already has historical implicit merge rules
- it already has RMB priority behavior
- it now needs iron-law review against same-file coexisting metrics

- [ ] **Step 2: Add explicit pending orders review items**

Add these review targets:

- `sales_amount` source group
- `paid_amount` source group
- `profit` source group
- RMB priority fields
- any same-file coexisting order metrics that must split instead of merge

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/SEMANTIC_FIELD_RULES.md docs/superpowers/specs/2026-05-26-global-semantic-governance-design.md
git commit -m "docs: prepare orders semantic governance follow-up"
```

## Verification Checklist

- [ ] Run: `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_field_rules_sql.py -v`
- [ ] Run: `python -m pytest backend/tests/data_pipeline/test_analytics_semantic_mapping.py -v`
- [ ] Run: `python -m pytest backend/tests/data_pipeline/test_shop_month_kpi_aggregation.py -v`
- [ ] Run targeted downstream analytics-related SQL tests if failures indicate dependency impact
- [ ] Re-run the existing data-sync contract suite if analytics semantic changes reveal shared assumptions

## Risks

- downstream marts may assume `analytics_monthly_atomic` only exposes traffic fields
- existing dashboards may implicitly rely on current merged behavior
- some aliases currently living inside `analytics_atomic.sql` may need to be downgraded from merge to split
- orders closure may reveal more historical ambiguity than analytics

## Out Of Scope

- orders SQL changes in this plan
- products/services/inventory SQL changes in this plan
- migration to `core.field_alias_rules`
- full dashboard mart recomputation redesign
