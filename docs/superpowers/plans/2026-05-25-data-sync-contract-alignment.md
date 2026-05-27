# Data Sync Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the file-based data-sync runtime with the raw-first, semantic-later contract so raw ingestion preserves source fidelity and task/file/error state becomes trustworthy.

**Architecture:** Keep the existing sync entrypoints and PostgreSQL-first pipeline, but move semantic-style field collapse out of raw ingestion. Make template-driven raw reading authoritative, preserve coexisting source columns in `b_class raw`, and standardize state/error ownership around task execution and file processing records. Apply the smallest possible runtime changes before any semantic SQL expansion.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Celery, pytest

---

## File Structure

- Modify: `backend/services/data_ingestion_service.py`
  - Remove raw-preinsert semantic collapse behavior.
  - Introduce raw-safe normalization rules limited to storage mechanics.
  - Correct error attribution and file-state writing.
- Modify: `backend/services/data_sync_service.py`
  - Make template-governed raw reading explicit.
  - Ensure task/file status transitions remain consistent on all exits.
- Modify: `backend/services/raw_data_importer.py`
  - Accept preserved raw headers/rows without requiring semantic-style key collapse.
  - Preserve template linkage metadata where available.
- Modify: `backend/services/currency_extractor.py`
  - Narrow normalization behavior so raw ingestion does not destroy source distinctions.
- Modify: `backend/services/sync_progress_tracker.py`
  - Align compatibility behavior with task/file status ownership.
- Modify: `backend/tasks/data_sync_tasks.py`
  - Verify worker-side state transitions and failure messages stay aligned.
- Test: `backend/tests/test_data_ingestion_raw_contract.py`
  - New focused tests for raw-preservation behavior.
- Test: `backend/tests/test_data_sync_status_contract.py`
  - New focused tests for task/file/progress agreement.
- Test: `backend/tests/test_data_sync_error_classification.py`
  - New focused tests for stage-accurate error messages.
- Test: `backend/tests/test_metric_date_template_rules.py`
  - Extend to cover success-path date contract.
- Docs: `docs/architecture/DATA_SYNC_CONTRACT.md`
  - Update if implementation reveals needed clarifications.

## Task 1: Lock Raw-Preservation Contract With Failing Tests

**Files:**
- Create: `backend/tests/test_data_ingestion_raw_contract.py`
- Test: `backend/tests/test_data_ingestion_raw_contract.py`

- [ ] **Step 1: Write the failing test for coexisting source columns**

```python
import pytest

from backend.services.data_ingestion_service import normalize_row_fields_for_domain


def test_analytics_raw_contract_preserves_coexisting_source_columns():
    row = {
        "订单数": 10,
        "SKU 订单数": 14,
        "GMV": 100.0,
    }

    result = normalize_row_fields_for_domain("analytics", row)

    assert "订单数" in result
    assert "SKU 订单数" in result
    assert result["订单数"] == 10
    assert result["SKU 订单数"] == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -v`
Expected: FAIL because analytics raw normalization currently collapses or errors on coexisting fields.

- [ ] **Step 3: Add a second failing test for orders currency fields**

```python
def test_orders_raw_contract_preserves_distinct_currency_source_fields():
    row = {
        "VAT(RMB)": 1.2,
        "SST(RMB)": 2.3,
    }

    result = normalize_row_fields_for_domain("orders", row)

    assert "VAT(RMB)" in result
    assert "SST(RMB)" in result
```

- [ ] **Step 4: Run the two tests together**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -v`
Expected: FAIL on both cases.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_data_ingestion_raw_contract.py
git commit -m "test: lock raw preservation contract for sync ingestion"
```

## Task 2: Refactor Raw Normalization To Be Storage-Safe Only

**Files:**
- Modify: `backend/services/data_ingestion_service.py`
- Modify: `backend/services/currency_extractor.py`
- Test: `backend/tests/test_data_ingestion_raw_contract.py`

- [ ] **Step 1: Replace semantic-style raw normalization with raw-safe normalization**

Implement a new helper in `backend/services/data_ingestion_service.py` that:

- preserves original source keys for raw storage
- allows only minimal storage-safe cleanup when explicitly required
- never collapses two distinct source keys into one raw key

