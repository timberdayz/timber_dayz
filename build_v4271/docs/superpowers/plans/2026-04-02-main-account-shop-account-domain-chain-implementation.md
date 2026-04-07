# Main Account Shop Account Domain Chain Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the collection account model into `main_accounts + shop_accounts + shop_account_aliases + shop_account_capabilities + platform_shop_discoveries`, switch runtime session reuse to `main_account_id`, and make account management, component testing, and collection execution all operate on shop-account semantics.

**Architecture:** The implementation replaces the current overloaded `core.platform_accounts` model with a split login-owner model (`main_accounts`) and shop-target model (`shop_accounts`). API, frontend, and runtime execution paths are updated in the same cutover so that session ownership is keyed by `main_account_id`, while task ownership, test ownership, alias mapping, and data-domain enablement are keyed by `shop_account_id`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, Vue 3, Element Plus, Pinia, Playwright runtime, pytest

---

## File Structure

### Database and ORM

**Files:**
- Create: `migrations/versions/20260402_000001_main_shop_account_domain_chain.py`
- Modify: `modules/core/db/schema.py`
- Modify: `backend/models/database.py`
- Test: `backend/tests/test_main_shop_account_schema_contract.py`
- Test: `backend/tests/test_main_shop_account_migration_contract.py`

**Responsibilities:**
- Add the new canonical tables and ORM classes.
- Migrate and transform existing `core.platform_accounts` rows into the new structure.
- Remove runtime dependence on the old `PlatformAccount` ORM for collection/account-management codepaths.

### Backend Schemas, Services, and Routers

**Files:**
- Create: `backend/schemas/main_account.py`
- Create: `backend/schemas/shop_account.py`
- Create: `backend/schemas/shop_account_alias.py`
- Create: `backend/schemas/platform_shop_discovery.py`
- Modify: `backend/schemas/component_version.py`
- Modify: `backend/schemas/__init__.py`
- Create: `backend/services/shop_account_loader_service.py`
- Create: `backend/services/platform_shop_discovery_service.py`
- Create: `backend/routers/main_accounts.py`
- Create: `backend/routers/shop_accounts.py`
- Create: `backend/routers/shop_account_aliases.py`
- Create: `backend/routers/platform_shop_discoveries.py`
- Modify: `backend/routers/component_versions.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/main.py`
- Modify or retire: `backend/routers/account_management.py`
- Test: `backend/tests/test_main_accounts_api.py`
- Test: `backend/tests/test_shop_accounts_api.py`
- Test: `backend/tests/test_shop_account_aliases_api.py`
- Test: `backend/tests/test_platform_shop_discoveries_api.py`
- Test: `backend/tests/test_shop_account_loader_service.py`
- Test: `backend/tests/test_component_test_runtime_config_shop_accounts.py`

**Responsibilities:**
- Replace account-management contracts with explicit main-account and shop-account contracts.
- Make component testing accept `shop_account_id`.
- Add alias claim APIs and platform-shop-ID confirmation APIs.
- Make collection config and collection tasks consume shop-account-based loaders and capability checks.

### Frontend API, Store, and Views

**Files:**
- Modify: `frontend/src/api/accounts.js`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/stores/accounts.js`
- Modify: `frontend/src/views/AccountManagement.vue`
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `backend/tests/test_collection_frontend_contracts.py`

**Responsibilities:**
- Rename UI semantics to `主账号ID / 店铺账号ID / 平台店铺ID / 店铺别名 / 店铺数据域能力`.
- Switch account management to the split backend APIs while preserving the current page skeleton.
- Switch component test dialogs from account selection to shop-account selection.

### Runtime and Execution

**Files:**
- Modify: `modules/components/base.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `modules/apps/collection_center/app.py`
- Modify: `modules/apps/collection_center/handlers.py`
- Modify: `modules/platforms/shopee/components/products_export.py`
- Modify: `modules/platforms/tiktok/components/shop_switch.py`
- Test: `tests/test_executor_v2.py`
- Test: `backend/tests/test_collection_executor_reused_session_scope.py`
- Test: `backend/tests/test_component_tester_account_loading.py`
- Test: `backend/tests/test_collection_account_capability_alignment.py`

**Responsibilities:**
- Move session ownership from `account_id` to `main_account_id`.
- Inject `shop_account_id / platform_shop_id / shop_region / store_name` as shop context, not login identity.
- Trigger and persist platform-shop-ID discovery and candidate confirmation flow.

