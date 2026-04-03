# Shop Discovery Current Only Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first cold-start shop discovery loop so a main account can log in, navigate to a stable landing page, detect the current active shop, and let account management bind or create a `shop_account` without requiring prior collection.

**Architecture:** The implementation keeps `shop_account` as the only formal target for component testing and collection, but moves login/bootstrap semantics to `main_account`. A new `shop_discovery(current_only)` capability is added behind backend services and account-management APIs; frontend account management becomes the standard discovery entry, while the component test page gets only a lightweight fallback trigger.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Pinia, Element Plus, Playwright runtime, pytest

---

## File Structure

**Backend contracts and API**
- Modify: `backend/schemas/platform_shop_discovery.py`
- Modify: `backend/routers/platform_shop_discoveries.py`
- Modify: `backend/routers/main_accounts.py`
- Modify: `backend/main.py`
- Modify: `backend/src` is not used in this repository and must not be introduced
- Test: `backend/tests/test_platform_shop_discoveries_api.py`
- Test: `backend/tests/test_main_accounts_shop_discovery_api.py`

**Discovery services and runtime**
- Create: `backend/schemas/shop_discovery.py`
- Create: `backend/services/shop_discovery_service.py`
- Modify: `backend/services/platform_shop_discovery_service.py`
- Modify: `backend/services/shop_account_loader_service.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `modules/platforms/miaoshou/adapter.py`
- Modify: `modules/platforms/shopee/adapter.py`
- Modify: `modules/platforms/tiktok/adapter.py`
- Test: `backend/tests/test_shop_discovery_service.py`
- Test: `backend/tests/test_platform_shop_discovery_service_contract.py`
- Test: `backend/tests/test_main_account_login_runtime_contract.py`

**Frontend account management**
- Modify: `frontend/src/api/accounts.js`
- Modify: `frontend/src/stores/accounts.js`
- Modify: `frontend/src/views/AccountManagement.vue`
- Test: `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`

**Component test fallback**
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`

## Task 1: Define Discovery Contracts and Main-Account Discovery APIs

**Files:**
- Create: `backend/schemas/shop_discovery.py`
- Modify: `backend/schemas/platform_shop_discovery.py`
- Modify: `backend/routers/main_accounts.py`
- Modify: `backend/routers/platform_shop_discoveries.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_main_accounts_shop_discovery_api.py`
- Test: `backend/tests/test_platform_shop_discoveries_api.py`

- [ ] **Step 1: Write the failing main-account discovery trigger API test**

```python
async def test_trigger_current_shop_discovery_from_main_account(async_client):
    response = await async_client.post(
        "/api/main-accounts/hongxikeji:main/shop-discovery/current",
        json={"mode": "current_only", "reuse_session": True},
    )
    assert response.status_code == 200
    assert response.json()["main_account_id"] == "hongxikeji:main"
    assert response.json()["mode"] == "current_only"
```

- [ ] **Step 2: Run the trigger API test to verify it fails**

Run: `pytest backend/tests/test_main_accounts_shop_discovery_api.py::test_trigger_current_shop_discovery_from_main_account -v`
Expected: FAIL because the route and response contract do not exist yet.

- [ ] **Step 3: Write the failing discovery confirm/create API tests**

```python
async def test_create_shop_account_from_discovery(async_client):
    response = await async_client.post(
        "/api/platform-shop-discoveries/1/create-shop-account",
        json={"shop_account_id": "shopee_sg_hongxi_local", "store_name": "HongXi SG"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "created_shop_account"
```

- [ ] **Step 4: Run the discovery confirm/create tests to verify they fail**

Run: `pytest backend/tests/test_platform_shop_discoveries_api.py -k "create_shop_account or confirm" -v`
Expected: FAIL because the create endpoint and expanded status contract do not exist yet.

- [ ] **Step 5: Add the new request and response schemas**

```python
class ShopDiscoveryRunRequest(BaseModel):
    mode: Literal["current_only"] = "current_only"
    reuse_session: bool = True
    expected_region: str | None = None
    capture_evidence: bool = True
```

- [ ] **Step 6: Add `POST /main-accounts/{main_account_id}/shop-discovery/current`**

```python
@router.post("/{main_account_id}/shop-discovery/current")
async def run_current_shop_discovery(...):
    ...
```

- [ ] **Step 7: Expand `platform_shop_discoveries` APIs for confirm and create**

```python
@router.post("/{discovery_id}/create-shop-account")
async def create_shop_account_from_discovery(...):
    ...
```

- [ ] **Step 8: Register any new router dependencies in `backend/main.py`**

Run: `pytest backend/tests/test_main_accounts_shop_discovery_api.py backend/tests/test_platform_shop_discoveries_api.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/schemas/shop_discovery.py backend/schemas/platform_shop_discovery.py backend/routers/main_accounts.py backend/routers/platform_shop_discoveries.py backend/main.py backend/tests/test_main_accounts_shop_discovery_api.py backend/tests/test_platform_shop_discoveries_api.py
git commit -m "feat: add main account shop discovery APIs"
```

