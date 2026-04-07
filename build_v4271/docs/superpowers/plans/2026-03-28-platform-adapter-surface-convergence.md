# Platform Adapter Surface Convergence Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status note (2026-03-28):** This convergence plan is functionally landed. Legacy default adapter surfaces have been locked down, key archive moves were completed, and this file should now be treated as a historical execution plan. Do not reopen the unchecked steps below as default backlog unless a new gap is first confirmed in `task_plan.md`.

**Goal:** Remove the old platform-adapter and legacy collection-center surface as a default execution path across all collection platforms, so only the approved V2 active components remain in the live workflow and old helper/export components can safely move to archive.

**Architecture:** This work targets the old adapter entrypoints, not the new V2 runtime. The key rule is that `modules/apps/collection_center/app.py`, `modules/services/platform_adapter.py`, and per-platform adapters must stop exposing legacy `navigation/date_picker/exporter/shop_selector` component chains as active production behavior. V2 active components remain the only supported runtime path; old adapter capabilities should either be downgraded to explicit unsupported paths or redirected to canonical V2 components where that mapping is safe.

**Tech Stack:** Python component runtime, FastAPI backend services, collection-center legacy app surface, SQLAlchemy-backed component version metadata

---

## Scope

This plan covers:

- legacy adapter surface audit and convergence
- old `collection_center/app.py` entrypoint isolation
- platform-level adapter slimming for `shopee`, `tiktok`, `miaoshou`
- follow-up conditions for moving second-batch legacy files into archive

This plan does **not** include:

- building new V2 components for every remaining platform/domain
- deleting the old collection-center app immediately
- changing the stable runtime manifest mechanism

## Audit Snapshot

Current findings from `modules/apps/collection_center/app.py`:

- `get_adapter(` appears 16 times
- `adapter.login(` appears 9 times
- `adapter.navigation(` appears 12 times
- `adapter.date_picker(` appears 10 times
- `adapter.exporter(` appears 11 times
- `adapter.shop_selector(` appears 3 times

This means old adapter-driven flows still exist as a real entry surface and block safe archive moves for old platform helper/export components.

## File Map

### Primary files

- Modify: `modules/services/platform_adapter.py`
  - Central adapter registry and factory.
- Modify: `modules/platforms/shopee/adapter.py`
- Modify: `modules/platforms/tiktok/adapter.py`
- Modify: `modules/platforms/miaoshou/adapter.py`
  - Platform-specific old adapter capability surfaces.
- Modify: `modules/apps/collection_center/app.py`
  - Legacy collection-center execution and local/manual entrypoints still using `get_adapter(...)`.

### Tests

- Add: `backend/tests/test_platform_adapter_surface_convergence.py`
- Add: `backend/tests/test_collection_center_app_adapter_usage_contract.py`
- Re-run:
  - `backend/tests/test_component_tester_version_resolution.py`
  - `backend/tests/test_component_tester_gate_contract.py`
  - `backend/tests/test_miaoshou_export_contract.py`

### Related docs

- Modify: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`
- Modify: `docs/guides/COMPONENT_COLLABORATION.md`
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`

---

### Task 1: Define The New Adapter Policy In Tests

**Files:**
- Create: `backend/tests/test_platform_adapter_surface_convergence.py`
- Create: `backend/tests/test_collection_center_app_adapter_usage_contract.py`

- [ ] **Step 1: Write failing policy tests**

Cover:
- only approved active V2 components should remain effectively reachable through default adapter/runtime surfaces
- adapter methods for non-active legacy slots must be either absent or explicitly rejected
- `collection_center/app.py` should stop treating adapter-driven legacy component chains as the default path for collection work

Run:

```bash
pytest backend/tests/test_platform_adapter_surface_convergence.py backend/tests/test_collection_center_app_adapter_usage_contract.py -q
```

Expected: FAIL because current adapters still expose legacy helper/export surfaces and `app.py` still calls them.

- [ ] **Step 2: Commit the failing test baseline**

```bash
git add backend/tests/test_platform_adapter_surface_convergence.py backend/tests/test_collection_center_app_adapter_usage_contract.py
git commit -m "test: define platform adapter convergence contract"
```

### Task 2: Converge The Central Adapter Registry

**Files:**
- Modify: `modules/services/platform_adapter.py`
- Modify: `modules/platforms/adapter_base.py`

- [ ] **Step 1: Introduce explicit legacy-surface semantics**

Decide and implement one consistent rule:
- either active-only adapters are returned for default runtime paths, or
- legacy adapters remain constructible but their deprecated methods raise clear unsupported errors

Do not allow silent continued use of old slot chains.

- [ ] **Step 2: Re-run focused adapter policy tests**

Run:

