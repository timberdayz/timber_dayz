# Data Sync Gap Analysis

This document compares the current data-sync implementation against the active contract defined in `docs/architecture/DATA_SYNC_CONTRACT.md`.

## Scope

This analysis focuses on the file-based sync pipeline:

```text
catalog_files
-> data-sync router
-> task_center_tasks
-> data_sync_service
-> data_ingestion_service
-> b_class raw
-> sql/semantic
```

## Summary

The current implementation does not fully honor the raw-first, semantic-later contract.

The most important gaps are:

1. raw ingestion performs semantic-style field-name collapse before persistence
2. template success does not guarantee raw-preserving ingestion behavior
3. task/file/progress state is not consistently aligned
4. error attribution is misleading
5. successful ingestion can still produce semantically suspicious stored data

## Gap Matrix

| Gap | Severity | Contract Section | Current Behavior | Primary Files |
|-----|----------|------------------|------------------|---------------|
| Raw pre-collapse of coexisting source fields | P0 | Raw Ingestion Layer | Resolved on the primary ingestion path; raw rows are now passed through without semantic key collapse | `backend/services/data_ingestion_service.py` |
| Template does not govern raw preservation | P0 | Template Contract | Partially resolved; template-recognized headers are now preserved into raw importer inputs | `backend/services/data_sync_service.py`, `backend/services/data_ingestion_service.py` |
| Error stage misclassification | P1 | Error Classification Contract | Resolved for raw importer/storage failures on the primary path; stage-aware error label now used | `backend/services/data_ingestion_service.py` |
| Status-source split | P1 | Status Contract | Partially resolved on single-file sync path; file status/error/timestamp now align better, compatibility surfaces still exist | `backend/services/data_sync_service.py`, `backend/services/sync_progress_tracker.py`, routers/tasks |
| Semantic suspicion on success path | P1 | Raw Fidelity / Status Contract | Resolved on the primary raw-ingestion path; `template_id` and file date range reach raw importer, and out-of-range `metric_date` now fails before persistence | `backend/services/data_ingestion_service.py`, `backend/services/raw_data_importer.py`, raw tables |
| Historical variable/connection instability | P2 | Execution Reliability | historical failures show `import_result` scope bugs and asyncpg connection lifecycle problems | `backend/services/data_ingestion_service.py`, task workers |

## Detailed Gaps

### Gap 1: Raw Ingestion Collapses Distinct Source Columns Before Persistence

**Severity:** P0

**Contract mismatch:** raw ingestion must preserve source distinctions when two source columns coexist in the same file.

**Observed behavior:**

- `normalize_row_fields_for_domain()` rewrites each row into a normalized key map before raw persistence
- if two source columns normalize to the same target key, ingestion fails immediately
- this means the system cannot preserve the original coexisting columns in raw

**Evidence:**

- latest failed task: `single_file_2391_c387ea16`
- file: `catalog_files.id=2391`
- error: `Field normalization collision in domain=analytics: 订单数 and SKU 订单数 both map to 订单数`

**Primary code path:**

- `backend/services/data_ingestion_service.py`
  - `normalize_field_name_for_domain()`
  - `normalize_row_fields_for_domain()`
  - row normalization before `RawDataImporter.async_batch_insert_raw_data()`

**Why this matters:**

Status: Resolved on 2026-05-25 for the primary raw-ingestion path. Raw rows are now preserved before raw persistence, and focused tests protect this behavior.

### Gap 2: Template Match Does Not Control Raw-Preservation Behavior

**Severity:** P0

**Contract mismatch:** templates should govern how the file is read and how raw source columns are identified, but they should not allow later logic to destroy source distinctions.

**Observed behavior:**

- template match determines `header_row`
- template drift checks compare headers
- after that, the row still goes through generic field normalization before raw insert

**Evidence:**

- analytics monthly published template exists for `tiktok + analytics + monthly`
- template `header_row=8`
- template `header_columns` include both `订单数` and `SKU 订单数`
- direct file read confirms `header_row=8` is correct
- task still fails later because generic normalization collapses both fields

**Primary code path:**

- `backend/services/data_sync_service.py`
- `backend/services/data_ingestion_service.py`
- `backend/domains/data_platform/routers/field_mapping_templates.py`

