# Data Sync Template Drift And Inventory Granularity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify template drift judgment across data-sync surfaces, add alias-only compatibility for proven platform field renames, and enforce `inventory -> snapshot` semantics during collection landing and catalog registration.

**Architecture:** Introduce one shared backend template-status evaluator that all file-list, governance, readiness, and auto-sync flows reuse. Add a narrow alias-normalization layer for proven platform/domain/granularity combinations so harmless vendor label changes do not trigger structural drift. In parallel, add a landing-granularity resolver in collection landing so inventory files always persist as snapshot data before filename, metadata, and catalog registration are written.

**Tech Stack:** Python, FastAPI, SQLAlchemy async, pytest, Vue 3 data-sync consumers, Playwright-derived collection landing pipeline

---

## File Map

- Modify: `backend/services/template_matcher.py`
  - Extend header comparison to support alias normalization by platform/domain/granularity.
- Create: `backend/services/template_alias_registry.py`
  - Store initial proven alias mappings such as `tiktok/orders/monthly`.
- Create: `backend/services/data_sync_template_status_service.py`
  - Centralize template-status evaluation and expose one consistent status model.
- Modify: `backend/services/data_sync_service.py`
  - Delegate file-level template readiness to the shared status service.
- Modify: `backend/routers/data_sync.py`
  - Use the shared status service for file list and governance counts/lists.
- Modify: `backend/tasks/scheduled_tasks.py`
  - Reuse the unified status model if scheduled sync readiness text depends on template state.
- Modify: `modules/apps/collection_center/executor_v2.py`
  - Resolve final landing granularity before filename/meta/catalog registration.
- Create: `modules/apps/collection_center/landing_semantics.py`
  - Hold shared domain-to-business-granularity resolution rules.
- Create: `scripts/repair_inventory_snapshot_granularity.py`
  - Repair corrupted inventory records and companion files already written with wrong granularity.
- Test: `backend/tests/test_data_sync_template_status_service.py`
  - Shared evaluator coverage: ready, alias_only, update_required, missing.
- Test: `backend/tests/test_data_sync_governance_status_consistency.py`
  - File list and governance must agree on status.
- Test: `backend/tests/test_collection_inventory_landing_granularity.py`
  - Inventory landing must resolve to snapshot even when task granularity is monthly.
- Test: `backend/tests/test_inventory_granularity_repair_script.py`
  - Historical repair behavior for file name, meta, and catalog updates.

## Task 1: Add Alias Registry For Proven Field Renames

**Files:**
- Create: `backend/services/template_alias_registry.py`
- Test: `backend/tests/test_data_sync_template_status_service.py`

- [ ] **Step 1: Write the failing alias-registry test**

```python
def test_tiktok_orders_monthly_alias_registry_maps_old_and_new_labels():
    mapping = get_header_alias_mapping("tiktok", "orders", "monthly")
    assert mapping["TikTok Shop平台佣金"] == "TikTok 平台佣金"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -k alias_registry -q`
Expected: FAIL because registry helper does not exist.

- [ ] **Step 3: Write minimal alias registry**

```python
ALIASES = {
    ("tiktok", "orders", "monthly"): {
        "TikTok Shop平台佣金": "TikTok 平台佣金",
        "TikTok Shop平台佣金(RMB)": "TikTok 平台佣金(RMB)",
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -k alias_registry -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/template_alias_registry.py backend/tests/test_data_sync_template_status_service.py
git commit -m "feat: add template header alias registry"
```

## Task 2: Extend Header Comparison With Semantic Normalization

**Files:**
- Modify: `backend/services/template_matcher.py`
- Modify: `backend/services/template_alias_registry.py`
- Test: `backend/tests/test_data_sync_template_status_service.py`

- [ ] **Step 1: Write the failing semantic-normalization test**

```python
async def test_detect_header_changes_reports_semantic_match_for_alias_only_drift():
    result = await matcher.detect_header_changes(template_id=1, current_columns=RENAMED_TIKTOK_COLUMNS)
    assert result["is_semantic_match"] is True
    assert result["is_exact_match"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -k semantic_match -q`
Expected: FAIL because semantic-match fields are not returned.

- [ ] **Step 3: Update header-comparison logic**

Implementation notes:
- normalize current and template headers using existing currency normalization first
- then apply alias normalization for matching platform/domain/granularity
- return both raw and normalized comparison outputs:
  - `normalized_current_columns`
  - `normalized_template_columns`
  - `is_semantic_match`
  - `normalized_added_fields`
  - `normalized_removed_fields`

