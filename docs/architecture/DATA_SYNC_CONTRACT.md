# Data Sync Contract

This document defines the active architecture contract for file-based data sync in the PostgreSQL-first runtime.

The active repository rule entrypoint remains `AGENTS.md`. This document is an architecture reference for the data-sync pipeline.

## Goal

Ensure the data-sync pipeline preserves raw source fidelity first, then applies business-semantic unification in the PostgreSQL semantic layer.

This contract exists to prevent:

- raw-layer data loss caused by premature field-name normalization
- template behavior drifting away from runtime ingestion behavior
- task/file/progress status disagreement
- success states that still produce semantically incorrect stored data

## Canonical Flow

```text
catalog_files
-> data-sync router
-> task_center_tasks
-> data_sync_service
-> data_ingestion_service
-> b_class raw
-> sql/semantic
-> sql/mart
-> sql/api_modules
-> backend router
-> frontend
```

## Layer Contract

### 1. File Registration Layer

Primary record: `public.catalog_files`

Responsibilities:

- register file identity and storage location
- register platform/domain/granularity/sub-domain context
- register file-level date range metadata
- register file-level shop/account context

Must not:

- infer semantic metric aliases
- collapse raw field differences

### 2. Task Orchestration Layer

Primary record: `public.task_center_tasks`

Responsibilities:

- create task identity
- record runner metadata
- record task-level success/failure state
- record structured error summary
- record linkage to `catalog_files` and target source table

Must not:

- become a second semantic interpretation layer
- hide the actual failure stage behind inaccurate error labels

### 3. Template Resolution Layer

Primary components:

- template matcher
- field mapping templates
- header drift checks

Responsibilities:

- determine whether a file has a matching template
- determine the correct `header_row`
- preserve original header identity
- detect true template drift
- provide raw header bindings and optional semantic hints

Must not:

- silently rewrite raw source fields into semantic-standard field names during raw ingestion
- destroy distinctions between two source columns that both exist in the same file

### 4. Raw Ingestion Layer

Primary target: `b_class.fact_{platform}_{domain}_{sub_domain?}_{granularity}`

Responsibilities:

- preserve raw source field names and values
- attach ingestion metadata such as `file_id`, `platform_code`, `shop_id`, `metric_date`, `ingest_timestamp`
- preserve original headers in storage metadata
- preserve enough information to fully reconstruct semantic decisions later

Allowed transformations:

- header-row selection using template
- file/date/shop metadata extraction
- minimal technical normalization required for storage safety
- dynamic-column creation for raw field persistence

Must not:

- merge semantically similar source fields before raw persistence
- drop one source field because another field has similar business meaning
- rename raw source fields into canonical business metrics as a prerequisite for raw storage

Examples of fields that may be business-semantic synonyms but must still be preserved independently in raw when they appear as distinct source columns:

- `销售额`
- `GMV`
- `商品交易总额`
- `订单数`
- `SKU 订单数`
- `VAT(RMB)`
- `SST(RMB)`

### 5. Semantic Layer

Primary target: `sql/semantic/`

Responsibilities:

- unify cross-platform business semantics
- define canonical metric meaning
- resolve alias relationships
- define precedence when multiple source aliases are present
- split semantically distinct metrics when raw fields look similar but are not interchangeable

This is the correct layer for rules such as:

- `销售额`, `GMV`, `商品交易总额` -> canonical `gmv`
- `访客数`, `商品访客数`, `UV` -> canonical `visitor_count`

If multiple raw fields coexist in the same record and may represent different semantics, semantic logic must explicitly decide between:

- alias merge
- precedence selection
- separate canonical metrics

The semantic layer must never depend on raw ingestion having already destroyed the distinction.

## Raw Fidelity Rules

### Rule 1: Raw First

If a field exists in the source file, the raw layer should prefer preserving it over interpreting it.

### Rule 2: Coexisting Source Fields Stay Distinct