### Downstream Read Paths and Reporting

**Files:**
- Modify: `backend/routers/account_alignment.py`
- Modify: `backend/routers/performance_management.py`
- Modify: `backend/routers/hr_commission.py`
- Modify: the active target-management router backing `/targets/shops`
- Test: `backend/tests/test_account_identity_alignment.py`
- Test: `backend/tests/test_target_management_extended_fields.py`

**Responsibilities:**
- Make “unmatched alias” logic, target-shop sources, and shop-oriented reporting read from the new tables.
- Ensure all read paths that currently join `platform_accounts` are moved to `shop_accounts` + aliases.

## Task 1: Build the New Canonical Schema and Migration

**Files:**
- Create: `migrations/versions/20260402_000001_main_shop_account_domain_chain.py`
- Modify: `modules/core/db/schema.py`
- Modify: `backend/models/database.py`
- Test: `backend/tests/test_main_shop_account_schema_contract.py`
- Test: `backend/tests/test_main_shop_account_migration_contract.py`

- [ ] **Step 1: Write the failing schema contract tests**

```python
def test_core_schema_contains_main_and_shop_account_tables():
    assert "core.main_accounts" in table_names
    assert "core.shop_accounts" in table_names
    assert "core.shop_account_aliases" in table_names
    assert "core.shop_account_capabilities" in table_names
    assert "core.platform_shop_discoveries" in table_names
```

- [ ] **Step 2: Run schema contract tests to verify they fail**

Run: `pytest backend/tests/test_main_shop_account_schema_contract.py -v`
Expected: FAIL because the new tables and ORM classes do not exist yet.

- [ ] **Step 3: Add the new ORM models to the SSOT schema**

```python
class MainAccount(Base):
    __tablename__ = "main_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "main_account_id", name="uq_main_accounts_platform_id"),
        {"schema": "core"},
    )
```

- [ ] **Step 4: Add shop-account, alias, capability, and discovery ORM models**

```python
class ShopAccount(Base):
    __tablename__ = "shop_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "shop_account_id", name="uq_shop_accounts_platform_id"),
        {"schema": "core"},
    )
```

- [ ] **Step 5: Create the Alembic migration**

```python
def upgrade():
    op.create_table("main_accounts", ...)
    op.create_table("shop_accounts", ...)
    op.create_table("shop_account_aliases", ...)
    op.create_table("shop_account_capabilities", ...)
    op.create_table("platform_shop_discoveries", ...)
```

- [ ] **Step 6: Encode data migration rules in the migration**

Run inside migration:
- create one `main_accounts` row per `platform + parent_account` group, falling back to `platform + account_id` when `parent_account` is empty
- create one `shop_accounts` row per old `platform_accounts` row
- migrate old `account_alias` into `shop_account_aliases`
- split old `capabilities` JSON into `shop_account_capabilities`

- [ ] **Step 7: Add a migration contract test for the transformation**

```python
def test_platform_accounts_rows_expand_into_main_and_shop_accounts():
    assert migrated_main_count == 1
    assert migrated_shop_count == 2
    assert alias_rows == 2
```

- [ ] **Step 8: Run the schema and migration tests**

Run: `pytest backend/tests/test_main_shop_account_schema_contract.py backend/tests/test_main_shop_account_migration_contract.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add modules/core/db/schema.py backend/models/database.py migrations/versions/20260402_000001_main_shop_account_domain_chain.py backend/tests/test_main_shop_account_schema_contract.py backend/tests/test_main_shop_account_migration_contract.py
git commit -m "feat: add main and shop account schema"
```

## Task 2: Replace Account Contracts and Loaders

**Files:**
- Create: `backend/schemas/main_account.py`
- Create: `backend/schemas/shop_account.py`
- Create: `backend/schemas/shop_account_alias.py`
- Create: `backend/schemas/platform_shop_discovery.py`
- Modify: `backend/schemas/component_version.py`
- Modify: `backend/schemas/__init__.py`
- Create: `backend/services/shop_account_loader_service.py`
- Test: `backend/tests/test_shop_account_loader_service.py`
- Test: `backend/tests/test_component_test_runtime_config_shop_accounts.py`

- [ ] **Step 1: Write the failing loader test**