- [ ] **Step 4: Run focused test suite**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -k "semantic_match or header_changes" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/template_matcher.py backend/services/template_alias_registry.py backend/tests/test_data_sync_template_status_service.py
git commit -m "feat: normalize template drift with header aliases"
```

## Task 3: Create Shared Template Status Service

**Files:**
- Create: `backend/services/data_sync_template_status_service.py`
- Modify: `backend/services/data_sync_service.py`
- Test: `backend/tests/test_data_sync_template_status_service.py`

- [ ] **Step 1: Write the failing service-state tests**

```python
async def test_template_status_service_returns_alias_only_for_semantic_match():
    status = await service.evaluate_catalog_file(catalog_file, template=template)
    assert status["template_status"] == "alias_only"
    assert status["template_update_required"] is False
```

```python
async def test_template_status_service_returns_update_required_for_true_structure_drift():
    status = await service.evaluate_catalog_file(catalog_file, template=template)
    assert status["template_status"] == "update_required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -q`
Expected: FAIL because shared service does not exist.

- [ ] **Step 3: Implement shared service**

Implementation notes:
- service owns status model:
  - `missing`
  - `ready`
  - `alias_only`
  - `update_required`
- decision order:
  1. no template -> `missing`
  2. exact raw match -> `ready`
  3. semantic normalized match -> `alias_only`
  4. otherwise -> `update_required`
- include structured reason and normalized diff payload for UI reuse

- [ ] **Step 4: Replace local logic in `DataSyncService`**

Implementation notes:
- keep `DataSyncService.evaluate_catalog_file_template_status()` as a thin delegating adapter
- preserve existing response keys used by routes/UI

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/data_sync_template_status_service.py backend/services/data_sync_service.py backend/tests/test_data_sync_template_status_service.py
git commit -m "feat: centralize data sync template status evaluation"
```

## Task 4: Make File List And Governance Reuse Shared Status

**Files:**
- Modify: `backend/routers/data_sync.py`
- Test: `backend/tests/test_data_sync_governance_status_consistency.py`

- [ ] **Step 1: Write the failing consistency tests**

```python
async def test_file_list_and_governance_both_report_alias_only_as_non_update():
    assert file_list_row["template_status"] == "alias_only"
    assert governance_summary["needs_update_count"] == 0
