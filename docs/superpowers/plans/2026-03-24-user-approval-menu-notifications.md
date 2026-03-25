# User Approval And Notification Navigation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix user approval success flow, expose the pending-approval page in the frontend menu, and make notification entry points navigate to valid pages.

**Architecture:** Keep the existing permission model and route structure. Fix the approval bug at the API/UI contract boundary, then wire the existing route into the system-management menu, and finally unify notification navigation around the existing system notifications page plus approval-specific deep links.

**Tech Stack:** Vue 3, Element Plus, FastAPI, Async SQLAlchemy, pytest, vue-tsc

---

### Task 1: Approval Flow Root Cause And Regression Coverage

**Files:**
- Modify: `backend/tests/test_users_admin_routes.py`
- Modify: `frontend/src/views/admin/UserApproval.vue`

- [ ] Add or update a failing regression test that proves the approval API response shape expected by the frontend.
- [ ] Run the targeted test to verify the failure reproduces.
- [ ] Adjust the frontend approval success path to consume the actual API payload correctly.
- [ ] Re-run the targeted test or equivalent verification to confirm the failure is gone.

### Task 2: Menu Placement For User Approval

**Files:**
- Modify: `frontend/src/config/menuGroups.js`

- [ ] Add `/admin/users/pending` to the `system` menu group.
- [ ] Place it immediately before `/user-management`.
- [ ] Run frontend type-check to ensure the menu config remains valid.

### Task 3: Notification Navigation Unification

**Files:**
- Modify: `frontend/src/components/common/NotificationBell.vue`
- Modify: `frontend/src/router/index.js` (only if route metadata needs alignment)

- [ ] Add or update a regression test or deterministic check for notification target routing logic if lightweight coverage is feasible.
- [ ] Change `View all notifications` to navigate to `/system-notifications`.
- [ ] Change default notification click routing away from `/messages/notifications`.
- [ ] Route user-registration approval notifications to `/admin/users/pending`; send all other notification clicks to `/system-notifications`.
- [ ] Run frontend type-check to verify the component still compiles.

### Task 4: Verification

**Files:**
- Verify only

- [ ] Run the targeted backend tests for users admin behavior.
- [ ] Run any targeted frontend verification available.
- [ ] Run `npm -C frontend run type-check`.
- [ ] Confirm no regressions in recently changed component-version and notification flows.
