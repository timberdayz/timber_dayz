# Login Entry De-Shopification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove shop-bound `main_account.login_url` behavior from formal collection so runtime login entry is platform-generated, homepage success is judged by platform-shell signals, and shop context is always handled after login.

**Architecture:** Add platform login-entry generators and route formal collection through them, then normalize main-account writes and clean existing DB rows so shop-specific login URLs stop re-entering the system. Keep login success focused on reaching homepage or platform shell, and keep target-shop correctness as a separate post-login concern.

**Tech Stack:** FastAPI, SQLAlchemy async, Playwright async runtime, existing platform login components, Vue 3 account-management UI

---

## File Structure

### New files to create

- `backend/services/platform_login_entry_service.py`
  Responsibility: generate canonical platform-neutral login entries for formal collection.
- `backend/tests/test_platform_login_entry_service.py`
  Responsibility: verify each platform returns a shop-neutral login entry and rejects shop-bound query state.

### Existing files to modify

- `modules/apps/collection_center/executor_v2.py`
  Responsibility: stop using DB-stored `main_account.login_url` in formal collection runtime and instead inject platform-generated login entry.
- `modules/platforms/shopee/components/login.py`
  Responsibility: keep login success focused on reaching authenticated homepage/platform shell rather than exact shop-specific URLs.
- `modules/platforms/miaoshou/components/login.py`
  Responsibility: consume runtime-provided platform-neutral login entry and keep homepage-success logic shell-based.
- `modules/platforms/tiktok/components/login.py`
  Responsibility: same as above for TikTok.
- `modules/utils/login_status_detector.py`
  Responsibility: keep platform homepage success based on URL pattern + homepage signals rather than precise shop-specific URLs.
- `backend/routers/main_accounts.py`
  Responsibility: normalize or overwrite `login_url` on create/update so shop-bound URLs cannot persist in the test environment.
- `frontend/src/views/AccountManagement.vue`
  Responsibility: remove the implication that login URL is a free-form shop-specific runtime setting; hide it or make it read-only as appropriate.

### Existing tests to extend

- `backend/tests/test_main_accounts_api.py`
  Responsibility: verify main-account create/update no longer persist shop-bound login URLs.
- `backend/tests/test_collection_verification_flow.py`
  Responsibility: ensure login and verification flows continue to work after runtime login entry generation changes.
- `backend/tests/test_shopee_login_component.py`
  Responsibility: lock homepage/platform-shell success behavior after the login-entry change.
- `backend/tests/test_login_status_detector_miaoshou.py`
  Responsibility: ensure Miaoshou homepage detection remains correct under platform-neutral entry flow.
- `backend/tests/test_collection_executor_reused_session_scope.py`
  Responsibility: ensure runtime still uses `main_account_id` scope while no longer depending on stored shop-bound login URLs.

---

## Task 1: Add Platform Login Entry Generator

**Files:**
- Create: `backend/services/platform_login_entry_service.py`
- Test: `backend/tests/test_platform_login_entry_service.py`

- [ ] **Step 1: Write the failing platform entry tests**

Cover:

- Shopee returns a platform-neutral seller login entry with no `shop_id` / `cnsc_shop_id`
- Miaoshou returns a platform-neutral login entry
- TikTok returns a platform-neutral seller-center login entry
- generator rejects unknown platforms with a clear error

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_platform_login_entry_service.py -q
```

Expected: FAIL because the generator service does not exist yet.

- [ ] **Step 3: Implement the minimal login-entry generator**

Add:

- one canonical runtime entry per supported platform
- explicit guarantee that no shop-specific query keys appear in returned URLs

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_platform_login_entry_service.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/platform_login_entry_service.py backend/tests/test_platform_login_entry_service.py
git commit -m "feat: add platform-neutral login entry generator"
```

## Task 2: Switch Formal Collection Runtime Away From DB Login URL

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_collection_executor_reused_session_scope.py`
- Test: `backend/tests/test_collection_verification_flow.py`

- [ ] **Step 1: Write or extend failing runtime tests**

Cover:

- formal collection no longer depends on `account["login_url"]`
- runtime injects a generated platform login entry before executing login
- same-main-account session coordination still works after the switch

- [ ] **Step 2: Run the focused runtime tests and verify failure**

Run:

```bash
pytest backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_verification_flow.py -q
```

Expected: FAIL until runtime is detached from DB-provided login URL.

- [ ] **Step 3: Implement the minimal runtime switch**

Update:

- formal collection path in `executor_v2.py`
- any runtime params construction that still forwards DB-stored `login_url`

Requirement:

- formal collection must always use platform-generated login entry
- shop context must remain post-login

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_verification_flow.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_verification_flow.py
git commit -m "feat: use platform login entries for formal collection runtime"
```

## Task 3: Lock Homepage Success Semantics

**Files:**
- Modify: `modules/platforms/shopee/components/login.py`
- Modify: `modules/platforms/miaoshou/components/login.py`
- Modify: `modules/platforms/tiktok/components/login.py`
- Modify: `modules/utils/login_status_detector.py`
- Test: `backend/tests/test_shopee_login_component.py`
- Test: `backend/tests/test_login_status_detector_miaoshou.py`

- [ ] **Step 1: Write or extend failing tests for homepage success**

Cover:

