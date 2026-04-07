# Orders RMB Field Preservation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `orders` domain preserve RMB-vs-non-RMB field semantics during template save, header comparison, ingestion normalization, and semantic/model SQL selection, while keeping frontend-facing business field names unchanged.

**Architecture:** Keep the current global normalization behavior for non-`orders` domains. Introduce `orders`-specific preservation rules in the template save path, header diff path, and ingestion normalization path so fields such as `利润(RMB)` can map to stable internal standard names like `profit_rmb` instead of collapsing into `profit`. Update `orders_atomic.sql` and `orders_model.sql` so system-facing fields like `profit` prefer RMB-backed raw fields first and only fall back to legacy non-RMB fields when needed.

**Tech Stack:** FastAPI, SQLAlchemy async, Vue 3 only for unchanged consumers, existing field-mapping/ingestion services, PostgreSQL semantic SQL, pytest, Node `node:test`

---

## File Structure

### Existing files to modify

- `backend/routers/field_mapping_dictionary.py`
  Responsibility: template save path; will stop blindly stripping RMB suffixes for `orders` template headers.
- `backend/services/template_matcher.py`
  Responsibility: header diffing; will treat RMB-vs-non-RMB differences as real field changes in `orders`.
- `backend/services/data_ingestion_service.py`
  Responsibility: row normalization before raw import; will map RMB orders fields to explicit internal standard names and guard against collisions.
- `backend/services/field_mapping/mapper.py`
  Responsibility: alias dictionary; will learn RMB orders source names and their explicit internal mappings.
- `sql/semantic/orders_atomic.sql`
  Responsibility: semantic cleanup; will prioritize RMB-backed raw fields for system-facing business fields.
- `sql/metabase_models/orders_model.sql`
  Responsibility: model layer over orders data; will mirror the RMB-first priority from semantic SQL.

### Existing tests to modify or extend

- `backend/tests/test_field_mapping_template_update_context_api.py`
  Responsibility: extend to prove `orders` header diff logic preserves RMB-vs-non-RMB changes where expected.
- `backend/tests/data_pipeline/test_orders_profit_mapping_sql.py`
  Responsibility: extend to prove RMB-first priority in `profit_raw`.

### New tests to create

- `backend/tests/test_orders_rmb_field_preservation.py`
  Responsibility: lock the ingestion-side collision and normalization behavior for `orders`.
- `backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py`
  Responsibility: verify RMB-backed fields are preferred in semantic/model SQL for the targeted orders business fields.

---

## Task 1: Lock Orders Ingestion Collision Behavior With Failing Tests

**Files:**
- Create: `backend/tests/test_orders_rmb_field_preservation.py`
- Modify: `backend/services/data_ingestion_service.py`

- [ ] **Step 1: Write the failing ingestion preservation tests**

Cover:

- an `orders` row containing both:
  - `利润`
  - `利润(RMB)`
  does not normalize into one silent overwritten key
- an `orders` row containing both:
  - `买家支付`
  - `买家支付(RMB)`
  preserves distinct internal field names
- non-`orders` domains still keep current behavior unless explicitly changed

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
pytest backend/tests/test_orders_rmb_field_preservation.py -q
```

Expected: FAIL because `orders` still uses blind suffix stripping and dict overwrite.

- [ ] **Step 3: Implement the minimal ingestion-side fix**

In `backend/services/data_ingestion_service.py`:

- add an `orders`-specific field-name normalization branch
- map known RMB source names to explicit internal fields, for example:
  - `利润(RMB)` -> `profit_rmb`
  - `订单原始金额(RMB)` -> `original_amount_rmb`
  - `买家支付(RMB)` -> `buyer_payment_rmb`
  - `平台佣金(RMB)` -> `platform_commission_rmb`
  - `预估回款金额(RMB)` -> `estimated_settlement_rmb`
- ensure known legacy non-RMB fields still map to their non-RMB internal counterparts
- detect collisions and fail loudly or log a strong warning instead of silent overwrite

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
pytest backend/tests/test_orders_rmb_field_preservation.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_orders_rmb_field_preservation.py backend/services/data_ingestion_service.py
git commit -m "feat: preserve rmb order fields during ingestion"
```

## Task 2: Preserve Orders RMB Semantics In Template Save And Diff

**Files:**
- Modify: `backend/routers/field_mapping_dictionary.py`
- Modify: `backend/services/template_matcher.py`
- Modify: `backend/tests/test_field_mapping_template_update_context_api.py`

- [ ] **Step 1: Extend the failing tests**

Add assertions showing:

- for `orders`, template headers preserve `利润(RMB)` rather than always normalizing to `利润`
- `利润` vs `利润(RMB)` becomes visible as a real field difference in update-context/header-diff logic

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
```

Expected: FAIL until template save/diff behavior is updated.

- [ ] **Step 3: Implement the minimal template-side fix**

In `backend/routers/field_mapping_dictionary.py`:

- add `orders`-specific template header normalization behavior
- preserve RMB semantic field names instead of blindly removing suffixes

In `backend/services/template_matcher.py`:

- make `orders` header comparison preserve meaningful RMB-vs-non-RMB differences
- keep non-`orders` behavior unchanged

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_field_mapping_template_update_context_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/field_mapping_dictionary.py backend/services/template_matcher.py backend/tests/test_field_mapping_template_update_context_api.py
git commit -m "feat: preserve rmb semantics in orders template diffs"
```

## Task 3: Teach The Alias Dictionary About Orders RMB Source Fields