```

```python
async def test_file_list_and_governance_both_report_true_structure_drift_as_update_required():
    assert file_list_row["template_status"] == "update_required"
    assert governance_summary["needs_update_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_data_sync_governance_status_consistency.py -q`
Expected: FAIL because governance still uses local `< 90` logic.

- [ ] **Step 3: Refactor file-list route**

Implementation notes:
- keep route payload shape stable
- populate `template_status`, `template_update_required`, and `update_reason` exclusively from shared service

- [ ] **Step 4: Refactor governance detailed-coverage route**

Implementation notes:
- remove local `match_rate < 90` decision for `needs_update_list`
- use shared status result for covered/missing/needs_update classification
- optionally expose alias-only informational fields without counting them as updates

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest backend/tests/test_data_sync_governance_status_consistency.py backend/tests/test_data_sync_template_status_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/data_sync.py backend/tests/test_data_sync_governance_status_consistency.py backend/tests/test_data_sync_template_status_service.py
git commit -m "fix: unify data sync governance and file template status"
```

## Task 5: Add Collection Landing Granularity Resolver

**Files:**
- Create: `modules/apps/collection_center/landing_semantics.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_inventory_landing_granularity.py`

- [ ] **Step 1: Write the failing landing-semantics tests**

```python
def test_inventory_domain_resolves_snapshot_even_when_task_granularity_is_monthly():
    resolved = resolve_business_granularity(data_domain="inventory", task_granularity="monthly")
    assert resolved == "snapshot"
```

```python
def test_orders_domain_keeps_task_granularity():
    resolved = resolve_business_granularity(data_domain="orders", task_granularity="monthly")
    assert resolved == "monthly"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_collection_inventory_landing_granularity.py -q`
Expected: FAIL because resolver does not exist.

- [ ] **Step 3: Implement landing semantics resolver**

Implementation notes:
- create one small helper file for:
  - `resolve_business_granularity(data_domain, task_granularity, component_hint=None)`
- initial hard rule:
  - `inventory -> snapshot`
  - other domains -> task granularity

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_inventory_landing_granularity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/landing_semantics.py backend/tests/test_collection_inventory_landing_granularity.py
git commit -m "feat: add collection landing granularity resolver"
```

## Task 6: Enforce Resolved Granularity During File Landing

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_inventory_landing_granularity.py`

- [ ] **Step 1: Write the failing end-to-end landing test**

```python
async def test_process_files_writes_inventory_filename_meta_and_catalog_as_snapshot(...):
    result = await executor._process_files(
        file_paths=[str(source_file)],
        platform="miaoshou",
        data_domains=["inventory"],
        granularity="monthly",
    )
    assert result[0].endswith("inventory_snapshot_...")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_collection_inventory_landing_granularity.py -k process_files -q`
Expected: FAIL because `_process_files()` still uses task granularity directly.

- [ ] **Step 3: Update `_process_files()` to use resolved granularity**

Implementation notes:
- compute `resolved_granularity` once per file after `data_domain` inference
- use `resolved_granularity` in:
  - `StandardFileName.generate(...)`
  - `business_metadata["granularity"]`
  - any downstream registration inputs/log messages tied to business semantics

- [ ] **Step 4: Add guard rails**

Implementation notes:
- if `data_domain == "inventory"` and resolved granularity is not `snapshot`, raise or correct before write
- optionally assert non-inventory domains do not emit snapshot unless explicitly allowed

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest backend/tests/test_collection_inventory_landing_granularity.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_inventory_landing_granularity.py
git commit -m "fix: enforce snapshot granularity for inventory landing"
```

## Task 7: Add Historical Inventory Repair Script

**Files:**
- Create: `scripts/repair_inventory_snapshot_granularity.py`
- Test: `backend/tests/test_inventory_granularity_repair_script.py`

- [ ] **Step 1: Write the failing repair-script tests**

```python
def test_repair_script_targets_only_inventory_records_with_non_snapshot_granularity():
    assert repair_candidates == [bad_inventory_record]
```

```python
def test_repair_script_updates_file_name_meta_and_catalog_record(tmp_path):
    assert fixed_catalog_row["granularity"] == "snapshot"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_inventory_granularity_repair_script.py -q`
Expected: FAIL because repair script does not exist.

- [ ] **Step 3: Implement repair script**

Implementation notes:
- dry-run by default
- target only:
  - `data_domain='inventory'`
  - `granularity!='snapshot'`
- update:
  - filename when encodes wrong granularity
  - sibling `.meta.json`
  - `catalog_files.granularity`
  - `catalog_files.file_name`
  - `catalog_files.file_path` if renamed

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_inventory_granularity_repair_script.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/repair_inventory_snapshot_granularity.py backend/tests/test_inventory_granularity_repair_script.py
git commit -m "feat: add repair utility for inventory snapshot granularity"
```

## Task 8: Verify End-To-End Regression Coverage

**Files:**
- Modify: `backend/tests/test_data_sync_template_status_service.py`
- Modify: `backend/tests/test_data_sync_governance_status_consistency.py`
- Modify: `backend/tests/test_collection_inventory_landing_granularity.py`
- Modify: `backend/tests/test_inventory_granularity_repair_script.py`

- [ ] **Step 1: Run template-status regression suite**

Run: `python -m pytest backend/tests/test_data_sync_template_status_service.py backend/tests/test_data_sync_governance_status_consistency.py -q`
Expected: PASS.

- [ ] **Step 2: Run collection landing and repair suite**

Run: `python -m pytest backend/tests/test_collection_inventory_landing_granularity.py backend/tests/test_inventory_granularity_repair_script.py -q`
Expected: PASS.

- [ ] **Step 3: Run broader data-sync regression slice**

Run: `python -m pytest backend/tests/test_governance_stats_async_api.py backend/tests/test_field_mapping_template_update_context_api.py -q`
Expected: PASS or only unrelated pre-existing failures.

- [ ] **Step 4: Run repository validation for domain/granularity rules if applicable**

Run: `python scripts/test_data_sync.py`
Expected: inventory-related rule checks still pass.

- [ ] **Step 5: Commit verification-only updates if tests required fixture adjustments**

```bash
git add backend/tests
git commit -m "test: cover template drift and inventory granularity regressions"
```

## Task 9: Update Operational Notes

**Files:**
- Modify: `docs/superpowers/specs/2026-04-14-data-sync-template-drift-and-inventory-granularity-design.md`
- Optional Modify: relevant operator doc if current template-governance behavior is documented elsewhere

- [ ] **Step 1: Record final implementation decisions**

Add final notes covering:
- alias-only status semantics
- why template update is still required for true structure drift
- why inventory business granularity is snapshot regardless of task preset

- [ ] **Step 2: Run quick doc sanity check**

Run: `rg -n "alias_only|inventory.*snapshot|template drift" docs backend frontend`
Expected: the new terms appear only where intended.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-14-data-sync-template-drift-and-inventory-granularity-design.md
git commit -m "docs: record template drift and inventory granularity rules"
```

## Notes For Execution

- Prefer minimal in-code alias scope first. Do not invent a generic alias DSL unless the tests force it.
- Preserve existing API response keys consumed by the frontend. Add new fields only when they are clearly additive.
- Do not weaken sync blocking behavior for true structural drift.
- Do not implement sync-layer fallback from `inventory/monthly` to `inventory/snapshot`; fix the landing layer and repair historical bad rows instead.
- Keep tests explicit and narrow. The point is to prove rule behavior, not to build giant fixture stacks.

## Review Note

This environment does support delegated agents, but the current user did not explicitly authorize subagent review for this turn. Because of that, the plan-document reviewer loop is intentionally skipped here and should be performed manually or after explicit user approval for delegation.