- login success remains defined as reaching homepage/platform shell
- URL matching is fuzzy enough to tolerate platform shell variants
- homepage DOM signals remain the primary success confirmation
- target-shop correctness is not treated as login success itself

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_shopee_login_component.py backend/tests/test_login_status_detector_miaoshou.py -q
```

Expected: FAIL until login success semantics are fully aligned with the new model.

- [ ] **Step 3: Implement the minimal login-success cleanup**

Keep:

- homepage URL fuzzy matching
- homepage feature-signal checks

Remove:

- exact shop-bound login success dependence
- shop-specific URL assumptions in login success

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_shopee_login_component.py backend/tests/test_login_status_detector_miaoshou.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/platforms/shopee/components/login.py modules/platforms/miaoshou/components/login.py modules/platforms/tiktok/components/login.py modules/utils/login_status_detector.py backend/tests/test_shopee_login_component.py backend/tests/test_login_status_detector_miaoshou.py
git commit -m "fix: align homepage-based login success semantics"
```

## Task 4: Normalize Main-Account Writes

**Files:**
- Modify: `backend/routers/main_accounts.py`
- Test: `backend/tests/test_main_accounts_api.py`

- [ ] **Step 1: Write the failing API tests**

Cover:

- create main account with a shop-bound login URL -> persisted value becomes platform-neutral
- update main account with a shop-bound login URL -> persisted value becomes platform-neutral
- platform-neutral URL remains stable after normalization

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest backend/tests/test_main_accounts_api.py -q
```

Expected: FAIL until normalization/overwrite logic is added.

- [ ] **Step 3: Implement the minimal write normalization**

Requirement:

- in the current test environment, runtime-facing login URLs must be platform-standard after write
- no shop-bound login URL may persist

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest backend/tests/test_main_accounts_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/main_accounts.py backend/tests/test_main_accounts_api.py
git commit -m "feat: normalize main account login urls on write"
```

## Task 5: Clean Existing Database Rows

**Files:**
- Create or modify: appropriate repo-local migration or cleanup script
- Verify: current DB rows in `core.main_accounts`

- [ ] **Step 1: Add a failing test or verification script for current-row normalization**

If this repo already prefers script-based data maintenance for local/test env, use a script plus verification command instead of migration-only testing.

- [ ] **Step 2: Run verification and confirm existing rows still contain shop-bound URLs**

Run a direct DB inspection command to identify rows containing:

- `shop_id`
- `cnsc_shop_id`
- store-specific redirect targets

- [ ] **Step 3: Implement the cleanup**

Normalize all current `main_account.login_url` rows to platform-neutral values.

- [ ] **Step 4: Re-run verification**

Confirm no remaining `main_account.login_url` rows contain shop-bound query parameters.

- [ ] **Step 5: Commit**

```bash
git add <cleanup-script-or-migration>
git commit -m "chore: clean stored main account login urls"
```

## Task 6: Simplify Admin UI Treatment Of Login URL

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`
- Test: `backend/tests/test_collection_frontend_contracts.py`

- [ ] **Step 1: Write or extend failing UI contract assertions**

Cover:

- login URL is no longer presented as a free-form shop-bound runtime field
- if shown, it is read-only or clearly platform-standard

- [ ] **Step 2: Run the focused contract check and verify failure**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
```

Expected: FAIL until the UI treatment is aligned.

- [ ] **Step 3: Implement the minimal UI cleanup**

Choose one:

- hide the field
- or show it as a platform-standard read-only field

Do not leave a misleading editable `https://...` input that suggests pasting shop URLs.

- [ ] **Step 4: Re-run the focused contract check**

Run:

```bash
pytest backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/AccountManagement.vue backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: simplify main account login url ui"
```

## Task 7: Full Verification And Manual Walkthrough

**Files:**
- Verify: `backend/services/platform_login_entry_service.py`
- Verify: `modules/apps/collection_center/executor_v2.py`
- Verify: `modules/platforms/*/components/login.py`
- Verify: `backend/routers/main_accounts.py`
- Verify: `frontend/src/views/AccountManagement.vue`

- [ ] **Step 1: Run backend verification**

Run:

```bash
pytest backend/tests/test_platform_login_entry_service.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_verification_flow.py backend/tests/test_shopee_login_component.py backend/tests/test_login_status_detector_miaoshou.py backend/tests/test_main_accounts_api.py backend/tests/test_collection_frontend_contracts.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend static verification**

Run:

```bash
npm run build
npm run type-check
```

Expected: PASS

- [ ] **Step 3: Run compile verification**

Run:

```bash
python -m py_compile backend/services/platform_login_entry_service.py backend/routers/main_accounts.py modules/apps/collection_center/executor_v2.py modules/platforms/shopee/components/login.py modules/platforms/miaoshou/components/login.py modules/platforms/tiktok/components/login.py modules/utils/login_status_detector.py
```

Expected: PASS

- [ ] **Step 4: Manual walkthrough**

Validate:

- same-main-account multi-shop Shopee collection still reaches homepage and then target shop
- Miaoshou login still reaches homepage correctly
- TikTok login still reaches homepage correctly
- main-account management no longer encourages shop-bound login URLs

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: de-shopify runtime login entry handling"
```

## Implementation Notes

- Keep homepage success semantics explicit: URL fuzzy match plus homepage feature signals.
- Do not collapse login success and target-shop correctness into one check.
- Runtime should stay strict and single-source-of-truth in this phase; avoid compatibility branches unless the implementation is blocked without them.
