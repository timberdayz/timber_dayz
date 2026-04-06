# Collection Config Main-Account Scoping Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope collection configs from platform-level records to `platform + main_account_id` records, add the missing list filters and dialog linkage, and keep config execution/scheduling behavior stable by continuing to run through `config_id`.

**Architecture:** Add `main_account_id` to the config header, validate every saved shop scope against the selected platform and main account, and extend list/coverage queries with the new filter dimensions. On the frontend, derive platform and main-account options from real account data, fix the platform select layout bug, and rebuild the dialog scope list from the selected `platform + main_account_id` pair instead of platform-only selection.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Alembic-style migrations under `migrations/`, Vue 3, Element Plus, existing frontend script tests, existing collection runtime and scheduler services

---

## File Structure

### Existing files to modify

- `modules/core/db/schema.py`
  Responsibility: add `main_account_id` to `CollectionConfig` and adjust constraints/indexes.
- `modules/core/db/__init__.py`
  Responsibility: export any updated ORM symbols if needed after schema changes.
- `backend/schemas/collection.py`
  Responsibility: add `main_account_id` to config create/update/response contracts and query filter contracts if modeled here.
- `backend/routers/collection_config.py`
  Responsibility: extend config list/coverage filters, enforce `platform + main_account_id` validation, and return main-account fields.
- `backend/services/collection_contracts.py`
  Responsibility: host reusable helpers for scope normalization and config summary if validation extraction is needed during implementation.
- `backend/tests/test_collection_config_api.py`
  Responsibility: cover CRUD, query filters, and invalid mixed-main-account scope writes.
- `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: lock the frontend-facing shape for config payloads and filters.
- `backend/tests/test_collection_scheduler_capability_filter.py`
  Responsibility: verify config execution behavior still works after config-header scoping changes.
- `frontend/src/api/collection.js`
  Responsibility: expose the new config query filters and request/response fields.
- `frontend/src/views/collection/CollectionConfig.vue`
  Responsibility: replace hardcoded platform options, add main-account filters/fields, fix select width, and scope dialog shops by `platform + main_account_id`.
- `frontend/scripts/collectionConfigGranularityUi.test.mjs`
  Responsibility: continue locking list-level collection config UI expectations after filters grow.
- `frontend/scripts/collectionConfigShopScopeUi.test.mjs`
  Responsibility: continue locking shop-scope dialog structure after main-account linkage is added.

### New files to create

- `migrations/versions/20260406_collection_config_main_account_scope.py`
  Responsibility: clean legacy config rows if required by the approved strategy, add `main_account_id`, and add supporting constraints/indexes.
- `backend/tests/test_collection_config_main_account_filters.py`
  Responsibility: verify list/coverage filters and save-time main-account validation behavior.
- `frontend/scripts/collectionConfigMainAccountUi.test.mjs`
  Responsibility: verify platform/main-account UI behavior, non-hardcoded platform options, and select layout hooks.

---

### Task 1: Add Config Main-Account Persistence And Cleanup Strategy

**Files:**
- Create: `migrations/versions/20260406_collection_config_main_account_scope.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Test: `backend/tests/test_collection_config_main_account_filters.py`

- [ ] **Step 1: Write the failing persistence/cleanup test**

Add coverage that proves:
- `CollectionConfig` requires `main_account_id`
- config rows are unique per `platform + main_account_id + name`
- legacy configs without `main_account_id` are not expected to survive the approved cleanup path

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
pytest backend/tests/test_collection_config_main_account_filters.py -q
```

Expected: FAIL because the model and migration do not yet expose `main_account_id`.

- [ ] **Step 3: Implement the minimal schema and migration**

Implement:
- `CollectionConfig.main_account_id` in `modules/core/db/schema.py`
- foreign key to `core.main_accounts.main_account_id`
- updated unique/index definitions for main-account-scoped configs
- migration file that applies the approved destructive cleanup for legacy collection configs before making `main_account_id` required

Keep the existing scheduler/config execution columns intact. This task is only about persistence shape and database truth.

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
pytest backend/tests/test_collection_config_main_account_filters.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260406_collection_config_main_account_scope.py modules/core/db/schema.py modules/core/db/__init__.py backend/tests/test_collection_config_main_account_filters.py
git commit -m "feat: add main-account scoping to collection configs"
```

### Task 2: Extend Backend Contracts, Filters, And Save-Time Validation

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/tests/test_collection_config_api.py`
- Modify: `backend/tests/test_collection_frontend_contracts.py`
- Modify: `backend/tests/test_collection_config_main_account_filters.py`
- Test: `backend/tests/test_collection_config_api.py`

- [ ] **Step 1: Write the failing backend contract tests**

Cover:
- config create/update payloads require `main_account_id`
- `GET /collection/configs` accepts `platform`, `main_account_id`, `date_range_type`, `execution_mode`, `schedule_enabled`, `is_active`
- `GET /collection/config-coverage` accepts `platform` and `main_account_id`
- save requests fail when any shop scope belongs to another main account
- config detail/list payloads return `main_account_id` and, if implemented, `main_account_name`

- [ ] **Step 2: Run the focused backend tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py backend/tests/test_collection_config_main_account_filters.py -q
```

Expected: FAIL because the router/schema still model platform-only config ownership and narrow query filters.

- [ ] **Step 3: Implement the minimal backend contract changes**

Implement:
- `main_account_id` on create/update/response models
- config list filtering for:
  - `platform`
  - `main_account_id`
  - `date_range_type`
  - `execution_mode`
  - `schedule_enabled`
  - `is_active`
