# Formal Training Management Module Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the temporary training pilot entry with a formal ERP training module that includes both management-side and employee-side entry points.

**Architecture:** Promote the existing pilot service into a formal `training` API surface, then build formal Vue routes for management and employee pages. Keep the initial data source lightweight and read-first, but stabilize the route contracts and UX as a real module.

**Tech Stack:** FastAPI, Vue 3, Element Plus, Vite, existing ERP router/menu/permission system, pytest, node:test

---

### Task 1: Formalize backend training API

**Files:**
- Modify: `backend/services/training_pilot_service.py`
- Modify: `backend/routers/training_pilot.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_training_routes.py`

- [ ] **Step 1: Write failing backend tests for formal training routes**
- [ ] **Step 2: Run backend tests to verify 404 / contract failure**
- [ ] **Step 3: Add formal `/api/training/*` read routes**
- [ ] **Step 4: Re-run backend tests**

### Task 2: Build formal management-side frontend routes

**Files:**
- Create: `frontend/src/views/training/TrainingOverview.vue`
- Create: `frontend/src/views/training/TrainingPrograms.vue`
- Create: `frontend/src/views/training/TrainingAssignments.vue`
- Create: `frontend/src/views/training/TrainingResults.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/config/rolePermissions.js`
- Test: `frontend/scripts/trainingUi.test.mjs`

- [ ] **Step 1: Write failing frontend route assertions**
- [ ] **Step 2: Run frontend tests to verify route/page absence**
- [ ] **Step 3: Add management-side formal routes and pages**
- [ ] **Step 4: Re-run frontend tests**

### Task 3: Build employee-side training entry

**Files:**
- Create: `frontend/src/views/training/MyTraining.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/menuGroups.js`
- Modify: `frontend/src/config/rolePermissions.js`
- Modify: `frontend/src/api/trainingPilot.js` or replace with formal API file
- Test: `frontend/scripts/trainingUi.test.mjs`

- [ ] **Step 1: Extend failing frontend test for employee entry**
- [ ] **Step 2: Run test to confirm failure**
- [ ] **Step 3: Add `/my-training` route and employee page**
- [ ] **Step 4: Re-run tests**

### Task 4: Polish formal module and verify

**Files:**
- Review: formal training backend/frontend files
- Test: backend and frontend formal route tests

- [ ] **Step 1: Remove reliance on pilot-only naming in primary navigation**
- [ ] **Step 2: Run `python -m pytest backend/tests/test_training_routes.py -q`**
- [ ] **Step 3: Run `node --test frontend/scripts/trainingUi.test.mjs`**
- [ ] **Step 4: Summarize remaining follow-up work for task/notification integration**

Plan complete and saved to `docs/superpowers/plans/2026-04-12-formal-training-management-module.md`. Ready to execute?
