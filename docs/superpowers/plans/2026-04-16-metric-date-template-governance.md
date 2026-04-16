# Metric Date Template Governance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `metric_date` deterministic by storing template-declared date parsing rules and enforcing them during governed ingestion.

**Architecture:** Extend `core.field_mapping_templates` with a JSONB rule payload, validate those rules in template APIs, expose them in the template-management UI, and pass them into `RawDataImporter` so governed ingestion uses strict declared parsing instead of heuristics. Historical remediation remains a separate execution phase after code rollout.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Vue 3, Element Plus, pytest

---

## File Map

**Schema and migration**

- Modify: `modules/core/db/schema.py`
- Create: `migrations/versions/20260416_add_field_parse_rules_to_templates.py`
- Test: `backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py`

**Backend template contract**

- Modify: `backend/schemas/field_mapping_template.py`
- Modify: `backend/services/field_mapping_template_service.py`
- Modify: `backend/routers/field_mapping_templates.py`
- Test: `backend/tests/test_field_mapping_template_update_context_api.py`

**Backend parsing and ingestion**

- Modify: `modules/services/smart_date_parser.py`
- Modify: `backend/services/raw_data_importer.py`
- Modify: `backend/routers/field_mapping_ingest.py`
- Test: `backend/tests/test_data_ingestion_raw_import_failure.py`
- Create: `backend/tests/test_metric_date_template_rules.py`

**Frontend template authoring**

- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Create: `frontend/scripts/metricDateTemplateGovernanceUi.test.mjs`

**Operational follow-up**

- Modify: `docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md`
- Create: `docs/guides/METRIC_DATE_TEMPLATE_GOVERNANCE_RUNBOOK.md`

---

### Task 1: Add Template Rule Storage

**Files:**
- Modify: `modules/core/db/schema.py`
- Create: `migrations/versions/20260416_add_field_parse_rules_to_templates.py`
- Test: `backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py`

- [ ] **Step 1: Write the failing migration/schema contract test**

Add a test asserting `core.field_mapping_templates` includes `field_parse_rules JSONB` and the ORM model exposes it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py -v`

Expected: failure mentioning missing `field_parse_rules`.

- [ ] **Step 3: Add the ORM field and migration**

Implement:

- `field_parse_rules = Column(JSONB, nullable=True, comment="字段解析规则(JSONB数组)")`
- Alembic migration that adds the column with backward-compatible nullability

- [ ] **Step 4: Run the migration/schema test again**

Run: `python -m pytest backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/core/db/schema.py migrations/versions/20260416_add_field_parse_rules_to_templates.py backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py
git commit -m "feat: add template field parse rules storage"
```

### Task 2: Extend Template API Contract

**Files:**
- Modify: `backend/schemas/field_mapping_template.py`
- Modify: `backend/services/field_mapping_template_service.py`
- Modify: `backend/routers/field_mapping_templates.py`
- Test: `backend/tests/test_field_mapping_template_update_context_api.py`

- [ ] **Step 1: Write failing API tests for parse-rule persistence and validation**

Add tests that:

- saving a template with `metric_date` mapping but no parse rule is rejected
- saving a valid parse rule persists it
- update-context payload returns `field_parse_rules`

- [ ] **Step 2: Run the template API tests to verify failure**

Run: `python -m pytest backend/tests/test_field_mapping_template_update_context_api.py -v`

Expected: FAIL on missing response fields or missing validation.

- [ ] **Step 3: Add request/response models and save/list/get support**

Implement:

- typed parse-rule schemas in `backend/schemas/field_mapping_template.py`
- persistence in `FieldMappingTemplateService.save_template()`
- response payload inclusion in list/get/update-context
- validation that date-target fields require parse rules

- [ ] **Step 4: Run the template API tests again**

Run: `python -m pytest backend/tests/test_field_mapping_template_update_context_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/field_mapping_template.py backend/services/field_mapping_template_service.py backend/routers/field_mapping_templates.py backend/tests/test_field_mapping_template_update_context_api.py
git commit -m "feat: validate and expose template date parse rules"
```

### Task 3: Add Strict Declared Date Parser

**Files:**
- Modify: `modules/services/smart_date_parser.py`
- Create: `backend/tests/test_metric_date_template_rules.py`

- [ ] **Step 1: Write failing parser tests**

Cover at minimum:

- `2026-03-12` with `yyyy-mm-dd` -> `2026-03-12`
- `2026-03-12 12:00:00` with `yyyy-mm-dd hh:mm:ss` -> `2026-03-12`
- `12-03-2026` with `dd-mm-yyyy` -> `2026-03-12`
- `14-04-2026-14-04-2026` with range rule + `start` -> `2026-04-14`
- invalid value under strict declared rule -> `None` or explicit parse error

- [ ] **Step 2: Run parser tests to verify failure**

Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`

Expected: FAIL because strict declared parser does not yet exist.

- [ ] **Step 3: Implement declared-format parsing**

Add a strict parser entry point that:

- does not use `pandas.to_datetime` guessing
- maps declared formats to exact parsing functions
- supports `single_date` and `date_range`
- returns deterministic results only

- [ ] **Step 4: Re-run parser tests**