If two columns exist in the same file at the same time, raw ingestion must not collapse them into one field merely because their names appear semantically similar.

### Rule 3: Template Match Does Not License Raw Collapse

A matched template authorizes:

- how to read the file
- how to identify the columns

It does not authorize:

- dropping source distinctions before raw persistence

### Rule 4: Semantic Unification Is Delayed

Cross-platform field aliasing belongs to the semantic layer unless a transformation is strictly required for raw storage mechanics.

### Rule 5: Same-File Coexisting Fields Split By Default

This is an iron law across **all data domains**:

- if two different fields coexist in the same platform, same data domain, and same source file
- they must be treated as different business metrics by default
- they must be split, not merged

Only cross-platform, business-semantic equivalence is allowed to merge into a canonical semantic field.

See `docs/architecture/SEMANTIC_FIELD_RULES.md` for the current explicit semantic-layer rule set.

## Template Contract

Templates are responsible for raw-file interpretation, not final semantic collapse.

Template responsibilities:

- `header_row`
- original `header_columns`
- `header_bindings`
- optional semantic hints such as `display_name` and `semantic_role`
- parse rules for source-date extraction and similar source-interpretation tasks

Template non-responsibilities:

- forcing raw ingestion to collapse distinct coexisting columns into one canonical business field

### Required Behavior

When a template identifies both:

- `订单数`
- `SKU 订单数`

the runtime must preserve both raw source fields unless an explicit raw-storage rule says otherwise.

## Status Contract

### Single Source Of Truth By Concern

- Task execution state: `public.task_center_tasks`
- File processing state: `public.catalog_files`
- Legacy/progress compatibility: `core.sync_progress_tasks` only if still required by active UI or API contracts

### Required Consistency

If a sync task fails:

- `task_center_tasks.status` must be `failed`
- `task_center_tasks.error_summary` must identify the true failure stage
- `catalog_files.status` must reflect failed processing
- `catalog_files.error_message` should be populated with a user-relevant failure summary
- any compatibility progress record must not contradict the task result

If a sync task succeeds:

- task state, file state, and any progress state must agree
- success must not be reported if stored raw data violates required file/date/template contracts

## Error Classification Contract

Errors must be attributed to the stage where they actually occur.

Examples:

- header-row or preview failure -> preview/read stage
- template mismatch or drift -> template stage
- raw field collision before persistence -> raw normalization stage
- SQL insert failure -> raw importer/storage stage

The system must not label all pre-insert failures as `RawDataImporter异常`.

## Current Known Gaps Against This Contract

The current implementation has already shown evidence of the following contract gaps:

- raw-layer field-name normalization previously collapsed coexisting source columns before persistence
- template success previously did not guarantee raw-preserving ingestion behavior
- task/file/progress status records have historically disagreed
- successful ingestion can still write semantically suspicious dates if success-path contract checks are not fully enforced at runtime

These are implementation gaps, not reasons to change the contract.

## Current Runtime Alignment Status

As of 2026-05-25, the following runtime alignments are in place:

- raw row normalization now preserves original source keys before raw persistence
- template-recognized raw headers are passed through unchanged to raw storage
- raw importer failures are classified as `raw_storage` stage failures instead of being generically blamed on `RawDataImporter异常`
- `catalog_files.status`, `catalog_files.error_message`, and `catalog_files.last_processed_at` are aligned on the primary single-file sync path
- raw importer now receives `template_id` and file-level date range metadata (`file_date_from`, `file_date_to`)
- raw importer now enforces file-date-range contract at runtime and rejects out-of-range `metric_date` values before persistence

## Implementation Direction

Any future refactor or bug fix in data sync should preserve this ordering:

1. fix architecture boundary
2. restore runtime behavior to the contract
3. then optimize matching, normalization, and performance

Do not optimize field unification behavior before raw/semantic boundary ownership is restored.
