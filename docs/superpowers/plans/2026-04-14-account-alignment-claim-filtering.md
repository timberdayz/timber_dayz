# Account Alignment Claim Filtering Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent already-claimed shop accounts from appearing in account-alignment claim dropdowns, and ensure clearing a primary alias returns the shop/account pair to the pending-claim flow.

**Architecture:** The frontend computes claimable shop-account options from loaded active primary aliases and hides occupied accounts in both quick-claim and batch-claim dialogs. The backend adds a guard in the claim API so direct callers cannot bind a new alias onto a shop account that already has a different active primary alias.

**Tech Stack:** Vue 3, Element Plus, FastAPI, SQLAlchemy async, pytest

---

### Task 1: Lock The Behavior With Tests

**Files:**
- Modify: `backend/tests/test_shop_account_aliases_api.py`
- Modify: `backend/tests/test_account_alignment_frontend_contract.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_claim_alias_rejects_shop_account_with_different_active_primary_alias(...):
    ...
    assert response.status_code == 409
```

```python
def test_account_alignment_view_filters_claim_dropdown_by_active_primary_alias():
    ...
    assert "occupiedPrimaryShopAccountIds" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_shop_account_aliases_api.py backend/tests/test_account_alignment_frontend_contract.py -q`
Expected: FAIL because the API currently allows reassignment and the view does not yet compute occupied primary-alias accounts.

### Task 2: Implement Minimal Frontend And Backend Changes

**Files:**
- Modify: `backend/routers/shop_account_aliases.py`
- Modify: `frontend/src/views/AccountAlignment.vue`

- [ ] **Step 1: Add minimal backend protection**

```python
primary_alias = (
    await db.execute(
        select(ShopAccountAlias).where(...)
    )
).scalar_one_or_none()
if primary_alias is not None and primary_alias.alias_normalized != alias_normalized:
    raise HTTPException(status_code=409, detail="...")
```

- [ ] **Step 2: Add frontend occupied-account filtering**

```javascript
const occupiedPrimaryShopAccountIds = computed(() => new Set(...))

function filteredShopAccountOptions(platform) {
  return shopAccounts.value.filter((item) => {
    ...
    return !occupiedPrimaryShopAccountIds.value.has(item.id)
  })
}
```

- [ ] **Step 3: Clarify the clear-primary success message**

```javascript
ElMessage.success('主别名已清除，该店铺账号已重新回到可认领状态')
```

### Task 3: Verify

**Files:**
- Test: `backend/tests/test_shop_account_aliases_api.py`
- Test: `backend/tests/test_account_alignment_frontend_contract.py`

- [ ] **Step 1: Run targeted tests**

Run: `pytest backend/tests/test_shop_account_aliases_api.py backend/tests/test_account_alignment_frontend_contract.py -q`
Expected: PASS

- [ ] **Step 2: Review for regressions**

Run: `git diff -- backend/routers/shop_account_aliases.py frontend/src/views/AccountAlignment.vue backend/tests/test_shop_account_aliases_api.py backend/tests/test_account_alignment_frontend_contract.py`
Expected: only the planned filtering, guard, message, and regression-test changes