```python
async def test_load_shop_account_returns_main_account_and_shop_context(async_session):
    payload = await service.load_shop_account_async("shopee_sg_hongxi_local", async_session)
    assert payload["main_account"]["main_account_id"] == "hongxikeji:main"
    assert payload["shop_context"]["shop_account_id"] == "shopee_sg_hongxi_local"
```

- [ ] **Step 2: Run the loader tests to verify they fail**

Run: `pytest backend/tests/test_shop_account_loader_service.py backend/tests/test_component_test_runtime_config_shop_accounts.py -v`
Expected: FAIL because the new service and request model do not exist yet.

- [ ] **Step 3: Add the new Pydantic contracts**

```python
class ShopAccountResponse(BaseModel):
    shop_account_id: str
    main_account_id: str
    store_name: str
    platform_shop_id: str | None = None
    platform_shop_id_status: str
```

- [ ] **Step 4: Change component test input from `account_id` to `shop_account_id`**

```python
class ComponentTestRequest(BaseModel):
    shop_account_id: str = Field(..., description="店铺账号ID")
```

- [ ] **Step 5: Build a loader that returns split login and shop contexts**

```python
return {
    "main_account": {...},
    "shop_context": {...},
    "capabilities": capabilities_map,
}
```

- [ ] **Step 6: Keep runtime compatibility helpers explicit**

```python
compat_account = {
    "main_account_id": main.main_account_id,
    "username": main.username,
    "login_url": main.login_url,
    "store_name": shop.store_name,
    "shop_region": shop.shop_region,
    "shop_id": shop.platform_shop_id,
}
```

- [ ] **Step 7: Run the new loader/runtime-config tests**

Run: `pytest backend/tests/test_shop_account_loader_service.py backend/tests/test_component_test_runtime_config_shop_accounts.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/schemas/main_account.py backend/schemas/shop_account.py backend/schemas/shop_account_alias.py backend/schemas/platform_shop_discovery.py backend/schemas/component_version.py backend/schemas/__init__.py backend/services/shop_account_loader_service.py backend/tests/test_shop_account_loader_service.py backend/tests/test_component_test_runtime_config_shop_accounts.py
git commit -m "feat: add main and shop account contracts"
```

## Task 3: Replace Account Management with Main/Shop APIs

**Files:**
- Create: `backend/routers/main_accounts.py`
- Create: `backend/routers/shop_accounts.py`
- Modify or retire: `backend/routers/account_management.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_main_accounts_api.py`
- Test: `backend/tests/test_shop_accounts_api.py`

- [ ] **Step 1: Write failing API tests for main-account CRUD**

```python
async def test_create_main_account(async_client):
    response = await async_client.post("/api/main-accounts", json={...})
    assert response.status_code == 200
    assert response.json()["main_account_id"] == "hongxikeji:main"
```

- [ ] **Step 2: Write failing API tests for shop-account CRUD and batch creation**

```python
async def test_batch_create_shop_accounts_under_main_account(async_client):
    response = await async_client.post("/api/shop-accounts/batch", json={...})
    assert response.status_code == 200
    assert len(response.json()) == 2
```

- [ ] **Step 3: Run the API tests to verify they fail**

Run: `pytest backend/tests/test_main_accounts_api.py backend/tests/test_shop_accounts_api.py -v`
Expected: FAIL because the routes are not registered.

- [ ] **Step 4: Implement main-account router**

Support:
- list
- create
- update
- delete

- [ ] **Step 5: Implement shop-account router**

Support:
- list
- create
- batch create under a main account
- update
- delete
- stats payload for account-management landing page

- [ ] **Step 6: Decide old route posture**

Preferred cutover:
- remove `/accounts/*` from active frontend usage
- optionally leave `backend/routers/account_management.py` as a thin 410/redirect shim only if needed for local debugging

- [ ] **Step 7: Register the new routers in `backend/main.py`**

```python
app.include_router(main_accounts.router, prefix="/api")
app.include_router(shop_accounts.router, prefix="/api")
```

- [ ] **Step 8: Run the API tests**

Run: `pytest backend/tests/test_main_accounts_api.py backend/tests/test_shop_accounts_api.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/routers/main_accounts.py backend/routers/shop_accounts.py backend/routers/account_management.py backend/main.py backend/tests/test_main_accounts_api.py backend/tests/test_shop_accounts_api.py
git commit -m "feat: add main and shop account routes"
```

## Task 4: Add Alias Claim and Platform-Shop Discovery APIs

