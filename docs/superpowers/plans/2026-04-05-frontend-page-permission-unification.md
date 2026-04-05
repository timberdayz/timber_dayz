# Frontend Page Permission Unification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify frontend page permissions under a single page-based standard, open approved read-only business pages to `admin + manager + operator`, keep operation/configuration pages admin-only, and eliminate inconsistent or implicit route access definitions.

**Architecture:** Keep the existing page-level route guard model, but normalize it by separating read vs manage permissions where needed, especially in inventory. Use route metadata plus role-permission mapping as the primary control surface, and remove duplicate or implicit route definitions that make access behavior ambiguous.

**Tech Stack:** Vue 3, Vue Router, Pinia, Element Plus, existing frontend RBAC helpers, targeted backend verification where admin-only write operations are involved

---

## File Structure

### Existing files to modify

- `frontend/src/router/index.js`
  Responsibility: normalize route access metadata, remove duplicate route definitions, and align page categories with the new standard.
- `frontend/src/config/rolePermissions.js`
  Responsibility: define the normalized permission buckets and align per-role grants with the approved page model.
- `frontend/src/components/common/Sidebar.vue`
  Responsibility: continue to reflect route-level access after permission changes.
- `frontend/src/components/common/GroupedSidebar.vue`
  Responsibility: continue to reflect route-level access after permission changes.
- `frontend/src/config/menuGroups.js`
  Responsibility: verify grouped navigation still points to the correct pages after route classification cleanup.
- `frontend/src/views/inventory/InventoryAdjustments.vue`
  Responsibility: confirm operation semantics remain admin-only through page-level access.
- `frontend/src/views/inventory/InventoryGrns.vue`
  Responsibility: confirm operation semantics remain admin-only through page-level access.
- `frontend/src/views/inventory/InventoryOpeningBalances.vue`
  Responsibility: confirm operation semantics remain admin-only through page-level access.
- `frontend/src/views/InventoryOverview.vue`
  Responsibility: confirm the page remains read-only and safe to open to the approved roles.
- `frontend/src/views/InventoryHealthDashboard.vue`
  Responsibility: confirm the page remains read-only and safe to open to the approved roles.
- `frontend/src/views/ProductQualityDashboard.vue`
  Responsibility: confirm the page remains read-only and safe to open to the approved roles.
- `frontend/src/views/InventoryDashboardSimple.vue`
  Responsibility: confirm the page remains read-only and safe to open to the approved roles.

### New files to create

- `frontend/scripts/frontPagePermissionAudit.test.mjs`
  Responsibility: lock route-level access expectations for key page classes and catch duplicate/implicit access regressions.

### Existing tests to extend

- `frontend/scripts/authRoleChecks.test.mjs`
  Responsibility: verify role permission mapping continues to match the route model.

---

## Task 1: Lock The New Permission Model With Failing Tests

**Files:**
- Modify: `frontend/scripts/authRoleChecks.test.mjs`
- Create: `frontend/scripts/frontPagePermissionAudit.test.mjs`

- [ ] **Step 1: Write failing permission-model tests**

Cover:

- inventory view pages are accessible to `admin`, `manager`, `operator`
- inventory operation pages are admin-only
- collection management pages are admin-only
- duplicate route definitions such as `/test` are not allowed
- business pages should not rely on `permission: null` and `roles: []` unless they are explicitly approved help/personal pages

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: FAIL because the current route and role-permission model does not yet match the approved standard.

- [ ] **Step 3: Commit**

```bash
git add frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
git commit -m "test: lock frontend page permission model"
```

## Task 2: Normalize Route Access Definitions

**Files:**
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Remove duplicate and ambiguous route definitions**

Remove:

- duplicate `/test` route definitions
- any conflicting duplicate name/path declarations discovered during implementation

- [ ] **Step 2: Normalize explicit access metadata**

Ensure:

- help pages are explicitly marked as intentionally open or broadly visible
- personal pages are explicitly marked as personal pages
- business pages do not rely on empty `roles` and `permission` metadata by accident

- [ ] **Step 3: Update page classifications**

Apply the approved rules:

- inventory overview / dashboard / health / product quality -> view-page roles
- inventory adjustments / GRNs / opening balances -> admin-only operation pages
- collection pages -> admin-only
- system/account/user/role/permission pages -> admin-only

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: still FAIL until role permission mapping is aligned.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/index.js
git commit -m "refactor: normalize frontend route access metadata"
```

## Task 3: Split Inventory Read vs Manage Permissions

**Files:**
- Modify: `frontend/src/config/rolePermissions.js`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Introduce normalized inventory permission buckets**

Add permission buckets such as:

- `inventory:view`
- `inventory:manage`
- `inventory-dashboard:view`

Keep naming concise and consistent with the existing config style.

- [ ] **Step 2: Map roles to the new buckets**

Grant:

- `admin` -> all inventory read and manage buckets
- `manager` -> approved inventory read buckets only
- `operator` -> approved inventory read buckets only
- `finance` -> inventory access only where explicitly retained

- [ ] **Step 3: Update inventory route metadata**

Assign:

- read-only inventory pages -> read permissions
- mutating inventory pages -> manage permissions

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: PASS for inventory route and permission-model checks.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/config/rolePermissions.js frontend/src/router/index.js
git commit -m "feat: split inventory view and manage permissions"
```

## Task 4: Align Other Route And Role Mismatches

**Files:**
- Modify: `frontend/src/config/rolePermissions.js`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Audit and fix route-role-permission mismatches**

Address mismatches where route `meta.roles` and role permission config disagree for active pages.

Examples already identified:

- `sales-analysis`
- `sales-detail-by-product`
- `invoice-management`
- `b-cost-analysis`

- [ ] **Step 2: Keep the fix scoped**

Do not redesign unrelated business policy. Only align the existing route model to explicit role grants or tighten the route to match actual permission ownership.

- [ ] **Step 3: Re-run focused tests**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/config/rolePermissions.js frontend/src/router/index.js
git commit -m "fix: align frontend route roles with permission grants"
```

## Task 5: Verify Sidebar And Navigation Behavior

**Files:**
- Modify: `frontend/src/components/common/Sidebar.vue`
- Modify: `frontend/src/components/common/GroupedSidebar.vue`
- Modify: `frontend/src/config/menuGroups.js`

- [ ] **Step 1: Verify whether navigation code needs changes**

If current navigation logic already respects normalized route metadata, keep changes minimal.

- [ ] **Step 2: Adjust only where required**

Make changes only if:

- newly explicit help/personal page access breaks menu visibility
- grouped navigation still references removed/renamed routes

- [ ] **Step 3: Re-run focused tests**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/common/Sidebar.vue frontend/src/components/common/GroupedSidebar.vue frontend/src/config/menuGroups.js
git commit -m "fix: keep sidebar access aligned with route permissions"
```

## Task 6: Full Verification

**Files:**
- Verify: `frontend/src/router/index.js`
- Verify: `frontend/src/config/rolePermissions.js`
- Verify: `frontend/src/components/common/Sidebar.vue`
- Verify: `frontend/src/components/common/GroupedSidebar.vue`
- Verify: `frontend/scripts/authRoleChecks.test.mjs`
- Verify: `frontend/scripts/frontPagePermissionAudit.test.mjs`

- [ ] **Step 1: Run route and role permission tests**

Run:

```bash
node --test frontend/scripts/authRoleChecks.test.mjs frontend/scripts/frontPagePermissionAudit.test.mjs
```

Expected: PASS

- [ ] **Step 2: Run frontend build verification**

Run:

```bash
npm run build
npm run type-check
```

Expected: PASS

- [ ] **Step 3: Manually verify critical access paths**

Check:

- operator can access approved inventory view pages
- operator cannot access inventory operation pages
- non-admin users cannot access collection pages
- non-admin users cannot access system/account/user/role/permission pages
- help/personal pages still behave as intended

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: unify frontend page permissions"
```

## Implementation Notes

- Keep the page-level authorization model as the primary boundary.
- Do not broaden this phase into full backend RBAC redesign.
- Do not convert the whole app into button-level permission architecture.
- If a page is mixed read/write, classify it as admin-only rather than inventing a hybrid rule.
- Collection management remains admin-only throughout this phase.