Code target:

```python
def normalize_row_fields_for_domain(
    domain: str,
    row: Dict[str, Any],
    currency_extractor=None,
) -> Dict[str, Any]:
    del domain, currency_extractor
    return dict(row)
```

This is the minimal contract-restoring version. If storage-safe transformations are later needed, add them explicitly and losslessly.

- [ ] **Step 2: Ensure header normalization used for dynamic-column management is also raw-safe**

Update the code path that currently builds `normalized_header_columns` so it preserves distinct source header identity for raw storage metadata.

Target behavior:

```python
header_columns_for_storage = original_header_columns
normalized_header_columns = list(header_columns_for_storage)
```

- [ ] **Step 3: Run the raw-contract tests**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -v`
Expected: PASS

- [ ] **Step 4: Run a focused existing test group**

Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`
Expected: PASS or only unrelated legacy failures.

- [ ] **Step 5: Commit**

```bash
git add backend/services/data_ingestion_service.py backend/services/currency_extractor.py backend/tests/test_data_ingestion_raw_contract.py
git commit -m "refactor: keep raw sync fields lossless before semantic layer"
```

## Task 3: Make Error Attribution Stage-Accurate

**Files:**
- Create: `backend/tests/test_data_sync_error_classification.py`
- Modify: `backend/services/data_ingestion_service.py`

- [ ] **Step 1: Write the failing classification test**

```python
def test_field_collision_is_reported_as_raw_normalization_failure():
    message = build_sync_error_message(
        stage="raw_normalization",
        detail="Field normalization collision",
    )

    assert "RawDataImporter异常" not in message
    assert "raw_normalization" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_data_sync_error_classification.py -v`
Expected: FAIL because the current message still blames RawDataImporter.

- [ ] **Step 3: Implement stage-specific error formatting**

Introduce a helper in `backend/services/data_ingestion_service.py` used by return paths:

```python
def _format_sync_stage_error(stage: str, detail: str) -> str:
    return f"数据同步失败:{stage},{detail}"
```

Use it in:

- raw normalization failures
- template failures
- preview/read failures
- raw importer/storage failures

- [ ] **Step 4: Re-run the focused test**

Run: `python -m pytest backend/tests/test_data_sync_error_classification.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/data_ingestion_service.py backend/tests/test_data_sync_error_classification.py
git commit -m "fix: classify sync failures by actual pipeline stage"
```

## Task 4: Align Task And File Status Contract

**Files:**
- Create: `backend/tests/test_data_sync_status_contract.py`
- Modify: `backend/services/data_sync_service.py`
- Modify: `backend/tasks/data_sync_tasks.py`
- Modify: `backend/services/sync_progress_tracker.py`

- [ ] **Step 1: Write a failing test for failed-task consistency**

```python
async def test_failed_sync_updates_task_and_catalog_file_consistently():
    task = await load_task("single_file_2391_example")
    catalog = await load_catalog_file(2391)

    assert task["status"] == "failed"
    assert catalog["status"] == "failed"
    assert catalog["error_message"]
```

- [ ] **Step 2: Write a failing test for successful-task consistency**

```python
async def test_successful_sync_does_not_leave_progress_state_missing_when_required():
    task = await load_task("single_file_success_example")
    assert task["status"] == "completed"
```

Use the real repository test pattern for async service tests; do not invent a new harness.

- [ ] **Step 3: Run the status tests to verify failure**

Run: `python -m pytest backend/tests/test_data_sync_status_contract.py -v`
Expected: FAIL because current file/task/progress surfaces are not consistently updated.

- [ ] **Step 4: Implement consistent state writes**

Required runtime behavior:

- on failure, populate `catalog_files.status='failed'`
- on failure, populate `catalog_files.error_message`
- on success, populate `catalog_files.status='ingested'`
- do not silently skip task/file alignment
- only keep `sync_progress_tasks` as a compatibility surface if active callers still need it

- [ ] **Step 5: Re-run the status tests**

Run: `python -m pytest backend/tests/test_data_sync_status_contract.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/data_sync_service.py backend/tasks/data_sync_tasks.py backend/services/sync_progress_tracker.py backend/tests/test_data_sync_status_contract.py
git commit -m "fix: align sync task and file state contracts"
```

