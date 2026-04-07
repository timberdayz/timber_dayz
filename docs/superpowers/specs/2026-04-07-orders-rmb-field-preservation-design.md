# Orders RMB Field Preservation Design

**Date:** 2026-04-07

**Goal:** Preserve RMB-suffixed monetary fields in the `orders` domain during template save, template comparison, ingestion normalization, and SQL model selection, while keeping the system-facing business field names and frontend labels unchanged.

## 1. Background

The current data-sync pipeline has three distinct stages:

1. file sync and raw ingestion into B-class raw tables
2. semantic/model SQL cleanup over raw data
3. backend API and frontend consumption of system-facing business fields

For `orders`, the business intent is now clearer than before:

- source files may include both original-currency fields and RMB fields
- RMB fields are the trusted business source for many metrics
- the system should continue exposing stable business names such as:
  - `profit`
  - `buyer_payment`
  - `original_amount`
  - `platform_commission`
  - `estimated_settlement`

This means the required change is not a frontend renaming exercise. It is an ingestion and model-priority correction exercise.

## 2. Current Problem

The current pipeline aggressively strips currency suffixes during normalization.

This is acceptable for many domains, but it is unsafe for `orders` now that fields like:

- `利润`
- `利润(RMB)`

can coexist in the same source dataset.

Today, the pipeline tends to collapse both into the same normalized key. The practical risk is not “two profit columns stored separately.” The risk is worse:

- both source fields normalize to the same key
- the later value silently overwrites the earlier value
- the system loses the distinction between original-currency and RMB business meaning

The same risk applies to other money fields, such as:

- `订单原始金额(RMB)`
- `买家支付(RMB)`
- `平台佣金(RMB)`
- `预估回款金额(RMB)`

## 3. Confirmed Current Evidence

### 3.1 Orders collector/schema already distinguishes RMB variants

The collector-side schema already models distinct RMB variants such as:

- `profit_rmb`
- `original_amount_rmb`
- `buyer_payment_rmb`
- `platform_commission_rmb`
- `estimated_settlement_rmb`

See:

- `modules/collectors/shopee_data_schema.py`

### 3.2 Template save currently strips currency suffixes

Template `header_columns` are normalized through `CurrencyExtractor.normalize_field_list(...)`, which removes currency suffixes before template persistence.

This means `利润(RMB)` may be saved as `利润` in template headers.

See:

- `backend/routers/field_mapping_dictionary.py`

### 3.3 Template comparison also treats currency suffix differences as non-differences

Header change detection currently normalizes template and current headers before comparison, so `利润` and `利润(RMB)` can be treated as equivalent.

See:

- `backend/services/template_matcher.py`

### 3.4 Ingestion normalization can silently overwrite RMB and non-RMB fields

During row normalization, the ingestion path currently normalizes field names and writes them into a single `normalized_row` dict.

If two source keys normalize to the same output key, the latter silently overwrites the former.

See:

- `backend/services/data_ingestion_service.py`

### 3.5 Downstream SQL still prefers old raw names

`orders_atomic.sql` and `orders_model.sql` currently build `profit_raw` primarily from:

- `利润`
- `profit`
- `毛利`
- `Profit`

This means even if RMB values are present upstream, the SQL layer is not yet explicitly prioritizing them.

See:

- `sql/semantic/orders_atomic.sql`
- `sql/metabase_models/orders_model.sql`

## 4. Non-Goals

This change should **not**:

- rename frontend labels from `利润` to `利润(RMB)`
- redesign unrelated domains such as `products`, `inventory`, or `services`
- globally disable currency normalization for every domain
- redesign all financial reporting in one pass

The target is specifically `orders` domain correctness with minimal collateral impact.

## 5. Design Goals

1. Preserve RMB-vs-non-RMB distinction for `orders`.
2. Avoid silent key collisions during ingestion normalization.
3. Keep frontend-facing business names stable.
4. Make semantic/model SQL prefer RMB-backed values where they are the trusted source.
5. Avoid changing other domains unless required.

## 6. Options Considered

### 6.1 Option A: Global stop stripping currency suffixes

Pros:

- straightforward conceptual change
- preserves all suffix information everywhere

Cons:

- too risky across all domains
- likely to break established template matching and ingestion assumptions elsewhere
- violates the goal of minimizing impact

### 6.2 Option B: Recommended

Apply a domain-specific rule for `orders`:

- stop blindly stripping RMB suffixes where semantic distinction matters
- map known RMB fields to explicit system-internal standard names
- keep other domains on the existing normalization behavior

Pros:

- smallest safe blast radius
- fixes the concrete `orders` problem directly
- preserves existing behavior for domains that currently rely on aggressive normalization

Cons:

- introduces domain-conditional normalization logic
- requires coordinated changes in ingestion and SQL layers

### 6.3 Option C: Leave ingestion unchanged and only patch SQL fallback order

Pros:

- smallest SQL-only change

Cons:

- does not solve silent overwrite during ingestion normalization
- only hides the upstream data-loss risk

### 6.4 Recommendation

Choose **Option B**.

This is the only option that solves both:

- upstream field-collision risk
- downstream business-field priority

without broad regressions in other domains.

## 7. Recommended Architecture

## 7.1 Preserve Source Semantics In Orders

For `orders`, monetary fields with RMB semantics must remain distinct during normalization.

Conceptually:

- `利润` -> `profit`
- `利润(RMB)` -> `profit_rmb`
- `订单原始金额` -> `original_amount`
- `订单原始金额(RMB)` -> `original_amount_rmb`
- `买家支付` -> `buyer_payment`
- `买家支付(RMB)` -> `buyer_payment_rmb`
- `平台佣金` -> `platform_commission`
- `平台佣金(RMB)` -> `platform_commission_rmb`
- `预估回款金额` -> `estimated_settlement`
- `预估回款金额(RMB)` -> `estimated_settlement_rmb`

This preserves meaning while still giving the system stable internal field codes.

## 7.2 Keep Frontend Business Names Stable

Downstream business fields exposed by semantic/model SQL should still be:

- `profit`
- `original_amount`
- `buyer_payment`
- `platform_commission`
- `estimated_settlement`

The only change is that SQL should now prefer the RMB-specific upstream raw fields where those are the trusted business source.

That means frontend pages and most API consumers do not need display-name changes.

## 7.3 Domain-Specific Behavior Boundary

The domain-specific rule should be explicit:

- `orders`: preserve and map RMB semantic fields
- other domains: keep current normalization unless separately redesigned

This boundary is critical to avoid accidental regressions.

## 8. Required Change Areas

## 8.1 Template Save

File:

- `backend/routers/field_mapping_dictionary.py`

Current issue:

- template `header_columns` are normalized by removing currency codes before save

Required change:

- for `orders`, do not blindly erase `(RMB)` from semantically significant fields
- template headers must preserve enough information for manual update, diff review, and field-pool correctness

## 8.2 Template Comparison

File:

- `backend/services/template_matcher.py`

Current issue:

- currency-suffix differences are normalized away before diffing

Required change:

- for `orders`, `利润` vs `利润(RMB)` and similar pairs must be treated as real differences

This ensures the manual-update UI can surface meaningful field changes.

## 8.3 Ingestion Normalization

File:

- `backend/services/data_ingestion_service.py`

Current issue:

- normalized row keys can collide after suffix stripping

Required change:

- for `orders`, replace blind suffix stripping with explicit standard-name mapping for known RMB fields
- add collision detection so two source fields cannot silently overwrite into the same normalized key

## 8.4 Alias / Mapping Dictionary

File:

- `backend/services/field_mapping/mapper.py`

Required change:

- add explicit aliases for RMB orders fields so dictionary-based and suggestion-based flows understand the new source naming

## 8.5 Orders Semantic SQL

Files:

- `sql/semantic/orders_atomic.sql`
- `sql/metabase_models/orders_model.sql`

Required change:

- system-facing fields like `profit`, `buyer_payment`, `original_amount`, `platform_commission`, and `estimated_settlement` should prefer RMB-specific upstream fields first
- only fall back to legacy non-RMB fields when RMB fields are absent

## 9. Safety Rules

1. No global change to all domains.
2. No silent overwrite when two normalized source keys collide.
3. No frontend label rename in this phase.
4. No assumption that old and RMB fields are equivalent for `orders`.

## 10. Acceptance Criteria

1. An `orders` source file containing both `利润` and `利润(RMB)` no longer loses one value through normalization collision.
2. `orders` template save and template comparison preserve RMB-vs-non-RMB differences where business meaning differs.
3. `orders_atomic.sql` and `orders_model.sql` prefer RMB-specific source fields for the corresponding system business fields.
4. Frontend business labels remain unchanged.
5. Non-`orders` domains keep current behavior.

## 11. Implementation Notes

- This work should be treated as an `orders`-domain semantic preservation fix, not as a generic currency-normalization redesign.
- Test coverage must prove:
  - no collision overwrite
  - SQL fallback priority is correct
  - template diff behavior for RMB fields is now visible in `orders`