**Files:**
- Create: `backend/services/platform_shop_discovery_service.py`
- Create: `backend/routers/shop_account_aliases.py`
- Create: `backend/routers/platform_shop_discoveries.py`
- Modify: `backend/routers/account_alignment.py`
- Test: `backend/tests/test_shop_account_aliases_api.py`
- Test: `backend/tests/test_platform_shop_discoveries_api.py`
- Test: `backend/tests/test_account_identity_alignment.py`

- [ ] **Step 1: Write failing alias-claim tests**

```python
async def test_claim_unmatched_alias_binds_to_shop_account(async_client):
    response = await async_client.post("/api/shop-account-aliases/claim", json={...})
    assert response.status_code == 200
    assert response.json()["shop_account_id"] == "shopee_sg_hongxi_local"
```

- [ ] **Step 2: Write failing platform discovery confirmation tests**

```python
async def test_confirm_platform_shop_discovery_updates_shop_account(async_client):
    response = await async_client.post("/api/platform-shop-discoveries/1/confirm", json={...})
    assert response.status_code == 200
```

- [ ] **Step 3: Run the failing tests**

Run: `pytest backend/tests/test_shop_account_aliases_api.py backend/tests/test_platform_shop_discoveries_api.py backend/tests/test_account_identity_alignment.py -v`
Expected: FAIL

- [ ] **Step 4: Implement alias read/write and claim routes**

Support:
- list aliases
- create alias
- update primary/active flags
- delete alias
- list unmatched aliases
- claim unmatched alias to `shop_account_id`

- [ ] **Step 5: Convert unmatched-alias logic from old `account_alias` lookup to alias-table lookup**

Use:

```sql
JOIN core.shop_account_aliases saa
  ON lower(saa.alias_normalized) = lower(:normalized_alias)
```

- [ ] **Step 6: Implement discovery-service write model**

Service responsibilities:
- record candidate discoveries
- auto-bind single-candidate findings
- expose pending confirmations

- [ ] **Step 7: Implement discovery confirm/reject routes**

On confirm:
- update `shop_accounts.platform_shop_id`
- set status to `manual_confirmed`

- [ ] **Step 8: Run the alias/discovery tests**

Run: `pytest backend/tests/test_shop_account_aliases_api.py backend/tests/test_platform_shop_discoveries_api.py backend/tests/test_account_identity_alignment.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/services/platform_shop_discovery_service.py backend/routers/shop_account_aliases.py backend/routers/platform_shop_discoveries.py backend/routers/account_alignment.py backend/tests/test_shop_account_aliases_api.py backend/tests/test_platform_shop_discoveries_api.py backend/tests/test_account_identity_alignment.py
git commit -m "feat: add shop alias and discovery workflows"
```

## Task 5: Refactor Account Management Frontend to the New Semantics

**Files:**
- Modify: `frontend/src/api/accounts.js`
- Modify: `frontend/src/stores/accounts.js`
- Modify: `frontend/src/views/AccountManagement.vue`
- Test: `backend/tests/test_collection_frontend_contracts.py`

- [ ] **Step 1: Write failing frontend-contract tests for renamed semantics**

```python
def test_account_management_uses_main_and_shop_account_terms():
    assert "主账号ID" in source
    assert "店铺账号ID" in source
    assert "平台店铺ID" in source
```

- [ ] **Step 2: Run the frontend-contract test to verify it fails**

Run: `pytest backend/tests/test_collection_frontend_contracts.py -k account_management -v`
Expected: FAIL

- [ ] **Step 3: Replace the frontend API module with split endpoints**

Add methods for:
- `listMainAccounts`
- `createMainAccount`
- `listShopAccounts`
- `batchCreateShopAccounts`
- alias APIs
- discovery APIs

- [ ] **Step 4: Refactor the Pinia store around the new response shapes**

State should separate:
- `mainAccounts`
- `shopAccounts`
- `unmatchedShopAliases`
- `pendingPlatformShopDiscoveries`

- [ ] **Step 5: Update the account-management table and dialogs**

Required UI changes:
- show `主账号ID`
- rename `账号ID` -> `店铺账号ID`
- rename `店铺ID` -> `平台店铺ID`
- replace single alias field display with alias summary
- preserve batch add shops UX under a chosen main account

- [ ] **Step 6: Add pending-discovery confirmation and alias-claim UI affordances**