Status: Partially resolved on 2026-05-25. Template-recognized headers and `template_id` now pass through to raw ingestion, but broader runtime semantic governance still remains downstream work.

### Gap 3: Error Classification Is Misleading

**Severity:** P1

**Contract mismatch:** errors must be attributed to the stage where they actually occur.

**Observed behavior:**

- row-field collision is thrown before SQL insert
- returned message is still labeled `数据入库失败:RawDataImporter异常,...`

**Why this matters:**

- sends engineers to the wrong module during debugging
- makes UI and history records less trustworthy
- hides true failure distribution across preview/template/raw-insert stages

Status: Resolved on 2026-05-25 for the raw-storage failure path. Focused tests now require stage-aware error labels.

### Gap 4: Status Sources Are Split And Can Drift

**Severity:** P1

**Contract mismatch:** task state, file state, and any compatibility progress state should not contradict each other.

**Observed behavior:**

- some successful syncs exist in `task_center_tasks` without corresponding `sync_progress_tasks` entries
- failed files may have `catalog_files.status='failed'` while `error_message` remains empty
- success and failure metadata are not written consistently to all surfaces

**Affected records already observed during investigation:**

- successful task on file `2388`: task state recorded, progress state absent
- failed file `2391`: file status failed, but `catalog_files.error_message` not populated

Status: Partially resolved on 2026-05-25 for the primary single-file sync path. `catalog_files.status`, `catalog_files.error_message`, and `catalog_files.last_processed_at` are now updated coherently there. Wider compatibility cleanup is still pending.

### Gap 5: Success Path Can Still Produce Semantically Suspicious Raw Data

**Severity:** P1

**Contract mismatch:** success should not be reported when required file/date/template contracts are clearly violated.

**Observed behavior:**

- prior successful file `2388` wrote raw rows whose `metric_date` did not match file-level date metadata
- template linkage was also missing in the written raw rows (`template_id` null)

**Why this matters:**

- downstream semantic logic starts from a compromised raw baseline
- success state becomes weaker as an operational signal

Status: Resolved on 2026-05-25 for the primary raw-ingestion path. The runtime now has a reusable `validate_metric_date_contract()` helper, passes `template_id` plus file date range metadata into raw ingestion, and rejects out-of-range `metric_date` values before persistence.

### Gap 6: Reliability Bugs Have Appeared In Multiple Layers

**Severity:** P2

**Observed historical evidence:**

- `import_result未定义`
- asyncpg connection closed during batch task execution
- preview/executor-related failures

**Interpretation:**

This is not only a contract-boundary issue. The sync pipeline also has runtime reliability debt. That debt should be addressed after the contract boundary is restored.

## File-Level Difference Map

### `backend/services/data_sync_service.py`

Current role:

- template resolution
- header-row selection
- header-drift blocking
- file status transitions

Contract concern:

- should remain the place for raw-read orchestration
- should not silently permit later raw-field collapse after template success

### `backend/services/data_ingestion_service.py`

Current role:

- file parsing handoff
- row normalization
- data hash generation
- raw importer call
- file success/failure transitions

Contract concern:

- currently mixes raw-ingestion responsibilities with semantic-style field unification
- should be reduced to raw-safe normalization and storage preparation

### `backend/services/raw_data_importer.py`

Current role:

- dynamic table resolution
- dynamic column handling
- batch raw insert/upsert

Contract concern:

- should receive already raw-safe rows
- should not be blamed for failures that happen before insertion

### `backend/domains/data_platform/routers/field_mapping_templates.py`

Current role:

- template persistence
- header binding storage
- semantic hint storage

Contract concern:

- current template model already stores enough signal to support better raw preservation
- runtime ingestion does not yet fully honor that signal

## Priority Order For Fixing

1. restore raw/semantic boundary
2. make template behavior authoritative for raw reading without authorizing raw collapse
3. align task/file/progress/error state contracts
4. add success-path contract validation
5. clean up historical runtime reliability bugs

## Non-Goals For The First Refactor

- redesign all semantic SQL at once
- rebuild dashboard marts
- broad rename of all legacy sync modules
- historical backfill of all old raw records in the same change

Those can follow after the contract boundary is restored.
