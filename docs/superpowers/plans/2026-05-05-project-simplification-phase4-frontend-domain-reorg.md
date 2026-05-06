# Project Simplification Phase 4 Frontend Domain Reorg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status
- Status: complete (merged to `main`)

**Goal:** Reorganize the Vue 3 frontend to mirror the backend domain model (`collection`, `data_platform`, `business`, `platform`) while preserving runtime behavior and existing route contracts.

**Architecture:** Introduce `frontend/src/domains/*` as the owning location for domain UI, API clients, stores, and domain-scoped utilities. Keep a compatibility layer via re-export “bridge” modules so existing imports continue to work during the cutover, then progressively repoint call sites to domain-owned paths.

**Tech Stack:** Vue 3, Vue Router, Pinia, Vite, Element Plus, TypeScript (via `vue-tsc`), Node.js

---

## Scope

In scope:
- `frontend/src/views/**`, `frontend/src/router/**`, `frontend/src/stores/**`, `frontend/src/api/**`, `frontend/src/services/**`
- introducing a domain-owned folder structure under `frontend/src/domains/**`
- compatibility re-exports to avoid breaking imports during transition
- targeted smoke/type-check verification and a minimal route presence check

Out of scope:
- redesigning UI/UX, changing business behavior, changing route paths
- backend changes
- replacing Element Plus or changing build tooling

## Phase 4 Exit Criteria

- A domain folder structure exists and owns the primary domain modules.
- The app still builds, type-checks, and runs the existing smoke checks.
- Route table remains compatible (no missing or renamed routes; only internal import paths change).
- Compatibility bridge modules are explicit and documented (so later cleanup is systematic).

## Target Directory Model

Create (or converge towards):
- `frontend/src/domains/collection/**`
- `frontend/src/domains/data_platform/**`
- `frontend/src/domains/business/**`
- `frontend/src/domains/platform/**`
- `frontend/src/domains/shared/**` (only for truly cross-domain UI primitives/utilities)

And introduce bridge modules as needed:
- `frontend/src/views/*` → re-export or thin wrappers that delegate to domain views
- `frontend/src/api/*` → re-export domain APIs (or keep as façade while moving implementations)
- `frontend/src/stores/*` → re-export domain stores (or keep façade while moving implementations)

---

### Task 1: Inventory and mapping (no behavior changes)

**Files:**
- Create: `docs/superpowers/findings/2026-05-05-phase4-frontend-domain-inventory.md` (or update an existing findings note if the repo already has a preferred location)
- Read: `frontend/src/router/**`, `frontend/src/views/**`, `frontend/src/api/**`, `frontend/src/stores/**`, `frontend/src/services/**`

- [ ] **Step 1: List all routes and their owning feature**

Record:
- route path
- route name
- component file
- which backend domain it belongs to

- [ ] **Step 2: Map each `views/` module to a target domain path**

Decide the target file path under `frontend/src/domains/<domain>/views/**`.

- [ ] **Step 3: Map each `api/` and `stores/` module to a target domain path**

Decide which modules are domain-owned vs shared-owned.

- [ ] **Step 4: Commit inventory artifact (optional)**

If you created a note under `docs/`, commit it.

```powershell
git add docs/superpowers/findings/2026-05-05-phase4-frontend-domain-inventory.md
git commit -m "docs: phase 4 frontend domain inventory"
```

---

### Task 2: Introduce domain folder skeleton + compatibility bridges

**Files:**
- Create: `frontend/src/domains/collection/.gitkeep`
- Create: `frontend/src/domains/data_platform/.gitkeep`
- Create: `frontend/src/domains/business/.gitkeep`
- Create: `frontend/src/domains/platform/.gitkeep`
- Create: `frontend/src/domains/shared/.gitkeep`
- Modify/Create: bridge re-export modules in `frontend/src/views/**`, `frontend/src/api/**`, `frontend/src/stores/**` as needed