At minimum:
- banner or card for unmatched aliases
- banner or card for pending platform-shop-ID confirmations

- [ ] **Step 7: Run the frontend-contract tests**

Run: `pytest backend/tests/test_collection_frontend_contracts.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/accounts.js frontend/src/stores/accounts.js frontend/src/views/AccountManagement.vue backend/tests/test_collection_frontend_contracts.py
git commit -m "feat: refactor account management frontend semantics"
```

## Task 6: Switch Component Testing to Shop-Account Semantics

**Files:**
- Modify: `backend/routers/component_versions.py`
- Modify: `backend/schemas/component_version.py`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `backend/tests/test_component_test_runtime_config.py`
- Test: `backend/tests/test_component_tester_account_loading.py`
- Test: `backend/tests/test_component_tester_runtime_config.py`

- [ ] **Step 1: Write failing tests for `shop_account_id`-based runtime config**

```python
def test_build_component_test_runtime_config_uses_shop_account_id():
    request = ComponentTestRequest(shop_account_id="shopee_sg_hongxi_local", ...)
    logical_type, runtime = _build_component_test_runtime_config(request, "shopee/products_export")
    assert runtime["shop_account_id"] == "shopee_sg_hongxi_local"
```

- [ ] **Step 2: Run the component-tester tests to verify they fail**

Run: `pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_account_loading.py backend/tests/test_component_tester_runtime_config.py -v`
Expected: FAIL

- [ ] **Step 3: Update the component-test request contract**

```python
class ComponentTestRequest(BaseModel):
    shop_account_id: str
    time_mode: Optional[Literal["preset", "custom"]] = None
```

- [ ] **Step 4: Load main-account and shop-account contexts inside `component_versions.py`**

Use the new loader:

```python
shop_payload = await shop_account_loader.load_shop_account_async(request.shop_account_id, db)
main_account = shop_payload["main_account"]
shop_context = shop_payload["shop_context"]
```

- [ ] **Step 5: Update the frontend dialog**

Required UI changes:
- rename “测试账号” to “测试店铺”
- load shop-account options instead of old accounts
- display main-account ID and platform-shop-ID status as read-only context

- [ ] **Step 6: Keep export-specific controls unchanged except for the target selector**

The time-range and `sub_domain` logic should remain intact after the target switch.

- [ ] **Step 7: Run the component-tester tests**

Run: `pytest backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_account_loading.py backend/tests/test_component_tester_runtime_config.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/routers/component_versions.py backend/schemas/component_version.py frontend/src/api/index.js frontend/src/views/ComponentVersions.vue backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_account_loading.py backend/tests/test_component_tester_runtime_config.py
git commit -m "feat: switch component testing to shop accounts"
```

## Task 7: Move Runtime Session Reuse to Main Accounts

**Files:**
- Modify: `modules/components/base.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `modules/apps/collection_center/app.py`
- Modify: `modules/apps/collection_center/handlers.py`
- Modify: `modules/platforms/shopee/components/products_export.py`
- Modify: `modules/platforms/tiktok/components/shop_switch.py`
- Test: `tests/test_executor_v2.py`
- Test: `backend/tests/test_collection_executor_reused_session_scope.py`
- Test: `backend/tests/test_collection_account_capability_alignment.py`

- [ ] **Step 1: Write failing session-scope tests**

```python
def test_executor_uses_main_account_id_for_session_scope():
    assert session_key == "hongxikeji:main"
