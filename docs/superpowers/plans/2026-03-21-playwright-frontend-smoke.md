# Playwright Frontend Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-owned Playwright smoke script that can open the core frontend routes with injected admin auth, capture browser errors, and emit stable artifacts for manual triage.

**Architecture:** Keep the implementation as a lightweight script-based workflow instead of a full Playwright test suite. Put the executable smoke runner under `frontend/scripts/`, keep reusable route/auth/result helpers in a small module with a Node built-in test, and write artifacts into `output/playwright/frontend-smoke/`.

**Tech Stack:** Node.js, Playwright, Vue 3 frontend localStorage auth, Python auth token helper, npm scripts

---

### Task 1: Define smoke scope and helper boundaries

**Files:**
- Create: `docs/superpowers/plans/2026-03-21-playwright-frontend-smoke.md`
- Create: `frontend/scripts/frontendSmokeShared.mjs`
- Test: `frontend/scripts/frontendSmokeShared.test.mjs`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run the helper test to verify it fails**
- [ ] **Step 3: Implement the shared route/auth/result helpers**
- [ ] **Step 4: Run the helper test to verify it passes**
- [ ] **Step 5: Commit**

### Task 2: Add auth payload generator and smoke runner

**Files:**
- Create: `scripts/generate_frontend_smoke_auth.py`
- Create: `frontend/scripts/playwrightFrontendSmoke.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write the failing helper expectation for auth storage payload shape**
- [ ] **Step 2: Run the helper test to verify it fails**
- [ ] **Step 3: Implement the Python auth generator and Playwright runner**
- [ ] **Step 4: Add npm entrypoint**
- [ ] **Step 5: Run the helper test to verify it passes**
- [ ] **Step 6: Commit**

### Task 3: Verify end-to-end smoke execution

**Files:**
- Create: `output/playwright/frontend-smoke/` (runtime artifacts)

- [ ] **Step 1: Run the smoke script against local frontend/backend**
- [ ] **Step 2: Confirm JSON summary and failure screenshot behavior**
- [ ] **Step 3: Re-run frontend type-check if package metadata changed**
- [ ] **Step 4: Commit**