- [ ] **Step 1: Add empty domain folders**

- [ ] **Step 2: Add bridge module convention**

Pick ONE convention and use it everywhere:
- “bridge = re-export everything” (preferred for low risk)
- or “bridge = import + export default/ named exports explicitly” (preferred if tree-shaking or names are inconsistent)

- [ ] **Step 3: Add a short README to explain the bridge rule**

Create: `frontend/src/domains/README.md`

- [ ] **Step 4: Type-check frontend**

Run:
```powershell
cd frontend
npm run type-check
```
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/domains
git commit -m "refactor(frontend): introduce domain folder skeleton"
```

---

### Task 3: Migrate one domain end-to-end (pilot) — choose `platform` first

**Files:**
- Modify: `frontend/src/router/**` (minimal, if paths change)
- Move/Create: `frontend/src/domains/platform/views/**`
- Move/Create: `frontend/src/domains/platform/api/**`
- Move/Create: `frontend/src/domains/platform/stores/**`
- Modify: bridge modules under `frontend/src/views/**`, `frontend/src/api/**`, `frontend/src/stores/**`

- [ ] **Step 1: Pick the smallest “platform” slice**

Prefer auth/users/notifications related pages first (already has frontend tests and is high-signal).

- [ ] **Step 2: Write a tiny import-only contract test (Node test)**

Create: `frontend/scripts/domainImportSmoke.platform.test.mjs`

Example:
```js
import "../src/domains/platform/README.md";
```

Run:
```powershell
cd frontend
node --test scripts/domainImportSmoke.platform.test.mjs
```
Expected: PASS.

- [ ] **Step 3: Move modules into `domains/platform/**`**

Keep public surface stable by updating bridge modules.

- [ ] **Step 4: Run frontend type-check + build**

Run:
```powershell
cd frontend
npm run type-check
npm run build
```
Expected: PASS.

- [ ] **Step 5: Run existing frontend smoke**

Run:
```powershell
cd frontend
npm run smoke:playwright
```
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src
git add frontend/scripts/domainImportSmoke.platform.test.mjs
git commit -m "refactor(frontend): migrate platform modules under domains"
```

---

### Task 4: Migrate remaining domains incrementally

Repeat Task 3 for:
- `business`
- `data_platform`
- `collection`

For each domain:
- [ ] **Step 1: Add/update a domain import smoke test**
- [ ] **Step 2: Move views/api/stores**
- [ ] **Step 3: Keep bridges stable**
- [ ] **Step 4: `npm run type-check`**
- [ ] **Step 5: `npm run build`**
- [ ] **Step 6: Run at least one existing smoke (`smoke:playwright` or domain-specific smoke if present)**
- [ ] **Step 7: Commit**

---

### Task 5: Phase 4 verification + documentation

**Files:**
- Modify: `docs/superpowers/plans/2026-05-05-project-simplification-phase4-frontend-domain-reorg.md` (mark checkboxes, record decisions)
- Modify (optional): `docs/DEVELOPMENT_RULES/**` if there is a preferred frontend architecture doc location

- [ ] **Step 1: Full frontend verification set**

Run:
```powershell
cd frontend
npm run type-check
npm run build
npm run smoke:playwright
npm run test:smoke-shared
```
Expected: PASS.

- [ ] **Step 2: Record what bridges remain**

List bridge modules that still exist and why.

- [ ] **Step 3: Commit docs (optional)**

```powershell
git add docs
git commit -m "docs: record phase 4 frontend domain cutover notes"
```

---

## Risks and Controls

- Risk: Silent route loss due to component path move
  - Control: keep route definitions stable; rely on type-check + smoke and add a minimal import smoke per domain
- Risk: Circular imports from “shared” misuse
  - Control: enforce “domain owns; shared is last resort” and prefer small bridges
- Risk: Over-scoping into UI redesign
  - Control: no component redesign; only file movement + import rewiring