## Task 2: Implement `shop_discovery(current_only)` Service and Matching Rules

**Files:**
- Create: `backend/services/shop_discovery_service.py`
- Modify: `backend/services/platform_shop_discovery_service.py`
- Modify: `backend/services/shop_account_loader_service.py`
- Test: `backend/tests/test_shop_discovery_service.py`
- Test: `backend/tests/test_platform_shop_discovery_service_contract.py`

- [ ] **Step 1: Write the failing discovery service test for URL-first extraction**

```python
def test_extract_current_shop_context_prefers_url_shop_id():
    result = service.extract_current_shop_context(
        platform="shopee",
        current_url="https://seller.example/path?shop_id=1227491331&region=SG",
        dom_snapshot={"store_name": "HongXi SG"},
    )
    assert result.detected_platform_shop_id == "1227491331"
    assert result.detected_region == "SG"
    assert result.detected_store_name == "HongXi SG"
```

- [ ] **Step 2: Run the discovery service test to verify it fails**

Run: `pytest backend/tests/test_shop_discovery_service.py::test_extract_current_shop_context_prefers_url_shop_id -v`
Expected: FAIL because the service and typed result model do not exist yet.

- [ ] **Step 3: Write the failing discovery matching test**

```python
async def test_record_manual_discovery_marks_pending_confirm_when_multiple_candidates(async_session):
    result = await service.record_manual_discovery(...)
    assert result.match.status == "pending_confirm"
    assert result.match.candidate_count == 2
```

- [ ] **Step 4: Run the matching test to verify it fails**

Run: `pytest backend/tests/test_platform_shop_discovery_service_contract.py -v`
Expected: FAIL because the manual discovery recording path and match contract do not exist yet.

- [ ] **Step 5: Implement `ShopDiscoveryService` with URL and DOM extraction**

```python
class ShopDiscoveryService:
    def extract_current_shop_context(...):
        ...
```

- [ ] **Step 6: Add typed confidence and source fields**

```python
confidence = 0.95 if platform_shop_id and (store_name or region) else ...
```

- [ ] **Step 7: Extend `PlatformShopDiscoveryService` with manual discovery persistence**

```python
async def record_manual_discovery(...):
    ...
```

- [ ] **Step 8: Add `create_shop_account_from_discovery` support**

```python
async def create_shop_account_from_discovery(...):
    ...
```

- [ ] **Step 9: Run the service tests**

Run: `pytest backend/tests/test_shop_discovery_service.py backend/tests/test_platform_shop_discovery_service_contract.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/services/shop_discovery_service.py backend/services/platform_shop_discovery_service.py backend/services/shop_account_loader_service.py backend/tests/test_shop_discovery_service.py backend/tests/test_platform_shop_discovery_service_contract.py
git commit -m "feat: add current-only shop discovery services"
```

## Task 3: Move Runtime Bootstrap to Main-Account Login Semantics

**Files:**
- Modify: `backend/services/shop_account_loader_service.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `modules/platforms/miaoshou/adapter.py`
- Modify: `modules/platforms/shopee/adapter.py`
- Modify: `modules/platforms/tiktok/adapter.py`
- Test: `backend/tests/test_main_account_login_runtime_contract.py`
- Test: `backend/tests/test_component_tester_account_loading.py`

- [ ] **Step 1: Write the failing runtime contract test for main-account login bootstrap**

```python
async def test_runtime_bootstrap_uses_main_account_identity_before_shop_binding():
    payload = await bootstrap_main_account_context("hongxikeji:main", ...)
    assert payload["main_account_id"] == "hongxikeji:main"
    assert payload["shop_account_id"] is None
```

- [ ] **Step 2: Run the runtime bootstrap test to verify it fails**

Run: `pytest backend/tests/test_main_account_login_runtime_contract.py -v`
Expected: FAIL because runtime bootstrap still assumes shop-bound semantics.

- [ ] **Step 3: Write the failing adapter-surface test**

```python
def test_platform_adapters_expose_main_account_login_and_optional_navigation():
    assert hasattr(adapter.login(), "...")
```

- [ ] **Step 4: Run the adapter contract test to verify it fails**

Run: `pytest backend/tests/test_component_tester_account_loading.py -k "main_account_login" -v`
Expected: FAIL because the runtime contract is not explicit yet.

- [ ] **Step 5: Refactor runtime bootstrap helpers around `main_account_id`**

```python
session_owner_id = main_account_id
shop_account_id = None
```

- [ ] **Step 6: Keep shop-bound runtime only after discovery or explicit shop selection**

```python
if resolved_shop_account_id:
    params["shop_account_id"] = resolved_shop_account_id
```

- [ ] **Step 7: Make platform adapters explicit about `login` and `navigation` availability**

```python
def login(self):
    return ...