```

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run: `pytest tests/test_executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_account_capability_alignment.py -v`
Expected: FAIL

- [ ] **Step 3: Replace runtime normalization helpers**

In `executor_v2.py`, change the session-owner derivation:

```python
session_owner_id = str(main_account["main_account_id"]).strip()
shop_account_id = str(shop_context["shop_account_id"]).strip()
```

- [ ] **Step 4: Make `ExecutionContext` explicitly carry login and shop semantics**

Preferred compatibility-safe shape:

```python
ExecutionContext(
    platform=platform,
    account=login_account_payload,
    config={
        **config,
        "shop_account_id": shop_context["shop_account_id"],
        "shop_id": shop_context["platform_shop_id"],
        "shop_region": shop_context["shop_region"],
        "shop_name": shop_context["store_name"],
    },
)
```

- [ ] **Step 5: Trigger platform-shop-ID discovery after login/shop-switch**

Add a hook in the runtime path that:
- inspects page URL and visible shop labels
- records a discovery event
- auto-binds single-candidate matches

- [ ] **Step 6: Update components that currently infer shop context from overloaded account payloads**

At minimum:
- `ShopeeProductsExport`
- `TiktokShopSwitch`

- [ ] **Step 7: Run runtime tests**

Run: `pytest tests/test_executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_account_capability_alignment.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add modules/components/base.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/app.py modules/apps/collection_center/handlers.py modules/platforms/shopee/components/products_export.py modules/platforms/tiktok/components/shop_switch.py tests/test_executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_account_capability_alignment.py
git commit -m "feat: scope runtime sessions to main accounts"
```

## Task 8: Update Downstream Read Paths and Final Regression Checks

**Files:**
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/performance_management.py`
- Modify: `backend/routers/hr_commission.py`
- Modify: `backend/routers/account_alignment.py`
- Modify: the active router backing `/targets/shops`
- Test: `backend/tests/test_target_management_extended_fields.py`
- Test: `backend/tests/test_collection_config_api.py`
- Test: `backend/tests/test_collection_account_capability_alignment.py`
- Test: `backend/tests/test_component_versions_test_history.py`

- [ ] **Step 1: Write failing tests for `/targets/shops` and shop-oriented read paths**

```python
def test_targets_shops_reads_from_shop_accounts():
    assert response_items[0]["shop_account_id"] == "shopee_sg_hongxi_local"
```

- [ ] **Step 2: Run the read-path tests to verify they fail**

Run: `pytest backend/tests/test_target_management_extended_fields.py backend/tests/test_collection_config_api.py backend/tests/test_component_versions_test_history.py -v`
Expected: FAIL or expose stale `platform_accounts` dependencies.

- [ ] **Step 3: Replace remaining `PlatformAccount` joins in active read paths**

Important conversions:
- target-shop lists
- commission/config shop lists
- account-alignment unmatched-alias read paths
- collection config selectable shops

- [ ] **Step 4: Ensure test history and task history serialize `shop_account_id` cleanly**

Preserve historical readability by also including:
- `main_account_id`
- `platform_shop_id` when available

- [ ] **Step 5: Run the focused regression suite**

Run:
```bash
pytest backend/tests/test_main_shop_account_schema_contract.py backend/tests/test_main_shop_account_migration_contract.py backend/tests/test_main_accounts_api.py backend/tests/test_shop_accounts_api.py backend/tests/test_shop_account_aliases_api.py backend/tests/test_platform_shop_discoveries_api.py backend/tests/test_shop_account_loader_service.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_account_loading.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_account_capability_alignment.py backend/tests/test_collection_config_api.py backend/tests/test_component_versions_test_history.py backend/tests/test_target_management_extended_fields.py tests/test_executor_v2.py -v
```
Expected: PASS

- [ ] **Step 6: Run repo-level verification commands**

Run:
```bash
python scripts/verify_architecture_ssot.py
python scripts/verify_api_contract_consistency.py
pytest backend/tests/test_database_schema_verification.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routers/collection_config.py backend/routers/performance_management.py backend/routers/hr_commission.py backend/routers/account_alignment.py backend/tests/test_target_management_extended_fields.py backend/tests/test_collection_config_api.py backend/tests/test_component_versions_test_history.py
git commit -m "feat: complete main and shop account cutover"
```

## Implementation Notes

- Prefer direct physical rename/cutover over dual-write compatibility.
- Do not keep active runtime reads on `core.platform_accounts` once the new schema lands.
- Keep `shop_id` semantics in data warehouse tables unchanged; this plan only renames the account-management/runtime meaning to `platform_shop_id`.
- Preserve Windows-safe logging and avoid emoji in any new runtime log output.
- Keep ORM SSOT in `modules/core/db/schema.py`; do not introduce a second SQLAlchemy base.

## Verification Checklist

- [ ] Main-account CRUD works.
- [ ] Shop-account CRUD and batch create work.
- [ ] Alias claim flow replaces old single-field alias usage.
- [ ] Component testing accepts `shop_account_id`.
- [ ] Session reuse is keyed by `main_account_id`.
- [ ] Platform-shop-ID discovery auto-binds single candidates and records pending confirmations for multiple candidates.
- [ ] Target/commission/reporting read paths no longer depend on `platform_accounts`.
- [ ] Focused regression suite passes.
- [ ] Architecture and API verification scripts pass.
