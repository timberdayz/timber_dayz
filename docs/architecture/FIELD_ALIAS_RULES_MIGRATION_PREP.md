# Field Alias Rules Migration Preparation

This document prepares the future migration from document + SQL governed semantic rules into database-managed rule tables.

It does **not** switch runtime reads yet.

## Current State

Current assets:

- `docs/architecture/SEMANTIC_FIELD_RULES.md`
- `sql/semantic/*.sql`
- `sql/ops/create_field_alias_rules.sql`
- `backend/services/field_alias_rule_service.py`

Current runtime truth:

- semantic behavior is still executed by SQL
- explicit governance decisions live in docs plus SQL
- `core.field_alias_rules` exists only as a narrow alias table model

## Why The Current `field_alias_rules` Table Is Not Enough

Current schema:

- `platform_code`
- `data_domain`
- `sub_domain`
- `source_field_name`
- `standard_field_name`
- `parser_type`
- `priority`
- `active`

This is enough for simple alias fallback lists, but it is **not** enough for the all-domain iron law and the current governance model.

### Missing Capabilities

1. **Rule type**
   - We need to distinguish:
     - `merge`
     - `split`
     - `priority`

2. **Coexisting same-file guard**
   - We must represent:
     - same platform
     - same data domain
     - same file
     - coexisting fields must split by default

3. **One-to-many split representation**
   - Example:
     - `订单数` and `SKU 订单数`
     - must map to different canonical outputs
   - A simple alias table that only says `source_field_name -> standard_field_name` cannot express the governance reason or guard.

4. **Rule-group identity**
   - We need to know which source fields belong to the same business decision group.

5. **Decision rationale / governance trace**
   - The future rule table should preserve enough metadata to explain why a rule exists.

6. **Phase-safe migration boundary**
   - We need a structure that allows docs + SQL to remain the runtime source of truth until rule-table execution is explicitly switched on.

## Required Future Model

The future rule-table design should support two levels:

### 1. Rule Header

One row per semantic decision group.

Recommended fields:

- `rule_id`
- `platform_code`
- `data_domain`
- `sub_domain`
- `canonical_field_name`
- `rule_type` (`merge` / `split` / `priority`)
- `coexistence_policy` (`split_if_same_file` / `merge_cross_platform_only` / `priority_fallback`)
- `active`
- `notes`
- `decision_source`
- `created_at`
- `updated_at`

### 2. Rule Members

One row per source-field member inside a rule group.

Recommended fields:

- `member_id`
- `rule_id`
- `source_field_name`
- `priority`
- `source_platform_scope`
- `source_domain_scope`
- `active`

## Draft Migration Target

This preparation phase introduces a **draft-only** SQL asset:

- `sql/ops/create_semantic_field_rules_v2_draft.sql`

It is intentionally not wired into runtime bootstrapping yet.

## Mapping Rules From Current Governance

### Merge Example

Cross-platform semantic merge:

- canonical field: `gmv`
- members:
  - TikTok `GMV`
  - Shopee analytics sales-like confirmed equivalent

### Split Example

Same-file coexistence split:

- rule A:
  - canonical field: `order_count`
  - rule type: `split`
  - member: `订单数`
- rule B:
  - canonical field: `sku_order_count`
  - rule type: `split`
  - member: `SKU 订单数`

### Priority Example

Orders RMB-first fallback:

- canonical field: `profit`
- rule type: `priority`
- members in priority order:
  - `利润(RMB)`
  - `profit_rmb`
  - `利润`
  - `profit`

## Migration Strategy

### Phase 1: Preparation

- keep docs + SQL as runtime source of truth
- add draft schema and tests
- do not read the new tables at runtime

### Phase 2: Seed Generation

- generate seed data from `SEMANTIC_FIELD_RULES.md`
- validate seed structure against the draft schema

### Phase 3: Dual Verification

- compare:
  - SQL runtime behavior
  - rule-table interpreted behavior

### Phase 4: Runtime Switch

- only after parity is proven

## Success Criteria

1. We can represent merge, split, and priority rules explicitly.
2. We can represent the all-domain iron law in the future table model.
3. We do not force a runtime switch before parity checks exist.
4. Future migration does not erase the distinction between:
   - cross-platform semantic merge
   - same-file coexistence split

## Non-Goals

- No runtime read switch in this phase
- No migration script execution in this phase
- No replacement of current semantic SQL in this phase