Run: `python -m pytest backend/tests/test_metric_date_template_rules.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/services/smart_date_parser.py backend/tests/test_metric_date_template_rules.py
git commit -m "feat: add strict declared date parser"
```

### Task 4: Make Governed Ingestion Use Template Rules

**Files:**
- Modify: `backend/routers/field_mapping_ingest.py`
- Modify: `backend/services/raw_data_importer.py`
- Modify: `backend/services/field_mapping_template_service.py`
- Test: `backend/tests/test_data_ingestion_raw_import_failure.py`
- Test: `backend/tests/test_metric_date_template_rules.py`

- [ ] **Step 1: Write failing ingestion tests**

Add tests proving:

- governed ingestion passes template parse rules into raw import
- `metric_date` comes from declared source column, not heuristic scanning
- invalid date under strict rule does not fall back to `date.today()`

- [ ] **Step 2: Run ingestion tests to verify failure**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_import_failure.py backend/tests/test_metric_date_template_rules.py -v`

Expected: FAIL on fallback behavior or missing template-rule propagation.

- [ ] **Step 3: Thread template rules into raw ingestion**

Implement:

- template lookup in `/ingest`
- pass `template_id` and `field_parse_rules` into `RawDataImporter.batch_insert_raw_data()`
- in `RawDataImporter`, prefer template-declared rules over date-field scanning
- remove `date.today()` fallback in governed path

- [ ] **Step 4: Re-run ingestion tests**

Run: `python -m pytest backend/tests/test_data_ingestion_raw_import_failure.py backend/tests/test_metric_date_template_rules.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/field_mapping_ingest.py backend/services/raw_data_importer.py backend/services/field_mapping_template_service.py backend/tests/test_data_ingestion_raw_import_failure.py backend/tests/test_metric_date_template_rules.py
git commit -m "fix: enforce template date rules during ingestion"
```

### Task 5: Add Frontend Rule Authoring

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/DataSyncTemplates.vue`
- Modify: `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue`
- Create: `frontend/scripts/metricDateTemplateGovernanceUi.test.mjs`

- [ ] **Step 1: Write a failing frontend contract/UI script**

Add a lightweight script or component-level assertion that checks:

- date-target mappings surface parse-rule controls
- template save request includes `field_parse_rules`
- save action blocks when required date rules are missing

- [ ] **Step 2: Run the frontend script to verify failure**

Run: `node frontend/scripts/metricDateTemplateGovernanceUi.test.mjs`

Expected: FAIL because UI does not surface or submit parse rules yet.

- [ ] **Step 3: Implement minimal UI**

Implement:

- API client support for `field_parse_rules`
- form state for parse rules in template save/update
- required validation and inline error messaging
- display of existing rules in workbench detail

- [ ] **Step 4: Re-run the frontend script**

Run: `node frontend/scripts/metricDateTemplateGovernanceUi.test.mjs`

Expected: PASS

- [ ] **Step 5: Build the frontend**

Run: `npm run build`

Expected: build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/index.js frontend/src/views/DataSyncTemplates.vue frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue frontend/scripts/metricDateTemplateGovernanceUi.test.mjs
git commit -m "feat: add template date rule authoring ui"
```

### Task 6: Add Rollout Guardrails And Runbook

**Files:**
- Create: `docs/guides/METRIC_DATE_TEMPLATE_GOVERNANCE_RUNBOOK.md`
- Modify: `docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md`

- [ ] **Step 1: Document rollout and re-import procedure**

Describe:

- how to publish date-governed templates
- how to identify templates missing parse rules
- how to re-import affected files
- how to rebuild semantic/mart/monthly settlement data

- [ ] **Step 2: Link the new rule to existing data identity guidance**

Document that shop identity alignment and date governance are both required for correct shop-level finance attribution.

- [ ] **Step 3: Commit**

```bash
git add docs/guides/METRIC_DATE_TEMPLATE_GOVERNANCE_RUNBOOK.md docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md
git commit -m "docs: add metric date template governance runbook"
```

### Task 7: Full Verification

**Files:**
- No new files

- [ ] **Step 1: Run focused backend test suite**

Run:

```bash
python -m pytest \
  backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py \
  backend/tests/test_field_mapping_template_update_context_api.py \
  backend/tests/test_data_ingestion_raw_import_failure.py \
  backend/tests/test_metric_date_template_rules.py -v
```

Expected: PASS

- [ ] **Step 2: Run relevant existing pipeline regressions**

Run:

```bash
python -m pytest \
  backend/tests/test_orders_rmb_field_preservation.py \
  backend/tests/data_pipeline/test_orders_semantic_mapping.py -v
```

Expected: PASS

- [ ] **Step 3: Build frontend**

Run: `npm run build`

Expected: PASS

- [ ] **Step 4: Record rollout verification notes**

Capture:

- templates updated with date rules
- files selected for re-import
- months selected for finance rebuild

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: complete metric date template governance rollout"
```

## Execution Notes

- Do not remove legacy heuristic parsing for callers that are not yet template-governed until all known ingestion paths are audited.
- For governed finance-facing data-sync flows, strict declared parsing is mandatory.
- Treat fallback-to-today as a data corruption bug, not a resilience feature.
- Historical re-import should be executed only after all code and tests pass.