**Files:**
- Modify: `backend/services/field_mapping/mapper.py`
- Modify or Create: `backend/tests/test_orders_rmb_field_preservation.py`

- [ ] **Step 1: Extend the failing tests**

Cover:

- `利润(RMB)` suggests or maps to `profit_rmb`
- `订单原始金额(RMB)` maps to `original_amount_rmb`
- `买家支付(RMB)` maps to `buyer_payment_rmb`
- `平台佣金(RMB)` maps to `platform_commission_rmb`
- `预估回款金额(RMB)` maps to `estimated_settlement_rmb`

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_orders_rmb_field_preservation.py -q
```

Expected: FAIL until aliases are added.

- [ ] **Step 3: Implement the minimal alias updates**

In `backend/services/field_mapping/mapper.py`:

- add explicit alias entries for the RMB orders source names
- avoid broad global alias changes outside the target orders fields

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_orders_rmb_field_preservation.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/field_mapping/mapper.py backend/tests/test_orders_rmb_field_preservation.py
git commit -m "feat: add orders rmb alias mappings"
```

## Task 4: Make Orders Semantic SQL Prefer RMB-Backed Raw Fields

**Files:**
- Create: `backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py`
- Modify: `sql/semantic/orders_atomic.sql`
- Modify: `sql/metabase_models/orders_model.sql`
- Modify: `backend/tests/data_pipeline/test_orders_profit_mapping_sql.py`

- [ ] **Step 1: Write the failing SQL-priority tests**

Cover:

- `profit_raw` prefers:
  - `利润(RMB)`
  - `profit_rmb`
  before falling back to:
  - `利润`
  - `profit`
  - `毛利`
  - `Profit`
- `estimated_settlement_amount_raw` prefers RMB-backed fields first
- `platform_commission_raw` prefers RMB-backed fields first where applicable
- equivalent behavior exists in both:
  - `orders_atomic.sql`
  - `orders_model.sql`

- [ ] **Step 2: Run the focused SQL tests and verify failure**

Run:

```bash
pytest backend/tests/data_pipeline/test_orders_profit_mapping_sql.py backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py -q
```

Expected: FAIL until SQL fallback order is updated.

- [ ] **Step 3: Implement the minimal SQL priority changes**

In `sql/semantic/orders_atomic.sql`:

- update the relevant `COALESCE(...) AS *_raw` expressions so RMB-backed raw fields are first

In `sql/metabase_models/orders_model.sql`:

- mirror the same priority order

Do not rename the exposed business fields in this phase.

- [ ] **Step 4: Re-run the focused SQL tests**

Run:

```bash
pytest backend/tests/data_pipeline/test_orders_profit_mapping_sql.py backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/semantic/orders_atomic.sql sql/metabase_models/orders_model.sql backend/tests/data_pipeline/test_orders_profit_mapping_sql.py backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py
git commit -m "feat: prioritize orders rmb fields in semantic sql"
```

## Task 5: Full Verification

**Files:**
- Verify: `backend/routers/field_mapping_dictionary.py`
- Verify: `backend/services/template_matcher.py`
- Verify: `backend/services/data_ingestion_service.py`
- Verify: `backend/services/field_mapping/mapper.py`
- Verify: `sql/semantic/orders_atomic.sql`
- Verify: `sql/metabase_models/orders_model.sql`
- Verify: `backend/tests/test_orders_rmb_field_preservation.py`
- Verify: `backend/tests/test_field_mapping_template_update_context_api.py`
- Verify: `backend/tests/data_pipeline/test_orders_profit_mapping_sql.py`
- Verify: `backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py`

- [ ] **Step 1: Run the targeted backend tests**

Run:

```bash
pytest backend/tests/test_orders_rmb_field_preservation.py backend/tests/test_field_mapping_template_update_context_api.py -q
```

Expected: PASS

- [ ] **Step 2: Run the targeted SQL/data-pipeline tests**

Run:

```bash
pytest backend/tests/data_pipeline/test_orders_profit_mapping_sql.py backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py -q
```

Expected: PASS

- [ ] **Step 3: Run one broader relevant regression slice**

Run:

```bash
pytest backend/tests -q -k "orders and (profit or template_update_context)"
```

Expected: PASS, or if there are pre-existing unrelated failures, record them explicitly before completion.

- [ ] **Step 4: Manual verification checklist**

Verify:

- an `orders` template can preserve RMB field names where business meaning differs
- `利润` and `利润(RMB)` are surfaced as distinct when appropriate
- ingesting an `orders` file with both fields no longer silently loses one value
- semantic/model SQL still exposes `profit` to downstream consumers
- frontend labels remain unchanged

- [ ] **Step 5: Final commit**

```bash
git add backend/routers/field_mapping_dictionary.py backend/services/template_matcher.py backend/services/data_ingestion_service.py backend/services/field_mapping/mapper.py sql/semantic/orders_atomic.sql sql/metabase_models/orders_model.sql backend/tests/test_orders_rmb_field_preservation.py backend/tests/test_field_mapping_template_update_context_api.py backend/tests/data_pipeline/test_orders_profit_mapping_sql.py backend/tests/data_pipeline/test_orders_rmb_field_priority_sql.py
git commit -m "feat: preserve orders rmb field semantics"
```

## Implementation Notes

- Keep this work scoped to `orders`.
- Do not rename frontend-facing business fields in this phase.
- Prefer explicit field mapping over broad currency-suffix stripping.
- Do not silently merge `xxx` and `xxx(RMB)` into one normalized key for `orders`.