```bash
pytest backend/tests/test_platform_adapter_surface_convergence.py -q
```

Expected: still failing until per-platform adapters are updated, but central policy should be in place.

### Task 3: Slim Per-Platform Adapters

**Files:**
- Modify: `modules/platforms/shopee/adapter.py`
- Modify: `modules/platforms/tiktok/adapter.py`
- Modify: `modules/platforms/miaoshou/adapter.py`

- [ ] **Step 1: Map active vs legacy capabilities per platform**

Use the active manifest as the source of truth:
- `miaoshou`: keep only `login` and the approved orders export path
- `shopee`: mark old surfaces legacy/inactive until V2 migration happens
- `tiktok`: mark old surfaces legacy/inactive until V2 migration happens

- [ ] **Step 2: Implement adapter slimming**

Per adapter:
- remove or explicitly reject legacy `navigation/date_picker/exporter/shop_selector` access where they no longer belong in the default workflow
- avoid silently importing old components that are slated for archive

- [ ] **Step 3: Re-run adapter policy tests**

Run:

```bash
pytest backend/tests/test_platform_adapter_surface_convergence.py backend/tests/test_component_tester_version_resolution.py backend/tests/test_component_tester_gate_contract.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add modules/services/platform_adapter.py modules/platforms/adapter_base.py modules/platforms/shopee/adapter.py modules/platforms/tiktok/adapter.py modules/platforms/miaoshou/adapter.py backend/tests/test_platform_adapter_surface_convergence.py backend/tests/test_component_tester_version_resolution.py backend/tests/test_component_tester_gate_contract.py
git commit -m "refactor: converge legacy platform adapter surfaces"
```

### Task 4: Isolate Legacy `collection_center/app.py` Entry Surfaces

**Files:**
- Modify: `modules/apps/collection_center/app.py`
- Re-run: `backend/tests/test_miaoshou_export_contract.py`

- [ ] **Step 1: Classify old adapter-driven entrypoints**

Document which `collection_center/app.py` paths are:
- obsolete and should be disabled
- fallback-only and should be clearly marked
- still needed temporarily but must stop using legacy adapter methods

- [ ] **Step 2: Implement minimal safe convergence**

For the old app surface:
- stop presenting adapter-driven legacy component chains as the recommended/default flow
- where safe, redirect to V2 canonical components
- where not safe, fail explicitly instead of silently using old legacy slot chains

- [ ] **Step 3: Re-run collection-center app contract tests**

Run:

```bash
pytest backend/tests/test_collection_center_app_adapter_usage_contract.py backend/tests/test_miaoshou_export_contract.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add modules/apps/collection_center/app.py backend/tests/test_collection_center_app_adapter_usage_contract.py backend/tests/test_miaoshou_export_contract.py
git commit -m "refactor: isolate legacy collection-center adapter entrypoints"
```

### Task 5: Re-evaluate Archive Candidates After Adapter Convergence

**Files:**
- Modify: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] **Step 1: Re-run candidate audit for**

- `modules/platforms/miaoshou/components/export.py`
- `modules/platforms/miaoshou/components/navigation.py`
- `modules/platforms/miaoshou/components/date_picker.py`
- the corresponding Shopee/TikTok old slot files

- [ ] **Step 2: Update archive readiness notes**

Record:
- which files are now safe to move
- which still have remaining dependencies

- [ ] **Step 3: Commit**

```bash
git add docs/guides/ACTIVE_COLLECTION_COMPONENTS.md findings.md progress.md
git commit -m "docs: update archive readiness after adapter convergence"
```

### Task 6: Final Verification

**Files:**
- Test only

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
pytest backend/tests/test_platform_adapter_surface_convergence.py backend/tests/test_collection_center_app_adapter_usage_contract.py backend/tests/test_component_tester_version_resolution.py backend/tests/test_component_tester_gate_contract.py backend/tests/test_miaoshou_export_contract.py -q
```

Expected: PASS

- [ ] **Step 2: Syntax-check touched Python files**

Run:

```bash
python -m py_compile modules/services/platform_adapter.py modules/platforms/adapter_base.py modules/platforms/shopee/adapter.py modules/platforms/tiktok/adapter.py modules/platforms/miaoshou/adapter.py modules/apps/collection_center/app.py
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: verify platform adapter surface convergence"
```

---

## Follow-Up

After this plan lands:

1. run the second archive move for old Miaoshou helper/export files
2. repeat the same archive pass for Shopee and TikTok old slot files
3. start the next V2 component migrations only after the legacy adapter entry surface is no longer the default path

---

Plan complete and saved to `docs/superpowers/plans/2026-03-28-platform-adapter-surface-convergence.md`. Ready to execute?
