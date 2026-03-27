# Active Components And Archive Isolation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define a V2 active-component source of truth, prevent legacy components from re-entering the default runtime/test/registration chain, and introduce a safe archive path for old components that should remain reference-only for future agent analysis.

**Architecture:** This work must proceed in order: first identify active V2 components and current runtime pointers, then enforce runtime and registration guards, and only after that move safe legacy files into archive/reference locations. The system should reject or ignore archive-only components in default flows rather than relying on human discipline.

**Tech Stack:** FastAPI, SQLAlchemy async, Vue 3, Python component runtime, ComponentVersion stable/runtime resolution

---

## Scope

This plan covers:

- a repository-level active V2 component manifest
- runtime/stable pointer audit rules
- archive-only file classification and directory strategy
- registration/UI/runtime guards that block archive components from default use

This plan does **not** include:

- migrating additional platforms to V2 logic
- deleting every legacy file immediately
- changing data output paths or data sync pipelines

## File Map

### New files

- `backend/services/active_collection_components.py`
  - SSOT for active V2 component names and archive-eligible legacy classifications.
- `backend/tests/test_active_collection_components.py`
  - Contract tests for active component recognition and archive exclusions.
- `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`
  - Human-readable active V2 component list and archive policy.

### Modified backend/runtime files

- `backend/services/component_runtime_resolver.py`
  - Refuse runtime resolution for non-active or archive-only components once the guard is enabled.
- `backend/services/component_version_service.py`
  - Add guard helpers for active/stable/archive checks where version selection or promotion occurs.
- `backend/routers/component_versions.py`
  - Default list/register/promote flows should prefer active V2 components and reject archive targets.
- `modules/apps/collection_center/component_loader.py`
  - Reject or clearly mark archive paths when loading Python components by file path.

### Modified frontend/docs files

- `frontend/src/views/ComponentVersions.vue`
  - Default UX should communicate active vs archive-only status.
- `frontend/src/views/ComponentRecorder.vue`
  - Recorder should direct users toward active canonical components only.
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
  - Cross-link to active component and archive policy.

### Future archive move targets

This plan should produce rules for later moving files into:

- `modules/platforms/<platform>/archive/`

but should not blindly move files until runtime pointers are proven safe.

---

### Task 1: Define The Active V2 Component Manifest