## Task 5: Restore Template Authority For Raw Reading

**Files:**
- Modify: `backend/services/data_sync_service.py`
- Modify: `backend/services/data_ingestion_service.py`
- Test: `backend/tests/test_data_ingestion_raw_contract.py`

- [ ] **Step 1: Write a failing test proving template-recognized columns survive raw ingestion**

```python
async def test_template_recognized_columns_are_preserved_in_raw_ingestion():
    template_headers = ["日期", "订单数", "SKU 订单数"]
    raw_row = {"日期": "2026-03-01", "订单数": 10, "SKU 订单数": 14}

    stored_row = ingest_with_template_headers(template_headers, raw_row)

    assert "订单数" in stored_row
    assert "SKU 订单数" in stored_row
```

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -k template -v`
Expected: FAIL before runtime alignment.

- [ ] **Step 3: Ensure template-resolved headers are passed through unchanged for raw storage**

Implementation rule:

- template header identity controls which columns are read
- raw storage must preserve those source columns unchanged

- [ ] **Step 4: Re-run the focused tests**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/data_sync_service.py backend/services/data_ingestion_service.py backend/tests/test_data_ingestion_raw_contract.py
git commit -m "fix: make template-guided sync preserve raw source columns"
```

## Task 6: Add Success-Path Contract Validation For Metric Date And Template Linkage

**Files:**
- Modify: `backend/services/data_ingestion_service.py`
- Modify: `backend/services/raw_data_importer.py`
- Modify: `backend/tests/test_metric_date_template_rules.py`

- [ ] **Step 1: Extend a failing date-contract test**

```python
def test_metric_date_must_not_disagree_with_file_level_date_range_without_explicit_rule():
    file_date = ("2026-05-16", "2026-05-16")
    row_metric_date = "2026-04-16"

    assert validate_metric_date_contract(file_date, row_metric_date) is False
```

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`
Expected: FAIL because the current success path does not enforce this contract.

- [ ] **Step 3: Implement post-ingest contract checks**

Required checks:

- metric date must agree with file-level range unless a documented exception exists
- template linkage metadata should be preserved when a template was used
- success must not be reported if these checks fail

- [ ] **Step 4: Re-run the focused tests**

Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/data_ingestion_service.py backend/services/raw_data_importer.py backend/tests/test_metric_date_template_rules.py
git commit -m "fix: enforce metric date and template success contracts"
```

## Task 7: Document Final Runtime Alignment

**Files:**
- Modify: `docs/architecture/DATA_SYNC_CONTRACT.md`
- Modify: `docs/architecture/DATA_SYNC_GAP_ANALYSIS.md`

- [ ] **Step 1: Update contract notes to reflect implemented behavior**

Add only the clarified runtime facts. Do not rewrite architecture philosophy.

- [ ] **Step 2: Mark resolved gaps in the gap-analysis document**

For each fixed gap, add a short note under the relevant section:

```markdown
Status: Resolved by <commit or date>, runtime now preserves raw source fields before semantic unification.
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/DATA_SYNC_CONTRACT.md docs/architecture/DATA_SYNC_GAP_ANALYSIS.md
git commit -m "docs: update data sync contract alignment status"
```

## Verification Checklist

- [ ] Run: `python -m pytest backend/tests/test_data_ingestion_raw_contract.py -v`
- [ ] Run: `python -m pytest backend/tests/test_data_sync_error_classification.py -v`
- [ ] Run: `python -m pytest backend/tests/test_data_sync_status_contract.py -v`
- [ ] Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`
- [ ] Run any additional narrow regression test discovered while implementing
- [ ] Manually verify one analytics file with both `订单数` and `SKU 订单数` can be stored in raw without collapse
- [ ] Manually verify one prior “success” path still writes consistent task/file status

## Risks

- legacy callers may still assume normalized raw keys
- dynamic-column logic may implicitly depend on the old normalization behavior
- template linkage fields may differ across existing dynamic raw tables
- some historical data may remain inconsistent and require later backfill

## Out Of Scope

- large semantic SQL redesign
- historical raw-data migration/backfill
- dashboard query rewrites
- collection/export-side refactors unrelated to sync runtime contract
