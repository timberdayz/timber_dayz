# Collection Config Granularity And Coverage Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade collection config management to use shop-account-based configuration with daily/weekly/monthly views, shop capability auto-apply, and per-granularity coverage reminders without removing the current manual testing workflow.

**Architecture:** Keep `CollectionConfig` as the persistence model, but make its semantics explicit: configs are stored against shop account IDs and grouped in the UI by derived granularity. Add a backend coverage aggregation layer and enrich the config UI so it can group shop accounts by main account and region, auto-apply stored capabilities, and highlight missing daily/weekly/monthly coverage while still allowing manual headed/headless test configs.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Vue 3, Element Plus, existing collection config/task APIs, canonical main/shop account tables

---

## File Structure

### Existing files to modify

- `frontend/src/views/collection/CollectionConfig.vue`
  Responsibility: main collection config management page; will gain daily/weekly/monthly tabs, grouped shop-account selector, auto-apply capability behavior, and coverage warning panels.
- `frontend/src/api/collection.js`
  Responsibility: frontend collection config API wrapper; will gain coverage query and any grouped account query helpers required by the new UI.
- `frontend/src/constants/collection.js`
  Responsibility: collection domain/time-selection helpers; will gain normalized granularity mapping helpers and subtype auto-select helpers used by the config page.
- `backend/routers/collection_config.py`
  Responsibility: collection config CRUD and collection account list APIs; will gain shop-account grouping payloads and per-granularity coverage endpoint(s).
- `backend/schemas/collection.py`
  Responsibility: request/response contracts for collection config/account payloads; will gain grouped account and coverage response shapes.
- `backend/services/collection_contracts.py`
  Responsibility: contract normalization helpers; will gain explicit date-preset to granularity mapping and reusable coverage/granularity derivation helpers if absent.

### Existing tests to modify

- `backend/tests/test_collection_time_selection_contract.py`
  Responsibility: verify time-selection and granularity mapping.
- `backend/tests/test_collection_scheduler_capability_filter.py`
  Responsibility: verify config/task behavior remains consistent with account capability constraints.
- `backend/tests/test_collection_frontend_contracts.py`
  Responsibility: verify frontend/runtime-facing collection config contracts referenced in repo docs or static assets.

### New tests to create

- `backend/tests/test_collection_config_coverage_api.py`
  Responsibility: verify per-shop per-granularity coverage aggregation and missing coverage reporting.
- `frontend/scripts/collectionConfigGranularityUi.test.mjs`
  Responsibility: verify `CollectionConfig.vue` exposes daily/weekly/monthly organization, auto-applies capabilities, and shows missing coverage counts.

---

### Task 1: Lock Granularity Mapping Semantics

**Files:**
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_time_selection_contract.py`

- [ ] **Step 1: Write failing tests for the agreed granularity mapping**

Cover these cases:
- `today`, `yesterday`, and daily custom mode map to `daily`
- `last_7_days` and weekly custom mode map to `weekly`
- `last_30_days` and monthly custom mode map to `monthly`
- custom ranges require an explicit granularity value

- [ ] **Step 2: Run the granularity contract tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py -q
```

Expected: FAIL until the new mapping rules are fully encoded.

- [ ] **Step 3: Implement the minimal backend mapping changes**

Add or adjust helpers so all config create/update/read paths derive granularity from the agreed rules without ambiguous fallback.

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_contracts.py backend/schemas/collection.py backend/tests/test_collection_time_selection_contract.py
git commit -m "feat: formalize collection config granularity mapping"
```

### Task 2: Add Shop Account Grouping And Coverage Contracts

**Files:**
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Test: `backend/tests/test_collection_config_coverage_api.py`

- [ ] **Step 1: Write the failing backend API tests**

Cover:
- grouped account payloads expose platform, main account, region, shop account, and capabilities
- coverage API reports `daily_covered`, `weekly_covered`, `monthly_covered`
- missing coverage is computed independently per granularity
- any enabled config counts as covered, including headed configs

- [ ] **Step 2: Run the new coverage API test and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
```

Expected: FAIL because the coverage endpoint/response does not exist yet.

- [ ] **Step 3: Implement grouped account and coverage responses**

Add:
- schema models for grouped shop-account selection data
- schema models for per-shop coverage status
- backend route(s) in `collection_config.py` that aggregate coverage using shop account IDs and config granularity

- [ ] **Step 4: Re-run the focused backend test**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/collection.py backend/routers/collection_config.py backend/tests/test_collection_config_coverage_api.py
git commit -m "feat: add collection config coverage and grouped shop account APIs"
```

### Task 3: Auto-Apply Shop Account Capabilities In The Config UI

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/constants/collection.js`
- Modify: `frontend/src/api/collection.js`
- Test: `frontend/scripts/collectionConfigGranularityUi.test.mjs`

