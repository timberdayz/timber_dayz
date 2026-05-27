# Metric Date Template Governance Design

**Date:** 2026-04-16

**Goal:** Eliminate date-guessing in the ingestion pipeline by moving `metric_date` parsing to explicit template rules, enforcing strict parsing during ingestion, and preventing silently corrupted month attribution in `b_class`, `semantic`, `mart`, and monthly settlement flows.

## 1. Background

The current ingestion chain still treats date parsing as a best-effort heuristic. That behavior was acceptable only while downstream modules were tolerant of small date drift. The finance settlement and shop-level profit chain are not tolerant: once `metric_date` lands in the wrong month, `orders -> semantic -> mart -> finance` all become wrong even though source rows and alias mappings are correct.

This is now a structural reliability issue, not a one-off bug:

- source files clearly contain valid date columns
- source rows clearly contain valid store labels
- monthly finance aggregation depends on `metric_date`
- current parsing still guesses instead of following a declared rule

The result is silent month misclassification, especially for `orders`, but the same parser is also reused by other data domains.

## 2. Evidence

### 2.1 Current Parser Still Guesses

The shared date parser in [smart_date_parser.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/services/smart_date_parser.py#L60) first tries `pandas.to_datetime(..., dayfirst=...)`. The row-level raw importer in [raw_data_importer.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/raw_data_importer.py#L295) explicitly calls that parser with `prefer_dayfirst=True`.

That means a value such as `2026-03-12` can be reinterpreted as `2026-12-03`, even though the year position already proves it is a `YYYY-MM-DD` style value.

### 2.2 Ingestion Still Has Silent Fallback Behavior

The raw importer writes:

- `period_start_date`
- `period_end_date`
- `metric_date = period_start_date`

If extraction fails, it falls back to `date.today()`. See [raw_data_importer.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/raw_data_importer.py#L424).

That behavior is unacceptable for finance-critical data because it converts a parsing failure into valid-looking but wrong data.

### 2.3 Template Layer Has No Date Parsing Contract

The active template model stores:

- `header_row`
- `sheet_name`
- `encoding`
- `header_columns`
- `deduplication_fields`

See [schema.py](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/core/db/schema.py#L2053) and [field_mapping_template.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/schemas/field_mapping_template.py#L13).

It does **not** store:

- which source column should drive `metric_date`
- which date format that column uses
- whether the column is a single date or a date range
- whether the start or end of a range should be used

So the active runtime still has no trustworthy parsing contract to follow.

### 2.4 Ingest Path Does Not Consume Template Parsing Rules

The active `/ingest` path in [field_mapping_ingest.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/domains/data_platform/routers/field_mapping_ingest.py#L379) normalizes raw rows and passes them into `RawDataImporter`, but it does not load or enforce template-level date parsing rules.

This means even if the template layer were extended, ingestion would still ignore it until the contract is explicitly threaded through.

### 2.5 Historical Signal Already Exists

There is an archived migration, [20250131_0013_add_template_parsing_config.py](/F:/Vscode/python_programme/AI_code/xihong_erp/migrations/versions_archived/20250131_0013_add_template_parsing_config.py), which shows the codebase has already moved template parsing config into the template table once before for `header_row`, `sub_domain`, `sheet_name`, and `encoding`.

The correct next step is to extend that same pattern to date parsing rules, not to build another heuristic parser.

## 3. Design Goals

This design must achieve the following:

1. Remove guess-based parsing from the `metric_date` chain.
2. Make date parsing a template contract, not a runtime guess.
3. Fail closed when template-declared dates cannot be parsed.
4. Support both single-date and date-range source columns.
5. Preserve compatibility for domains that do not need date parsing rules yet.
6. Allow historical re-import and month rebuild after the parser is fixed.

## 4. Options Considered

### 4.1 Option A: Fix `dayfirst` Heuristics Only

Change parser precedence so `YYYY-MM-DD` and `DD-MM-YYYY` parse correctly, but keep runtime auto-detection for everything else.

Pros:

- fastest short-term fix
- reduces current `orders` month drift

Cons:

- still leaves template semantics undefined
- still allows future regressions when new files arrive
- still requires parser guesses in finance-critical paths

### 4.2 Option B: Recommended

Introduce template-declared field parsing rules for date fields, then make ingestion consume those rules strictly.

Pros:

- aligns with the user's operational model
- eliminates parser ambiguity
- creates one source of truth for `metric_date`
- supports future manual governance in the template UI

Cons:

- touches schema, backend, frontend, and tests
- requires backfill/re-import for already affected data

### 4.3 Option C: File-Type Hardcoding

Encode platform/domain/granularity-specific date formats directly in backend code.

Pros:

- no frontend/template changes required initially

Cons:

- hides real file-level variation
- produces another config system outside templates
- breaks the operator-facing governance model

### 4.4 Recommendation

Choose **Option B**.

The system already treats template metadata as the contract for header row, sub-domain, and deduplication fields. Date parsing belongs in the same contract layer.

## 5. Target Rule Model

### 5.1 Core Principle

The system must stop asking, "What date does this string probably mean?"

It must instead ask, "What date format did the published template declare for this target field?"

### 5.2 Rule Structure

Add a new JSONB rule field to `core.field_mapping_templates`, proposed name:

- `field_parse_rules`

Initial rule shape:

```json
[
  {
    "target_field": "metric_date",
    "source_column": "订单日期",
    "value_kind": "single_date",
    "date_format": "yyyy-mm-dd hh:mm:ss",
    "strict": true
  },
  {
    "target_field": "period_start_date",
    "source_column": "日期区间",
    "value_kind": "date_range",
    "date_format": "dd-mm-yyyy-dd-mm-yyyy",
    "range_pick": "start",
    "strict": true
  },
  {
    "target_field": "period_end_date",
    "source_column": "日期区间",
    "value_kind": "date_range",
    "date_format": "dd-mm-yyyy-dd-mm-yyyy",
    "range_pick": "end",
    "strict": true
  }
]
```

### 5.3 Supported Initial Formats

Initial supported formats should be intentionally small:

- `yyyy-mm-dd`
- `yyyy/mm/dd`
- `yyyy-mm-dd hh:mm:ss`
- `yyyy/mm/dd hh:mm:ss`
- `dd-mm-yyyy`
- `dd/mm/yyyy`
- `dd-mm-yyyy hh:mm:ss`
- `dd/mm/yyyy hh:mm:ss`
- `dd-mm-yyyy-dd-mm-yyyy`
- `dd/mm/yyyy-dd/mm/yyyy`

No "auto" option should be allowed for finance-facing templates.

## 6. Template Governance Rules

### 6.1 Save-Time Validation

When a template maps any source column to one of these target fields:

- `metric_date`
- `period_start_date`
- `period_end_date`
- other date-sensitive standard fields later added by domain

the save API must require a matching entry in `field_parse_rules`.

If the user has declared a date target but not declared a parsing rule:

- template cannot be published
- API returns a clear validation error

### 6.2 Template Update Semantics

When a template enters update workbench flow, the update context response should surface:

- existing `field_parse_rules`
- which date targets currently have rule coverage
- whether new headers invalidate existing `source_column` bindings

This prevents a header rename from silently severing the date contract.

## 7. Ingestion Runtime Changes

### 7.1 Runtime Contract

The ingest path must load the published template by `template_id` or by current file/template match and pass `field_parse_rules` into the raw import path.

### 7.2 Raw Import Behavior

`RawDataImporter` should stop scanning for likely date columns when a template parsing rule is available.

New precedence:

1. template-declared rule
2. explicit runtime override if added in future
3. legacy heuristic only for non-governed old flows and only where business allows it

For governed data-sync file ingestion, template rule must always win.

### 7.3 Failure Mode

If a strict template rule exists and parsing fails:

- row must not be inserted into `b_class`
- file or row should be quarantined with a specific parse error
- the raw original value and expected `date_format` must be logged

The system must no longer fall back to `date.today()` in this path.

## 8. Parser Behavior Changes

### 8.1 Strict Format Parser

The shared parser should add a strict-format entry point, for example:

- `parse_date_by_declared_format(value, date_format, value_kind, range_pick)`

This function should not rely on `pandas.to_datetime` guessing rules.

### 8.2 Limited Non-Strict Legacy Support

The old heuristic parser can remain temporarily for legacy callers, but:

- it should no longer be used by template-governed ingestion
- it should stop preferring `dayfirst=True` blindly for ISO-like values

## 9. Data Model And Compatibility

### 9.1 Schema Change

Add `field_parse_rules JSONB NULL` to `core.field_mapping_templates`.

Null is allowed for backward compatibility while templates are upgraded.

### 9.2 Backward Compatibility Phase

During rollout:

- existing templates remain readable
- save/update APIs should accept empty `field_parse_rules` only when no governed date target is configured
- governance screens should flag templates that map date targets but lack parsing rules

### 9.3 Historical Data Remediation

After parser rollout, the team must:

1. identify affected files/templates
2. publish corrected templates with date rules
3. re-import affected B-class files
4. rebuild downstream semantic/mart outputs
5. rebuild finance monthly settlement snapshots for affected months

## 10. Frontend Requirements

The active field-mapping and template-management UI must allow operators to declare date rules when they map date fields.

The minimum frontend behavior should include:

- when user maps a column to `metric_date`, show required date-format controls
- when user maps a column to `period_start_date` / `period_end_date`, show range format and start/end selector
- block template publish until rules are valid
- show saved rules in template detail and template update workbench

Likely touch points include:

- [frontend/src/api/index.js](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/index.js)
- [frontend/src/views/DataSyncTemplates.vue](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/DataSyncTemplates.vue)
- [frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue)

Legacy archived field-mapping UI under `modules/apps/vue_field_mapping` may also need parity review if it is still used in maintenance flows.

## 11. Testing Strategy

Required coverage:

1. schema/migration contract test for `field_parse_rules`
2. template save API test that rejects date-target templates without rules
3. template update context API test that returns saved parse rules
4. strict parser tests for supported formats
5. ingest test proving template rules drive `metric_date`
6. ingest failure test proving invalid template-declared date does not fall back to today
7. pipeline regression test showing March orders stay in March

## 12. Non-Goals

This design does not attempt to:

- redesign all template metadata UX at once
- solve every historical free-form date format ever seen
- replace every legacy ingestion path in one step
- redesign monthly settlement formulas

The scope is specifically to make `metric_date` and range-date parsing deterministic and governable.

## 13. Recommended Rollout Order

1. Add schema support for `field_parse_rules`
2. Add backend save/update/list/get support for template rules
3. Add frontend authoring controls
4. Add strict parser entry point
5. Thread template rules into `/ingest` and `RawDataImporter`
6. Remove silent fallback in governed paths
7. Re-import affected files and rebuild March finance outputs

## 14. Decision

The system should no longer parse `metric_date` by heuristic guessing.

`metric_date` must be governed by template-declared field parsing rules, enforced strictly at ingest time, with failures quarantined rather than defaulted.