**Files:**
- Create: `backend/services/active_collection_components.py`
- Create: `backend/tests/test_active_collection_components.py`
- Create: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`

- [ ] **Step 1: Write failing manifest tests**

Cover:
- active V2 components include only the currently approved live set
- archive-only files are not treated as active
- active component names are expressed as logical names, not raw file paths

Example initial active set should cover at least:
- `miaoshou/login`
- `miaoshou/orders_export`
- `shopee/orders_export` only if explicitly approved and verified

Run:

```bash
pytest backend/tests/test_active_collection_components.py -q
```

Expected: FAIL because the active manifest service does not exist yet.

- [ ] **Step 2: Implement the manifest service**

Create a small SSOT with helpers like:

```python
def is_active_component_name(name: str) -> bool: ...
def is_archive_only_file(path_or_name: str) -> bool: ...
def list_active_component_names() -> list[str]: ...
```

- [ ] **Step 3: Re-run manifest tests**

Run:

```bash
pytest backend/tests/test_active_collection_components.py -q
```

Expected: PASS

- [ ] **Step 4: Document the active set and archive policy**

Write `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` with:
- active V2 component list
- archive-only policy
- reminder that archive files are reference-only for humans/agents

- [ ] **Step 5: Commit**

```bash
git add backend/services/active_collection_components.py backend/tests/test_active_collection_components.py docs/guides/ACTIVE_COLLECTION_COMPONENTS.md
git commit -m "refactor: define active collection component manifest"
```

### Task 2: Audit Runtime And Stable Pointer Safety

**Files:**
- Modify: `backend/tests/test_component_runtime_resolver.py`
- Modify: `backend/services/component_runtime_resolver.py`
- Modify: `backend/services/component_version_service.py`

- [ ] **Step 1: Write failing runtime-pointer tests**

Cover:
- runtime resolver rejects archive-only or non-active components
- stable selection still requires exactly one stable active version
- missing file/path errors remain explicit

Run:

```bash
pytest backend/tests/test_component_runtime_resolver.py -q
```

Expected: FAIL until active/archive guards are introduced.

- [ ] **Step 2: Add active/archive guards**

Implement checks so:
- formal runtime only resolves active component names
- archive-only component names or archive file paths are rejected from default runtime
- stable promotion cannot silently target archive-only files

- [ ] **Step 3: Re-run runtime resolver tests**

Run:

```bash
pytest backend/tests/test_component_runtime_resolver.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_component_runtime_resolver.py backend/services/component_runtime_resolver.py backend/services/component_version_service.py
git commit -m "refactor: guard runtime resolution with active component manifest"
```

### Task 3: Guard Registration And Default Management Surfaces

**Files:**
- Modify: `backend/routers/component_versions.py`
- Modify: `frontend/src/views/ComponentVersions.vue`
- Modify: `frontend/scripts/componentVersionsVerificationUi.test.mjs`

- [ ] **Step 1: Write failing registration/UI tests**

Cover:
- batch registration skips archive-only files even if they are still under `components/`
- default versions UI distinguishes active V2 components from archive-only references
- archive-only items cannot be promoted to stable from the default path

Run:

```bash
pytest backend/tests/test_component_versions_canonical_registration.py -q
node frontend/scripts/componentVersionsVerificationUi.test.mjs
```

Expected: at least one failure until guards and UI messaging are updated.

- [ ] **Step 2: Implement backend registration guards**

In `component_versions.py`:
- prefer active manifest over broad canonical scan for default surfaces
- keep archive-only items out of default registration/promote flow

- [ ] **Step 3: Implement UI freeze messaging**

In `ComponentVersions.vue`:
- active components are the default management set
- archive components, if shown at all, are clearly marked reference-only

- [ ] **Step 4: Re-run backend and frontend verification**

Run:

```bash
pytest backend/tests/test_component_versions_canonical_registration.py -q
node frontend/scripts/componentVersionsVerificationUi.test.mjs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/component_versions.py frontend/src/views/ComponentVersions.vue frontend/scripts/componentVersionsVerificationUi.test.mjs
git commit -m "refactor: isolate archive components from default management surfaces"
```

### Task 4: Guard Loader/File-Path Access For Archive Targets

**Files:**
- Modify: `modules/apps/collection_center/component_loader.py`
- Add: `backend/tests/test_component_loader_archive_guard.py`

- [ ] **Step 1: Write failing loader guard tests**

Cover:
- loading a Python component from `modules/platforms/<platform>/archive/` is rejected in default runtime/test paths
- `components/` remains allowed

Run:

```bash
pytest backend/tests/test_component_loader_archive_guard.py -q
```

Expected: FAIL until the loader understands archive boundaries.

- [ ] **Step 2: Implement archive path guard**

Tighten path validation so:
- runtime/test loaders only allow active component locations by default
- archive paths are treated as reference-only and require an explicit non-runtime code path if ever inspected

- [ ] **Step 3: Re-run loader tests**

Run:

```bash
pytest backend/tests/test_component_loader_archive_guard.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add modules/apps/collection_center/component_loader.py backend/tests/test_component_loader_archive_guard.py
git commit -m "refactor: block archive component paths from default loader flow"
```

### Task 5: Prepare The Archive Move Strategy

**Files:**
- Modify: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`
- Modify: `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
- Modify: `docs/guides/COMPONENT_REUSE_WORKFLOW.md`

- [ ] **Step 1: Write the archive move checklist**

Document a required pre-move checklist:
- active manifest says component is not active
- no stable `ComponentVersion.file_path` points to the file
- loader/runtime guards are already in place
- config/helper imports are preserved

- [ ] **Step 2: Add the target archive directory convention**

Document:
- `modules/platforms/<platform>/archive/`
- archive files are read-only/reference-only for agent analysis
- archive files do not participate in default runtime or registration

- [ ] **Step 3: Commit**

```bash
git add docs/guides/ACTIVE_COLLECTION_COMPONENTS.md docs/guides/CANONICAL_COLLECTION_COMPONENTS.md docs/guides/COMPONENT_REUSE_WORKFLOW.md
git commit -m "docs: define archive move policy for legacy collection components"
```

### Task 6: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run the focused backend regression set**

Run:

```bash
pytest backend/tests/test_active_collection_components.py backend/tests/test_component_runtime_resolver.py backend/tests/test_component_versions_canonical_registration.py backend/tests/test_component_loader_archive_guard.py -q
```

Expected: PASS

- [ ] **Step 2: Run frontend verification**

Run:

```bash
node frontend/scripts/componentVersionsVerificationUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Syntax-check touched Python files**

Run:

```bash
python -m py_compile backend/services/active_collection_components.py backend/services/component_runtime_resolver.py backend/services/component_version_service.py backend/routers/component_versions.py modules/apps/collection_center/component_loader.py
```

Expected: no output

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify active component and archive isolation foundation"
```

---

## Follow-Up Work

After this plan lands:

1. run a real stable-pointer audit against the current database
2. move safe legacy files into `archive/`
3. repeat for each platform as V2 active coverage expands

Do not move large batches of legacy files before the guards in this plan are live.

---

Plan complete and saved to `docs/superpowers/plans/2026-03-27-active-components-and-archive-isolation.md`. Ready to execute?
