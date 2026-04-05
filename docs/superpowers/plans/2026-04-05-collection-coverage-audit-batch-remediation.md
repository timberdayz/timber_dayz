# Collection Coverage Audit And Batch Remediation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated collection coverage audit page and batch remediation workflow so operators can find shops missing daily, weekly, or monthly configs and create the missing configs in bulk.

**Architecture:** Reuse the existing shop-account-based collection config model and coverage aggregation endpoint, then add one focused batch remediation backend contract plus one dedicated frontend audit page. Keep the existing collection config page unchanged as the editing surface; the new audit page becomes the detection and remediation surface.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, existing collection config/task/history contracts

---

## File Structure

### Existing files to modify

- `backend/routers/collection_config.py`
  Responsibility: extend collection coverage response and add the batch remediation endpoint.
- `backend/schemas/collection.py`
  Responsibility: define batch remediation request/response schemas and any extra audit payload fields.
- `backend/services/collection_contracts.py`
  Responsibility: reuse and centralize granularity and domain/sub-domain normalization helpers.
- `frontend/src/api/collection.js`
  Responsibility: expose coverage audit and batch remediation API wrappers.
- `frontend/src/constants/collection.js`
  Responsibility: reuse domain labels, granularity labels, and sub-domain auto-select helpers from the config page.
- `frontend/src/router/index.js`
  Responsibility: register the new `CollectionCoverageAudit` route.
- `frontend/src/config/menuGroups.js`
  Responsibility: add the new page to the data-collection navigation group.
- `frontend/src/config/rolePermissions.js`
  Responsibility: grant the new page the same access scope as collection config / tasks / history.

### New files to create

- `frontend/src/views/collection/CollectionCoverageAudit.vue`
  Responsibility: dedicated audit and batch remediation UI.
- `backend/tests/test_collection_batch_remediation_api.py`
  Responsibility: verify batch remediation request validation, skip behavior, and one-config-per-shop persistence.
- `frontend/scripts/collectionCoverageAuditUi.test.mjs`
  Responsibility: verify the audit page exposes summary cards, filters, row actions, and batch remediation dialog flow.

### Existing tests to extend

- `backend/tests/test_collection_config_coverage_api.py`
  Responsibility: verify the coverage endpoint returns the extra audit-facing fields and correct summary counts.
- `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: lock the new audit page API contract and frontend-facing payload shape.

---

## Task 1: Extend Coverage Audit Contracts

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Test: `backend/tests/test_collection_config_coverage_api.py`
- Test: `backend/tests/test_collection_frontend_contracts.py`

- [ ] **Step 1: Write the failing backend coverage tests**

Add test cases for:

- `GET /api/collection/config-coverage` returning:
  - `shop_type`
  - `is_partially_covered`
  - `recommended_domains`
- summary counts for:
  - total shops
  - daily covered / missing
  - weekly covered / missing
  - monthly covered / missing
  - partially covered shops

- [ ] **Step 2: Run the focused coverage tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: FAIL because the current coverage contract does not yet expose all audit fields.

- [ ] **Step 3: Implement the minimal schema and router changes**

Add:

- response fields in `backend/schemas/collection.py`
- coverage item enrichment in `backend/routers/collection_config.py`
- summary counters for the audit page

Keep the existing endpoint path unchanged so the current config page can continue reusing it.

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/tests/test_collection_config_coverage_api.py backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: extend collection coverage audit contracts"
```

## Task 2: Add Batch Remediation Backend Flow

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/services/collection_contracts.py`
- Test: `backend/tests/test_collection_batch_remediation_api.py`

- [ ] **Step 1: Write the failing batch remediation API tests**

Cover:

- request validation for `shop_account_ids` and `granularity`
- one config is created per uncovered shop
- target shops already covered for the requested granularity are skipped
- new configs are created as:
  - `execution_mode = headless`
  - `is_active = true`
- domains come from saved shop capability
- missing shop capability falls back to shop-type defaults
- sub-domains are auto-selected

- [ ] **Step 2: Run the focused backend remediation test and verify failure**

Run:

```bash
pytest backend/tests/test_collection_batch_remediation_api.py -q
```

Expected: FAIL because the endpoint does not exist yet.

- [ ] **Step 3: Implement the minimal backend remediation logic**

Add:

- request / response schemas in `backend/schemas/collection.py`
- `POST /api/collection/configs/batch-remediate` in `backend/routers/collection_config.py`
- helper logic in `backend/services/collection_contracts.py` only if it reduces duplication for:
  - domain derivation
  - sub-domain auto-selection
  - granularity-specific skip checks

Do not introduce templates or inheritance logic in this task.

- [ ] **Step 4: Re-run the focused backend remediation test**

Run:

```bash
pytest backend/tests/test_collection_batch_remediation_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/services/collection_contracts.py backend/tests/test_collection_batch_remediation_api.py
git commit -m "feat: add collection config batch remediation api"
```

## Task 3: Build The Collection Coverage Audit Page

**Files:**
- Create: `frontend/src/views/collection/CollectionCoverageAudit.vue`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/constants/collection.js`
- Test: `frontend/scripts/collectionCoverageAuditUi.test.mjs`