- coverage filtering for `main_account_id`
- save-time validation that every `shop_scope.shop_account_id` belongs to the selected `platform + main_account_id`

If helper extraction in `backend/services/collection_contracts.py` reduces duplication, keep the helpers narrow and focused on validation/summary building.

- [ ] **Step 4: Re-run the focused backend tests**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py backend/tests/test_collection_config_main_account_filters.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/services/collection_contracts.py backend/tests/test_collection_config_api.py backend/tests/test_collection_frontend_contracts.py backend/tests/test_collection_config_main_account_filters.py
git commit -m "feat: filter and validate collection configs by main account"
```

### Task 3: Rebuild Frontend Filters And Dialog Linkage Around Main Accounts

**Files:**
- Create: `frontend/scripts/collectionConfigMainAccountUi.test.mjs`
- Modify: `frontend/src/api/collection.js`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/scripts/collectionConfigGranularityUi.test.mjs`
- Modify: `frontend/scripts/collectionConfigShopScopeUi.test.mjs`
- Test: `frontend/scripts/collectionConfigMainAccountUi.test.mjs`

- [ ] **Step 1: Write the failing frontend tests**

Cover:
- platform options are not hardcoded `el-option` literals in the page
- list toolbar contains filters for platform, main account, date range, execution mode, and schedule enabled
- dialog contains a main-account selector
- dialog scope rows are derived from `platform + main_account_id`
- platform select wrapper still allows the selected value to render at full width

- [ ] **Step 2: Run the focused frontend tests and verify failure**

Run from the `frontend/` directory:

```bash
node --test scripts/collectionConfigMainAccountUi.test.mjs scripts/collectionConfigGranularityUi.test.mjs scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: FAIL because the page still hardcodes platform options, lacks main-account filters, and scopes dialog rows by platform only.

- [ ] **Step 3: Implement the minimal frontend changes**

Implement:
- derive platform options from loaded account data using normalized lowercase values
- derive main-account options from the selected platform
- add list filters for `main_account_id`, `date_range_type`, `execution_mode`, `schedule_enabled`
- extend config fetch calls to send those filter params
- add `form.main_account_id`
- clear and rebuild dialog scope rows when platform or main account changes
- fix the platform select layout bug without removing needed test hooks

Do not pull in unrelated UI redesign. Keep the current page structure and only add the new controls/linkage required by the spec.

- [ ] **Step 4: Re-run the focused frontend tests**

Run from the `frontend/` directory:

```bash
node --test scripts/collectionConfigMainAccountUi.test.mjs scripts/collectionConfigGranularityUi.test.mjs scripts/collectionConfigShopScopeUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/collection.js frontend/src/views/collection/CollectionConfig.vue frontend/scripts/collectionConfigMainAccountUi.test.mjs frontend/scripts/collectionConfigGranularityUi.test.mjs frontend/scripts/collectionConfigShopScopeUi.test.mjs
git commit -m "feat: scope collection config ui by main account"
```

### Task 4: Verify Config Execution Stability And Final Regression Coverage

**Files:**
- Modify: `backend/tests/test_collection_scheduler_capability_filter.py`
- Modify: `progress.md`
- Test: `backend/tests/test_collection_scheduler_capability_filter.py`

- [ ] **Step 1: Write the failing execution-regression test**

Cover:
- running a config still expands tasks through `config_id`
- main-account-scoped config headers do not break capability filtering
- scheduled/manual config execution does not require changes to the config-run entrypoint contract

- [ ] **Step 2: Run the focused regression test to verify failure or gap**

Run:

```bash
pytest backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: either FAIL because test expectations still assume platform-only configs, or expose missing assertions that need to be added before final verification.

- [ ] **Step 3: Implement the minimal regression-safe fixes**

Implement only what is needed so:
- config execution still works with the new header field
- no scheduler/config execution code starts depending on platform-wide config ownership again

Do not rewrite task creation or scheduler registration if the existing `config_id`-based path already passes once headers and validation are updated.

- [ ] **Step 4: Run final verification commands**

Run:

```bash
pytest backend/tests/test_collection_config_api.py backend/tests/test_collection_config_main_account_filters.py backend/tests/test_collection_frontend_contracts.py backend/tests/test_collection_scheduler_capability_filter.py -q
```

Run from `frontend/`:

```bash
node --test scripts/collectionConfigMainAccountUi.test.mjs scripts/collectionConfigGranularityUi.test.mjs scripts/collectionConfigShopScopeUi.test.mjs
```

If either stack requires additional safety checks because of touched files, run the smallest meaningful extra verification command and record the result in `progress.md`.

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_collection_scheduler_capability_filter.py progress.md
git commit -m "test: verify main-account-scoped collection config execution"
```

## Local Review Checklist

- [ ] Plan covers the destructive legacy-config cleanup approved by the user.
- [ ] Every changed backend contract named in the spec appears in at least one task.
- [ ] Frontend tasks explicitly cover non-hardcoded platform options and select-width regression.
- [ ] Verification includes both backend and frontend collection-config coverage.

## Notes For Execution

- Execute this plan only inside `F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\codex-collection-config-main-account-scope`.
- Respect `@test-driven-development` for each task: write the failing test, run it, then implement the minimal code.
- Respect `@verification-before-completion` before claiming any task or final result is complete.
- Keep `task_plan.md`, `findings.md`, and `progress.md` updated as work advances.
