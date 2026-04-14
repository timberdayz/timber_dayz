# Data Sync Template Drift And Inventory Granularity Design

**Date:** 2026-04-14

**Goal:** Solve two recurring data-sync reliability problems at the rule level rather than as one-off fixes: inconsistent template-update judgments across views, and incorrect `inventory` granularity being written during collection landing and catalog registration.

## 1. Background

Recent file samples show two separate but related problems in the current data-sync flow:

1. The same file can appear as `需要更新` in the pending-file list while the template-governance `需要更新` queue is empty or inconsistent.
2. `inventory` files produced by canonical collection components can be registered into `catalog_files` with `granularity='monthly'`, even though inventory is modeled as snapshot data and existing templates only support `snapshot`.

The first problem causes operator confusion and undermines trust in the governance screen. The second problem breaks template matching entirely and creates false `无模板` states for files that are semantically valid.

These are not isolated bugs. They reveal two architectural gaps:

- template drift detection is duplicated with different thresholds
- landing-time file semantics are not protected from task-level time-granularity defaults

## 2. Evidence

### 2.1 Template Drift Evidence

The current file-list readiness path uses `evaluate_catalog_file_template_status()` in [backend/services/data_sync_service.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/data_sync_service.py#L180). That path marks a file as `update_required` whenever header drift is detected and the file is not an exact template match.

The governance coverage path uses `get_detailed_coverage_stats()` in [backend/routers/data_sync.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/data_sync.py#L1979). That path only appends a row into `needs_update_list` when drift is detected and `match_rate < 90`, see [backend/routers/data_sync.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/data_sync.py#L2137).

This means two screens answer different business questions while both are labeled as template status:

- file list: "is this file an exact match to the current template?"
- governance tab: "is this combination below a hardcoded 90% threshold?"

For the sampled TikTok monthly orders file:

- current column count = 184
- template column count = 184
- exact match = `False`
- match rate = `91.7%`

The difference comes from paired field renames, not from true column-count drift. In other words, structure width is unchanged, but field identity has changed enough to break exact matching.

### 2.2 Inventory Granularity Evidence

The canonical Miaoshou inventory component already declares snapshot semantics:

- domain is `inventory`, see [modules/platforms/miaoshou/components/inventory_snapshot_export.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/miaoshou/components/inventory_snapshot_export.py#L19)
- output root uses `granularity="snapshot"`, see [modules/platforms/miaoshou/components/inventory_snapshot_export.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/miaoshou/components/inventory_snapshot_export.py#L221)
- final renamed file also uses `granularity="snapshot"`, see [modules/platforms/miaoshou/components/inventory_snapshot_export.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/miaoshou/components/inventory_snapshot_export.py#L240)

However, the shared collection landing flow in [modules/apps/collection_center/executor_v2.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/executor_v2.py#L3817) rewrites the final filename and metadata using the task-level `granularity` argument:

- filename generation uses task granularity, see [modules/apps/collection_center/executor_v2.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/executor_v2.py#L3879)
- `.meta.json` business metadata also writes task granularity, see [modules/apps/collection_center/executor_v2.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/executor_v2.py#L3908)

This is how a semantically snapshot inventory file can be registered as `inventory/monthly`.

The current repository already encodes the intended rule in validation scripts:

- `inventory` must use `snapshot`
- non-`inventory` domains must not use `snapshot`

See [scripts/test_data_sync.py](/F:/Vscode/python_programme/AI_code/xihong_erp/scripts/test_data_sync.py#L331).

## 3. Design Goals

This design should achieve the following:

1. Define a single business meaning for template drift and reuse it everywhere.
2. Distinguish "official field rename / semantic equivalent" from "real template break".
3. Keep strict operator visibility when fields actually change.
4. Ensure `inventory` landing semantics are always `snapshot`, regardless of task date preset.
5. Prevent future recurrence through shared resolution logic and tests.
6. Avoid weakening sync safety rules just to tolerate bad landing metadata.

## 4. Options Considered

### 4.1 Option A: Threshold-Only Cleanup

Keep current exact-vs-match-rate logic, but make all screens use the same threshold.

Pros:

- small change
- solves visible inconsistency quickly

Cons:

- still cannot distinguish harmless rename from real schema drift
- operators keep seeing avoidable "needs update" for platform wording changes
- does not address inventory semantic corruption

### 4.2 Option B: Recommended

Introduce one shared template-status evaluation pipeline plus a field-alias normalization layer, and separately introduce one shared landing-granularity resolver that enforces domain semantics before filename, metadata, and catalog registration are written.

Pros:

- fixes both recurring classes of issues at the rule level
- makes status consistent across file list, governance, and sync readiness
- supports future platform header wording changes without relying on ad hoc template churn
- keeps inventory rules explicit and testable

Cons:

- moderate implementation scope
- requires touching both collection and data-sync code paths

### 4.3 Option C: Sync-Layer Compatibility Only

Leave landing files as-is and teach template matching and sync readiness to special-case `inventory/monthly` as `inventory/snapshot`.

Pros:

- fastest tactical workaround

Cons:

- hides corrupted upstream semantics
- creates two truths for inventory granularity
- guarantees future drift between filenames, metadata, catalog records, and pipeline tables

### 4.4 Recommendation

Choose **Option B**.

The right place to fix inventory is the landing layer, not the sync layer. The right place to fix template inconsistency is a shared evaluation rule, not per-screen heuristics.

## 5. Unified Template Drift Model

The system should stop treating "template status" as a loosely duplicated UI concern. It should become a shared backend judgment with explicit states.

### 5.1 Target Status Model

Each file-level template evaluation should produce:

- `template_status`
  - `missing`
  - `ready`
  - `alias_only`
  - `update_required`
- `exact_match`
- `semantic_match`
- `template_update_required`
- `update_reason`
- `header_changes`
- `normalized_header_changes`

Interpretation:

- `ready`: exact structural match
- `alias_only`: raw labels changed, but normalized semantic fields are equivalent
- `update_required`: real structure drift after semantic normalization
- `missing`: no matching published template

### 5.2 Shared Consumers

The following flows must consume the same evaluator result instead of each implementing local logic:

- pending file list
- governance detailed coverage
- governance summary counts
- single-file sync readiness
- batch sync readiness
- scheduled auto-sync skip reasons

This removes the current inconsistency between [backend/services/data_sync_service.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/data_sync_service.py#L180) and [backend/routers/data_sync.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/data_sync.py#L1979).

## 6. Field Alias Normalization

The current `detect_header_changes()` routine already normalizes some currency variants. That same idea should be extended into a first-class field-alias layer for official platform wording changes.

### 6.1 Rule

Before judging whether a template requires update, compare two views of the headers:

1. raw headers
2. normalized semantic headers

If raw headers differ but normalized semantic headers are equivalent and ordered equivalently, status should be `alias_only`, not `update_required`.

### 6.2 Scope

This normalization should be opt-in by platform + domain + granularity because header wording changes are not globally interchangeable.

Suggested initial scope:

- `tiktok/orders/monthly`
- other domains only after evidence exists

### 6.3 Storage Model

Use a backend-managed alias rule source such as:

- in-code registry for initial rollout
- later evolvable into config or DB-backed rules if needed

Each rule should map raw platform headers to canonical semantic headers. Example shape:

- `platform`
- `data_domain`
- `granularity`
- `raw_field`
- `canonical_field`

### 6.4 Operator Visibility

Even when status becomes `alias_only`, the UI should still show that the platform changed label wording. It simply should not be escalated as a mandatory template update unless the canonical structure changed.

## 7. Governance UI Rule Changes

The governance page should stop recomputing its own threshold logic.

### 7.1 Summary Counts

`needs_update_count` must count files or combinations whose shared evaluator returns `update_required`.

`alias_only_count` may be added as an informational metric if the team wants visibility into vendor wording churn without operational noise.

### 7.2 Queue Semantics

The `需要更新` queue should only contain combinations with true structural drift after normalization.

If a combination only has alias drift:

- do not block sync
- optionally show under a softer informational bucket

This preserves operator trust: every row in `需要更新` means a real action is required.

## 8. Inventory Landing Granularity Design

The collection landing layer should resolve final file semantics before writing any of:

- final filename
- target path
- `.meta.json`
- `catalog_files` dimensions

### 8.1 Rule

Task-level date preset is not the same thing as business granularity.

For `inventory`:

- business granularity is always `snapshot`

For non-`inventory` domains:

- business granularity may remain task-driven (`daily`, `weekly`, `monthly`) according to existing export logic

### 8.2 New Resolver

Add one shared resolver in collection landing, conceptually:

- input:
  - platform
  - data_domain
  - task granularity
  - component metadata if available
- output:
  - final landing granularity
  - semantic reason/source

Suggested behavior:

- if `data_domain == "inventory"` -> return `snapshot`
- else -> return task granularity unless a component-specific override says otherwise

### 8.3 Write Paths To Use Resolved Granularity

The resolved granularity must be used in all three places:

1. `StandardFileName.generate(...)`
2. `.meta.json` `business_metadata.granularity`
3. subsequent `register_single_file(...)` parsing inputs

This prevents the current drift where the component knows inventory is snapshot but the shared landing layer rewrites it as monthly.

## 9. Historical Bad Data Handling

Fixing future landing is not enough. The system already contains wrong inventory records.

### 9.1 Repair Scope

For affected inventory files with bad granularity:

- rename file if filename encodes wrong granularity
- update `.meta.json`
- update `catalog_files.granularity`

### 9.2 Repair Rule

Repair should only target cases where:

- `data_domain = 'inventory'`
- `granularity != 'snapshot'`

This avoids risky bulk rewrites.

## 10. Error Handling And Safety

### 10.1 Template Drift Safety

Do not relax ingestion safety just because alias normalization exists.

The order of decisions should be:

1. no template -> `missing`
2. exact match -> `ready`
3. normalized semantic match -> `alias_only`
4. otherwise -> `update_required`

### 10.2 Inventory Safety

Add hard guards so invalid domain/granularity pairings are rejected before persistence:

- `inventory` with non-`snapshot` granularity should be corrected or blocked at landing
- non-`inventory` with `snapshot` should also be corrected or blocked unless explicitly modeled as snapshot data

These guards align with [scripts/test_data_sync.py](/F:/Vscode/python_programme/AI_code/xihong_erp/scripts/test_data_sync.py#L331).

## 11. Testing Strategy

### 11.1 Template Drift Tests

Add focused tests for:

- exact raw match -> `ready`
- alias-only rename set -> `alias_only`
- true added/removed semantic fields -> `update_required`
- file list and governance summary both deriving the same result from the shared evaluator

### 11.2 Inventory Landing Tests

Add focused tests for:

- inventory file landing with task granularity `monthly` still writes `snapshot`
- `.meta.json` and final filename agree on `snapshot`
- `catalog_files` registration stores `snapshot`
- non-inventory domains still retain existing daily/weekly/monthly behavior

### 11.3 Regression Coverage

Add tests that prove:

- `inventory/monthly` can no longer be created by the landing pipeline
- a TikTok-style official rename no longer creates conflicting template status across screens

## 12. MVP Scope

### 12.1 Included In MVP

- one shared backend template-status evaluator
- governance and file list both using that evaluator
- field-alias normalization for known proven drift cases
- one landing-granularity resolver
- inventory forced to snapshot at landing
- targeted repair path for already corrupted inventory records
- regression tests for both classes of issues

### 12.2 Excluded From MVP

- full database-backed alias rule management UI
- operator-facing alias rule editor
- generalized schema versioning for templates
- retroactive semantic rewrite of all historical templates

## 13. Rollout Order

Recommended implementation order:

1. extract shared template-status evaluator
2. refactor file list and governance endpoints to consume it
3. add alias normalization for proven TikTok monthly orders drift
4. add collection landing granularity resolver
5. enforce `inventory -> snapshot`
6. add historical inventory repair utility
7. run regression tests

## 14. Success Criteria

This design is successful when:

1. The same file produces the same template status in file list, governance, auto-sync, and sync readiness.
2. Official vendor wording changes no longer automatically create false mandatory template updates when semantics are unchanged.
3. True structural changes still block sync and surface clearly.
4. `inventory` files can no longer be landed or registered with `monthly`, `weekly`, or `daily` granularity.
5. Existing corrupted inventory records can be repaired deterministically.

## 15. Conclusion

The correct solution is not to relax sync safety and not to keep updating templates by hand whenever a vendor changes wording.

The correct solution is to separate:

- semantic equivalence
- structural template drift
- landing-time business granularity

Once those rules are centralized, the system becomes predictable:

- operators see one consistent status
- harmless field renames stop generating false alarms
- real template breaks still require action
- inventory always lands with snapshot semantics