- [ ] **Step 1: Write the failing UI script test**

Cover:

- summary cards render total shops and missing counts
- table rows show per-shop daily / weekly / monthly coverage badges
- filters exist for platform, main account, region, shop type, and coverage state
- row actions exist for `Go To Config`, `Remediate Daily`, `Remediate Weekly`, `Remediate Monthly`
- multi-select enables batch remediation actions

- [ ] **Step 2: Run the UI script test and verify failure**

Run:

```bash
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: FAIL because the page does not exist yet.

- [ ] **Step 3: Implement the new page**

Build:

- summary cards section
- filter bar
- table with per-granularity coverage badges
- batch action bar
- refresh behavior after remediation

Keep the page focused on auditing and remediation. Do not embed the full config editor into this page.

- [ ] **Step 4: Re-run the UI script test**

Run:

```bash
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionCoverageAudit.vue frontend/src/api/collection.js frontend/src/constants/collection.js frontend/scripts/collectionCoverageAuditUi.test.mjs
git commit -m "feat: add collection coverage audit page"
```

## Task 4: Add Batch Remediation Dialog And API Wiring

**Files:**
- Modify: `frontend/src/views/collection/CollectionCoverageAudit.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `frontend/scripts/collectionCoverageAuditUi.test.mjs`

- [ ] **Step 1: Extend the failing UI script test**

Cover:

- opening batch remediation dialog from multi-select actions
- dialog shows:
  - selected shop count
  - target granularity
  - default execution mode `headless`
  - default state `enabled`
  - domains derived from shop capability
- partial success feedback is rendered when some shops are skipped

- [ ] **Step 2: Run the UI script test and verify failure**

Run:

```bash
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: FAIL until the dialog and request flow are connected.

- [ ] **Step 3: Implement remediation dialog and request flow**

Add:

- row-level remediation entry
- multi-row remediation entry
- confirmation dialog
- success / partial success / skip feedback
- coverage refresh after completion

- [ ] **Step 4: Re-run the UI script test**

Run:

```bash
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionCoverageAudit.vue frontend/src/api/collection.js frontend/scripts/collectionCoverageAuditUi.test.mjs
git commit -m "feat: wire collection batch remediation flow"
```

## Task 5: Register Navigation And Access

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/config/rolePermissions.js`
- Test: `backend/tests/test_collection_frontend_contracts.py`
- Test: `frontend/scripts/collectionCoverageAuditUi.test.mjs`

- [ ] **Step 1: Write or extend failing assertions for route and access wiring**

Cover:

- route path exists for the new page
- menu group contains the new route
- role permission map grants access alongside other collection pages

- [ ] **Step 2: Run the focused route / contract checks and verify failure**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: FAIL until route and menu wiring are present.

- [ ] **Step 3: Implement route and menu integration**

Add:

- route entry for `/collection-coverage-audit`
- menu group entry under the existing collection center section
- matching permission wiring

- [ ] **Step 4: Re-run the focused checks**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/index.js frontend/src/config/menuGroups.js frontend/src/config/rolePermissions.js backend/tests/test_collection_frontend_contracts.py frontend/scripts/collectionCoverageAuditUi.test.mjs
git commit -m "feat: register collection coverage audit navigation"
```

## Task 6: Full Verification And Operator Walkthrough

**Files:**
- Verify: `backend/routers/collection_config.py`
- Verify: `backend/schemas/collection.py`
- Verify: `frontend/src/views/collection/CollectionCoverageAudit.vue`
- Verify: `frontend/src/api/collection.js`
- Verify: `frontend/src/router/index.js`

- [ ] **Step 1: Run backend coverage and remediation tests**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py backend/tests/test_collection_batch_remediation_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend page contract checks**

Run:

```bash
node frontend/scripts/collectionCoverageAuditUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Run frontend static verification**

Run:

```bash
npm run build
npm run type-check
```

Expected: PASS

- [ ] **Step 4: Do operator walkthrough**

Manually verify:

- open `Collection Coverage Audit`
- filter to missing daily / weekly / monthly shops
- perform row-level remediation
- perform batch remediation
- confirm coverage refreshes after remediation
- confirm created configs appear in `Collection Config`

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add collection coverage audit and batch remediation"
```

## Implementation Notes

- Preserve the existing `CollectionConfig.vue` as the primary config editor.
- Do not add templates in this phase.
- Do not add main-account inheritance in this phase.
- Prefer focused helper additions over bloating `collection_config.py`.
- The collection frontend area already contains some historical garbled text in comments / labels; do not broaden scope into a full text cleanup unless the edits are directly adjacent to this feature.

