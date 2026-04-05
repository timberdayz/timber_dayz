# Frontend Page Permission Unification Design

**Date:** 2026-04-05

**Goal:** Unify frontend page permissions under one repository-wide standard so all user-visible pages follow the same classification rules, inventory and recently added pages stop leaking or over-restricting access, and collection-management pages remain admin-only.

## 1. Background

The current frontend permission model is primarily page-based:

- route access is enforced through `meta.permission` and `meta.roles`
- sidebar visibility reuses the same route metadata
- most pages do not implement fine-grained button-level authorization as the main control boundary

That overall direction matches the product expectation, but the current implementation has drift:

- some pages rely on coarse permissions that mix read and write concerns
- some newer pages are stricter than the agreed business policy
- some legacy routes still use implicit open access
- some route role declarations and role permission mappings are inconsistent
- at least one route path is duplicated with conflicting access metadata

The result is that page access standards are not currently uniform.

## 2. Scope

This phase covers the **entire frontend page permission surface**, with implementation changes focused on:

- route definitions
- sidebar/menu visibility
- role-permission mapping
- mixed read/write page classification

This phase also includes targeted backend verification only for high-risk admin-only write surfaces that are touched by the frontend changes.

This phase does **not** redesign the whole backend RBAC model.

## 3. Core Decision

The repository standard remains **page-level authorization first**.

That means the main unit of permission is the page, not the individual button.

If a page contains management actions, configuration actions, posting actions, create/edit/delete actions, batch actions, or other operational controls, that page is treated as an **operation page** and is not downgraded into a read page simply because it also contains tables or dashboards.

## 4. Page Classification Standard

All frontend pages should be classified into exactly one of these categories.

### 4.1 View Pages

Definition:

- dashboard pages
- read-only list pages
- analytics pages
- detail-display pages
- pages whose user actions are limited to filtering, searching, refreshing, pagination, and opening detail views

Default access baseline:

- `admin`
- `manager`
- `operator`

`finance` is granted access only when the page belongs to the finance domain or is explicitly needed cross-domain.

### 4.2 Operation Pages

Definition:

- pages containing create, edit, delete, save, import, export-initiation, posting, reconciliation submission, configuration, version management, task execution management, alignment, approval-flow configuration, or any other business/system state-changing actions

Default access baseline:

- `admin` only

This rule is global unless a page is explicitly approved as a special exception later.

### 4.3 Personal Pages

Definition:

- pages centered on the current logged-in user’s own data or preferences

Examples:

- my income
- personal settings
- session management
- notification preferences

Access:

- authenticated users according to the page’s business need

These pages should still be explicit in route metadata, not left open by omission.

### 4.4 Help Pages

Definition:

- user guide
- FAQ
- tutorial pages

Access:

- may remain open or login-only, but must be explicitly declared in route metadata

## 5. Domain-Specific Rules

## 5.1 Inventory And Product Domain

The inventory/product area must be split by page intent.

### View pages

These should follow the default view baseline `admin + manager + operator`:

- inventory overview
- inventory dashboard
- inventory health dashboard
- product quality dashboard
- inventory balances
- inventory ledger
- inventory aging
- inventory alerts
- inventory reconciliation (only if the page remains read-only)

### Operation pages

These remain `admin` only:

- inventory adjustments
- GRN posting/management
- opening balances
- any inventory page that can save, post, or otherwise mutate inventory state

### Permission design implication

The current inventory permission model is too coarse because view pages and operation pages reuse the same route-level permission buckets.

This phase should introduce a split such as:

- `inventory:view`
- `inventory:manage`
- `inventory-dashboard:view`

The exact token names may vary, but read and write concerns must be separated.

## 5.2 Collection And Management Domain

The whole collection-management module is admin-only regardless of whether a page is operational or audit-oriented.

That includes:

- collection config
- collection coverage audit
- collection tasks
- collection history
- component recorder
- component versions

Reason:

- this entire domain belongs to collection operations and runtime management, not general staff visibility

## 5.3 System / Account / User / Role / Permission Domain

These are operation/configuration domains and remain `admin` only:

- system config
- database config
- security settings
- account management
- account alignment
- user management
- role management
- permission management
- system logs
- data backup
- system maintenance
- notification config

## 5.4 HR And Performance Domain

Split by page purpose:

- performance display remains a view page
- performance management remains an operation/configuration page
- shop assignment remains an operation page
- personal pages such as my income remain explicit personal pages

## 6. Standard For Mixed Pages

If a page contains both data display and management actions:

- classify the whole page as an operation page
- restrict the page to `admin`
- do not rely on button-level hiding as the primary safety boundary

This matches the confirmed product rule for this project.

## 7. Current Issues To Fix

## 7.1 Duplicate Route Definitions

Any duplicate route path or duplicate route name with conflicting permission metadata must be removed.

This is a correctness issue, not only a style issue.

## 7.2 Implicit Open Access

Pages using `permission: null` and `roles: []` as their effective business access definition should be normalized into explicit policy.

Help pages may remain broadly visible, but business pages should not rely on empty metadata.

## 7.3 Role-Permission Drift

Route `meta.roles` and `ROLE_CONFIG` permission grants must be aligned.

A role listed in a route should actually hold the matching permission unless the route intentionally relies on role-only access.

This phase should prefer consistent dual declaration so route guards and sidebars behave predictably.

## 8. Implementation Strategy

Implementation should proceed in this order:

1. define the normalized page classification and target permission buckets
2. remove duplicate and implicit-access route anomalies
3. split inventory read/write permission tokens
4. update route metadata to the new standard
5. update role permission mapping
6. verify sidebar visibility and route guard behavior
7. add regression tests for page access classification and known anomalies

## 9. Verification Strategy

Verification must cover:

- route guard behavior
- sidebar visibility behavior
- role-permission consistency for critical pages
- inventory read pages accessible to `operator`
- inventory operation pages denied to non-admin users
- collection pages denied to non-admin users
- duplicate route anomalies removed

## 10. Non-Goals

This phase does not include:

- full backend RBAC redesign
- per-button permission architecture rollout across the entire app
- redesigning unrelated page content
- changing business workflows beyond access control

## 11. Expected Outcome

After this phase:

- frontend page permissions follow one explicit standard
- page classification is stable and understandable
- inventory read pages align with the approved business policy
- operation/configuration pages are consistently admin-only
- collection management remains fully admin-only
- route and role-permission inconsistencies are materially reduced