```

- [ ] **Step 8: Run the runtime tests**

Run: `pytest backend/tests/test_main_account_login_runtime_contract.py backend/tests/test_component_tester_account_loading.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py modules/platforms/miaoshou/adapter.py modules/platforms/shopee/adapter.py modules/platforms/tiktok/adapter.py backend/services/shop_account_loader_service.py backend/tests/test_main_account_login_runtime_contract.py backend/tests/test_component_tester_account_loading.py
git commit -m "refactor: make login bootstrap main-account scoped"
```

## Task 4: Add Account-Management Discovery UX

**Files:**
- Modify: `frontend/src/api/accounts.js`
- Modify: `frontend/src/stores/accounts.js`
- Modify: `frontend/src/views/AccountManagement.vue`
- Test: `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`

- [ ] **Step 1: Write the failing account-management UI test**

```javascript
it('shows discover current shop action for main accounts and renders result state', async () => {
  ...
})
```

- [ ] **Step 2: Run the UI test to verify it fails**

Run: `node frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`
Expected: FAIL because the discovery action and result states are not rendered yet.

- [ ] **Step 3: Add frontend API methods for discovery run and shop-account creation from discovery**

```javascript
async runCurrentShopDiscovery(mainAccountId, data) {
  return await api.post(`/main-accounts/${mainAccountId}/shop-discovery/current`, data)
}
```

- [ ] **Step 4: Add Pinia actions for discovery run, confirm, and create**

```javascript
async runCurrentShopDiscovery(mainAccountId, payload) {
  ...
}
```

- [ ] **Step 5: Add the `探测当前店铺` action to account management**

```vue
<el-button size="small" @click="handleDiscoverCurrentShop(main)">
  探测当前店铺
</el-button>
```

- [ ] **Step 6: Render result branches**

```vue
auto_bound / pending_confirm / no_match / failed
```

- [ ] **Step 7: Run the UI test**

Run: `node frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/accounts.js frontend/src/stores/accounts.js frontend/src/views/AccountManagement.vue frontend/scripts/accountManagementShopDiscoveryUi.test.mjs
git commit -m "feat: add account management shop discovery flow"
```

## Task 5: Add Component-Test Fallback Trigger Without Breaking Shop-Scoped Testing

**Files:**
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`

- [ ] **Step 1: Write the failing component-versions fallback UI test**

```javascript
it('offers current-shop discovery when no shop accounts are available', async () => {
  ...
})
```

- [ ] **Step 2: Run the fallback UI test to verify it fails**

Run: `node frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`
Expected: FAIL because the fallback CTA does not exist yet.

- [ ] **Step 3: Add the empty-state discovery CTA**

```vue
<el-empty description="当前主账号下暂无可选店铺账号">
  <el-button @click="handleDiscoverCurrentShop">先探测当前店铺</el-button>
</el-empty>
```

- [ ] **Step 4: Keep test submission shop-scoped**

```javascript
payload.shop_account_id = testAccountId.value
```

- [ ] **Step 5: Run the fallback UI test**

Run: `node frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ComponentVersions.vue frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs
git commit -m "feat: add component test shop discovery fallback"
```

## Task 6: End-to-End Verification and Documentation Alignment

**Files:**
- Modify: `docs/guides/account_health_system.md`
- Modify: `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
- Test: `backend/tests/test_main_accounts_shop_discovery_api.py`
- Test: `backend/tests/test_shop_discovery_service.py`
- Test: `frontend/scripts/accountManagementShopDiscoveryUi.test.mjs`
- Test: `frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`

- [ ] **Step 1: Re-read the approved spec and implementation plan**

Run: `Get-Content docs/superpowers/specs/2026-04-03-shop-discovery-current-only-design.md`
Expected: Confirms the plan still matches the approved design.

- [ ] **Step 2: Update operator-facing docs if terminology changed**

```markdown
- login is main-account scoped
- shop discovery is the cold-start shop-binding entry
```

- [ ] **Step 3: Run backend verification**

Run: `pytest backend/tests/test_main_accounts_shop_discovery_api.py backend/tests/test_platform_shop_discoveries_api.py backend/tests/test_shop_discovery_service.py backend/tests/test_platform_shop_discovery_service_contract.py backend/tests/test_main_account_login_runtime_contract.py -v`
Expected: PASS

- [ ] **Step 4: Run frontend verification**

Run: `node frontend/scripts/accountManagementShopDiscoveryUi.test.mjs && node frontend/scripts/componentVersionsShopDiscoveryFallback.test.mjs`
Expected: PASS

- [ ] **Step 5: Run targeted regression checks around existing shop-account flows**

Run: `pytest backend/tests/test_shop_accounts_api.py backend/tests/test_shop_account_loader_service.py backend/tests/test_component_test_runtime_config_shop_accounts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/guides/account_health_system.md docs/guides/CANONICAL_COLLECTION_COMPONENTS.md
git commit -m "docs: align shop discovery operator guides"
```