- [ ] **Step 1: Write the failing UI behavior test**

Cover:
- selecting shop accounts auto-selects the stored allowed data domains
- any selected domain with subtypes auto-selects all subtype options
- the user can still deselect domains/subtypes afterward
- the auto-apply logic uses shop account data, not main account data

- [ ] **Step 2: Run the UI behavior test and verify failure**

Run:

```bash
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: FAIL until `CollectionConfig.vue` applies capabilities automatically.

- [ ] **Step 3: Implement the minimal UI changes**

Add:
- capability-driven auto-fill when shop account selection changes
- subtype auto-select helper use
- a safe “manual override after auto-apply” interaction model

- [ ] **Step 4: Re-run the UI behavior test**

Run:

```bash
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/constants/collection.js frontend/src/api/collection.js frontend/scripts/collectionConfigGranularityUi.test.mjs
git commit -m "feat: auto-apply shop account capabilities in collection config"
```

### Task 4: Split The Config Page Into Daily Weekly Monthly Views

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `frontend/scripts/collectionConfigGranularityUi.test.mjs`

- [ ] **Step 1: Extend the failing UI test with granularity view expectations**

Cover:
- page renders separate daily/weekly/monthly views or tabs
- each view filters configs by normalized granularity
- “today/yesterday” configs land in the daily view, `last_7_days` in weekly, `last_30_days` in monthly

- [ ] **Step 2: Run the UI test and verify failure**

Run:

```bash
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: FAIL until the page is organized by granularity.

- [ ] **Step 3: Implement the granularity-organized page structure**

Add:
- daily/weekly/monthly tabs or segmented views
- current-view filtering for config rows
- granularity-specific create flow defaults

- [ ] **Step 4: Re-run the UI test**

Run:

```bash
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js frontend/scripts/collectionConfigGranularityUi.test.mjs
git commit -m "feat: organize collection configs by daily weekly monthly views"
```

### Task 5: Add Coverage Warning Panels And Missing-Shop Guidance

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `frontend/scripts/collectionConfigGranularityUi.test.mjs`
- Test: `backend/tests/test_collection_config_coverage_api.py`

- [ ] **Step 1: Extend backend and UI tests for warning behavior**

Cover:
- current granularity view shows missing-shop counts for that granularity only
- shops missing any one of daily/weekly/monthly are marked partially covered
- warning panel links or exposes a filterable list of missing shops

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: FAIL until warning panels consume the coverage API.

- [ ] **Step 3: Implement warning and missing-shop UI**

Add:
- per-granularity warning summary
- missing-shop quick filter or drawer/table
- partial-coverage badges for shops lacking some other granularity

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js backend/tests/test_collection_config_coverage_api.py frontend/scripts/collectionConfigGranularityUi.test.mjs
git commit -m "feat: add collection config coverage warnings by granularity"
```

### Task 6: Add Main Account And Region Grouped Shop Selection

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_config_coverage_api.py`
- Test: `frontend/scripts/collectionConfigGranularityUi.test.mjs`

- [ ] **Step 1: Add failing tests for grouped selection data**

Cover:
- grouped account payload includes main account grouping
- grouped account payload includes region grouping
- UI can render the grouped selector without flattening into an unusable long list

- [ ] **Step 2: Run backend and UI tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: FAIL until grouped selector support is present.

- [ ] **Step 3: Implement grouped selector support**

Add:
- grouped account response shape in backend
- grouped rendering and filters in `CollectionConfig.vue`
- preservation of existing multi-select/manual workflows

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_config_coverage_api.py -q
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue backend/routers/collection_config.py backend/schemas/collection.py backend/tests/test_collection_config_coverage_api.py frontend/scripts/collectionConfigGranularityUi.test.mjs
git commit -m "feat: group collection shop selectors by main account and region"
```

### Task 7: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run backend coverage and contract tests**

Run:

```bash
pytest backend/tests/test_collection_time_selection_contract.py backend/tests/test_collection_config_coverage_api.py backend/tests/test_collection_scheduler_capability_filter.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend collection config verification**

Run:

```bash
node frontend/scripts/collectionConfigGranularityUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Run focused syntax validation**

Run:

```bash
python -m py_compile backend/routers/collection_config.py backend/schemas/collection.py backend/services/collection_contracts.py
```

Expected: no output, exit code 0

- [ ] **Step 4: Do a manual smoke check**

Check in the browser:
- Daily tab shows configs mapped from today/yesterday/daily custom
- Weekly tab shows configs mapped from last_7_days/weekly custom
- Monthly tab shows configs mapped from last_30_days/monthly custom
- selecting a shop account auto-selects allowed domains and all subtypes
- missing coverage warnings appear for uncovered shops

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: upgrade collection config management by granularity and coverage"
```

