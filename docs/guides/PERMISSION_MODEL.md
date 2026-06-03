# Permission Model

This document is the current maintenance reference for the repository permission model.

It describes the active sources of truth for:

- frontend page access
- frontend action-level access
- backend permission catalog
- backend system role seeds
- legacy compatibility boundaries

## Goal

Keep permission decisions consistent across frontend and backend so page visibility, page access, action buttons, and backend auth payloads do not drift into separate models.

## Active Sources Of Truth

### 1. Frontend Page Access

Primary source:

- `frontend/src/router/index.js`

Rules:

- `meta.permission` defines the page permission id
- `meta.roles` defines the allowed roles
- route guard enforces both permission and role checks
- sidebar visibility reuses the same route metadata

Implication:

- if a page is not represented in router metadata, it is not part of the active frontend page permission surface
- page permission changes must start from the router

### 2. Frontend Menu Visibility

Primary source:

- `frontend/src/config/menuGroups.js`

Rules:

- `menuGroups` organizes visible pages into sidebar groups
- it must only reference active route paths
- it must not introduce access policy that conflicts with router metadata

Implication:

- menu path alignment is a correctness requirement, not a cosmetic one
- a menu item pointing to an admin-only alias while shared roles use a different route is a permission bug

### 3. Frontend Role Permission Fallback

Primary source:

- `frontend/src/config/rolePermissions.js`

Purpose:

- role display metadata
- persisted permission fallback when backend explicit permissions are absent
- compatibility for role-based checks outside router page access

Rules:

- non-admin route-backed permissions must stay aligned with router access
- `ROLE_CONFIG` is not allowed to become a second independent page-access model
- page permissions that no longer map to accessible routes must be removed

### 4. Frontend Action Permissions

Primary source:

- `frontend/src/utils/actionPermissions.js`

Current scoped action domains:

- `campaign:*`
- `performance:*`
- `field-mapping`

Rules:

- action permissions are evaluated separately from route access
- active role is checked first
- admin still bypasses scoped restrictions
- unknown action permissions fall back to `ROLE_CONFIG`

Current consumers:

- `frontend/src/domains/business/views/sales/CampaignManagement.vue`
- `frontend/src/domains/business/views/hr/PerformanceManagement.vue`
- `frontend/src/domains/business/views/hr/PerformanceDisplay.vue`

## Backend Sources Of Truth

### 5. Permission Catalog

Primary source:

- `backend/services/permission_service.py`

Rules:

- defines the backend-recognized permission catalog
- must include current route-backed page permissions
- may include explicit action permissions still used by the frontend
- must not expose retired frontend page permissions

### 6. System Role Seeds

Primary source:

- `backend/services/system_role_service.py`

Rules:

- default seeded roles must match the current active permission surface
- non-admin system roles must not retain retired frontend page permissions
- investor and tourist permissions must match current product boundaries

### 7. Backend RBAC Payload

Primary source:

- `backend/services/rbac_service.py`

Rules:

- auth payload roles are normalized here
- explicit backend permissions are resolved from stored role permissions
- frontend auth/session code should prefer backend-driven permissions when they exist

## Legacy Compatibility

### 8. Legacy Auth Helpers

Compatibility source:

- `backend/utils/auth.py`

Status:

- legacy compatibility only
- not an active RBAC design source

Rules:

- do not add a standalone role-permission table here
- explicit `user.permissions` must be used first
- fallback permissions must come from `DEFAULT_SYSTEM_ROLES`
- new runtime code should prefer `backend/dependencies/auth.py` and `backend/services/rbac_service.py`

## Current Role Matrix

Current frontend menu-access summary:

- `manager`: workspace, sales analytics, finance, store operations, HR, approvals, messages, system/personal, help, training
- `operator`: workspace, sales analytics, store operations, HR, approvals, messages, system/personal, help, training
- `finance`: workspace, sales analytics, finance, HR, approvals, messages, system/personal, help, training
- `investor`: workspace, my follow-investment income, help
- `tourist`: workspace, help

Detailed route snapshots are protected by test coverage instead of being maintained manually here.

## Change Rules

When adding or changing a permissioned page:

1. Update `frontend/src/router/index.js`
2. Update `frontend/src/config/menuGroups.js` if the page is in the sidebar
3. Update `frontend/src/config/rolePermissions.js` only if fallback permissions need to change
4. Update `backend/services/permission_service.py`
5. Update `backend/services/system_role_service.py` if seeded role defaults change
6. Update action-permission rules if the change is button-level rather than page-level
7. Run the relevant permission regression tests

When adding or changing an action permission:

1. Update `frontend/src/utils/actionPermissions.js`
2. Update the corresponding frontend page to use the shared helper
3. Update `frontend/src/config/rolePermissions.js` if fallback permissions need the action id
4. Update `backend/services/permission_service.py`
5. Update `backend/services/system_role_service.py` if seeded role defaults change
6. Run action-permission and backend permission tests

## Regression Tests

Frontend:

- `frontend/scripts/routeRoleConfigConsistency.test.mjs`
- `frontend/scripts/roleMenuSnapshot.test.mjs`
- `frontend/scripts/menuRouteAlignment.test.mjs`
- `frontend/scripts/actionPermissions.test.mjs`
- `frontend/scripts/actionPermissionIntegration.test.mjs`
- `frontend/scripts/authRoleChecks.test.mjs`
- `frontend/scripts/moduleSunsetUi.test.mjs`

Backend:

- `backend/tests/test_permission_service_contract.py`
- `backend/tests/test_system_role_service.py`
- `backend/tests/test_investor_role_frontend_contract.py`
- `backend/tests/test_legacy_auth_permission_compat.py`

## Anti-Patterns

Do not:

- add page permissions only in `ROLE_CONFIG` without router changes
- add menu items pointing to paths not aligned with shared-access routes
- add backend permission catalog entries for retired pages
- reintroduce standalone legacy role tables
- hardcode per-page role logic when a shared action-permission helper should own it
