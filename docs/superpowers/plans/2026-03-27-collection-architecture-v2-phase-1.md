# Collection Architecture V2 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the collection system onto a V2 foundation with one canonical topology model, one runtime/test contract, and one default registration/testing path, while freezing legacy component layers out of the default workflow.

**Architecture:** Phase 1 does not migrate every platform component. It first establishes the shared V2 rules that every future component must obey: canonical filenames and slots, rule-driven registration, a stable `time_selection + granularity` contract, and a simplified execution/testing chain. Legacy files remain on disk temporarily but must stop acting as default maintenance targets.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Vue 3, Element Plus, async Playwright, Python component runtime

---

## Scope

This plan covers the first V2 architecture slice only:

- canonical component topology and rule-driven registration
- shared runtime/test/collection contract convergence
- execution-chain simplification and component boundary cleanup
- freezing legacy compatibility layers out of default registration and UI surfaces

This plan explicitly does **not** include:

- deleting all legacy files
- migrating output/data sync paths
- rewriting every platform component in the same pass

Follow-up migration plans should move platform slots onto the new foundation after this phase lands.

## Verification Recovery Constraints

The Phase 1 refactor must preserve the current shared verification recovery contract for both component testing and formal collection:

- verification input remains **mutually exclusive**:
  - `captcha_code`
  - `otp`
- component testing recovery path:
  - progress state uses `verification_required -> verification_submitted -> verification_retrying/resolved/failed`
  - screenshot and metadata live under the test directory
  - user submission is written to `verification_response.json`
  - the same test session/page resumes after submission
- formal collection recovery path:
  - paused task resumes only from `status="paused"` plus `verification_type` present
  - user submission is written to Redis
  - the same collection execution/page resumes after submission
- shared verification fields exposed to frontend/status endpoints must remain stable:
  - `verification_type`
  - `verification_screenshot`
  - `verification_id`
  - `verification_message`
  - `verification_expires_at`
  - `verification_attempt_count`

Phase 1 may simplify topology and execution boundaries, but it must not break these recovery semantics.

## File Map

### New files

- `backend/services/collection_component_topology.py`
  - Single source of truth for canonical slot names, canonical filename rules, legacy exclusion rules, and logical component-name helpers.
- `backend/tests/test_collection_component_topology.py`
  - Contract tests for canonical recognition, exporter auto-detection, and legacy exclusions.

### Modified backend/runtime files

- `backend/routers/component_versions.py`
  - Stop hardcoding platform allowlists inline; route batch registration and list filtering through the topology service.
- `backend/services/collection_contracts.py`
  - Remain the SSOT for `time_selection`, preset-to-granularity mapping, and legacy compatibility normalization.
- `backend/routers/collection_config.py`
  - Continue converging formal collection config onto `time_selection`.
- `backend/routers/collection_tasks.py`
  - Ensure task creation uses the same normalized contract as tests and formal config.
- `backend/schemas/component_version.py`
  - Keep test request schema aligned to the unified contract and reject conflicting input shapes.
- `backend/schemas/collection.py`
  - Keep formal collection schema aligned to the unified contract.
- `modules/apps/collection_center/python_component_adapter.py`
  - Stop embedding its own topology assumptions; read slot/component rules from the shared topology layer.
- `modules/apps/collection_center/executor_v2.py`
  - Keep execution order focused on `login -> export`, and remove remaining assumptions that non-export top-level slots should be driven as separate formal runtime phases.
- `modules/apps/collection_center/transition_gates.py`
  - Align gate boundaries to the V2 component model and keep login/export transitions explicit.
- `tools/test_component.py`
  - Keep the component tester aligned with the same runtime contract and slot model used by formal collection.

### Modified frontend/docs files

- `frontend/src/views/ComponentVersions.vue`
  - Surface only the V2 time-selection model and hide legacy/conflicting input combinations.
- `frontend/src/views/ComponentRecorder.vue`
  - Stop implying recorder-generated compatibility files are primary maintenance targets.
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
  - Rewrite around V2 slot rules and freeze/archive guidance.
- `docs/guides/COMPONENT_COLLABORATION.md`
  - Rewrite around the V2 execution chain and bounded helper structure.
- `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
  - Add explicit handoff rules from `pwcli` exploration to canonical V2 components.

### Regression tests to update or keep green

- `backend/tests/test_component_versions_canonical_registration.py`
- `backend/tests/test_component_test_runtime_config.py`
- `backend/tests/test_component_tester_runtime_config.py`
- `backend/tests/test_collection_contracts.py`
- `backend/tests/test_collection_time_selection_contract.py`
- `backend/tests/test_transition_gates_contract.py`

---

### Task 1: Establish The V2 Topology SSOT

**Files:**
- Create: `backend/services/collection_component_topology.py`
- Create: `backend/tests/test_collection_component_topology.py`
- Modify: `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`

- [ ] **Step 1: Write the failing topology tests**

Add tests for:
- canonical fixed slots: `login.py`, `navigation.py`, `date_picker.py`, `shop_switch.py`, `filters.py`
- domain exporters: any `*_export.py`
- exclusions: `*_config.py`, `overlay_guard.py`, versioned files such as `login_v1_0_3.py`, and recorder-only compatibility files
- logical component name derivation such as `miaoshou/orders_export`

Run: `pytest backend/tests/test_collection_component_topology.py -q`
Expected: FAIL because the topology SSOT does not exist yet.

- [ ] **Step 2: Implement the topology service**

Create `backend/services/collection_component_topology.py` with focused helpers, for example:

```python
CANONICAL_FIXED_COMPONENTS = {"login", "navigation", "date_picker", "shop_switch", "filters"}

def is_canonical_component_filename(filename: str) -> bool: ...
def is_legacy_component_filename(filename: str) -> bool: ...
def build_component_name(platform: str, filename: str) -> str: ...
def list_canonical_component_names(platform: str | None = None) -> list[str]: ...
```

Keep it rule-driven rather than platform allowlist-driven.

- [ ] **Step 3: Re-run topology tests**

Run: `pytest backend/tests/test_collection_component_topology.py -q`
Expected: PASS

- [ ] **Step 4: Rewrite the canonical guide around the new rules**

Update `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md` so it no longer presents recorder-era compatibility files as normal maintenance targets.

- [ ] **Step 5: Commit**

```bash
git add backend/services/collection_component_topology.py backend/tests/test_collection_component_topology.py docs/guides/CANONICAL_COLLECTION_COMPONENTS.md
git commit -m "refactor: add V2 collection component topology rules"
```

### Task 2: Converge Registration And Discovery On The Topology Service

**Files:**
- Modify: `backend/routers/component_versions.py`
- Modify: `modules/apps/collection_center/python_component_adapter.py`
- Test: `backend/tests/test_component_versions_canonical_registration.py`

- [ ] **Step 1: Extend registration tests for rule-driven discovery**

Add or update tests so batch registration:
- includes canonical fixed slots
- includes `*_export.py`
- excludes `*_config.py`, versioned files, and known compatibility-only files
- does not require editing a per-platform hardcoded filename set

Run: `pytest backend/tests/test_component_versions_canonical_registration.py -q`
Expected: FAIL with current inline allowlist logic.

- [ ] **Step 2: Route batch registration through the topology service**

Modify `backend/routers/component_versions.py` to replace inline allowlist checks with imports from `backend/services/collection_component_topology.py`.

- [ ] **Step 3: Route adapter discovery through the same slot logic**

Modify `modules/apps/collection_center/python_component_adapter.py` so:
- canonical slot detection does not drift from batch registration rules
- exporter discovery continues to resolve `*_export` consistently
- legacy compatibility files are not treated as first-class logical slots

- [ ] **Step 4: Re-run registration tests**

Run: `pytest backend/tests/test_component_versions_canonical_registration.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/component_versions.py modules/apps/collection_center/python_component_adapter.py backend/tests/test_component_versions_canonical_registration.py
git commit -m "refactor: converge registration on V2 topology rules"
```

### Task 3: Lock The Shared Runtime Contract

**Files:**
- Modify: `backend/services/collection_contracts.py`
- Modify: `backend/schemas/component_version.py`
- Modify: `backend/schemas/collection.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `tools/test_component.py`
- Test: `backend/tests/test_collection_contracts.py`
- Test: `backend/tests/test_collection_time_selection_contract.py`
- Test: `backend/tests/test_component_test_runtime_config.py`
- Test: `backend/tests/test_component_tester_runtime_config.py`

- [ ] **Step 1: Strengthen failing contract tests**

Cover:
- preset/custom mutual exclusion
- global hard mapping:
  - `today -> daily`
  - `yesterday -> daily`
  - `last_7_days -> weekly`
  - `last_30_days -> monthly`
- custom mode requires explicit `granularity`
- runtime config builder always emits one `time_selection` shape

Run:

```bash
pytest backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py -q
```

Expected: FAIL until all entrypoints enforce the same contract.

- [ ] **Step 2: Finish normalizing all entrypoints**

Use `backend/services/collection_contracts.py` as the only normalization/mapping hub. Ensure test requests, formal collection config, task creation, and component tester runtime config all flow through it.

- [ ] **Step 3: Re-run contract tests**

Run:

```bash
pytest backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/collection_contracts.py backend/schemas/component_version.py backend/schemas/collection.py backend/routers/collection_config.py backend/routers/collection_tasks.py tools/test_component.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py
git commit -m "refactor: unify collection time selection contract"
```

### Task 4: Simplify The Execution Chain And Component Boundaries

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `modules/apps/collection_center/transition_gates.py`
- Modify: `docs/guides/COMPONENT_COLLABORATION.md`
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
- Test: `backend/tests/test_transition_gates_contract.py`

- [ ] **Step 1: Write failing boundary tests**

Add or tighten tests to assert:
- formal runtime top-level chain is `login -> export`
- `navigation/date_picker/shop_switch/filters` are helper slots rather than independent formal runtime phases
- transition gates match these boundaries

Run: `pytest backend/tests/test_transition_gates_contract.py -q`
Expected: FAIL if the current gate/phase model still exposes old boundaries.

- [ ] **Step 2: Refactor the execution/gate chain**

Update `executor_v2.py` and `transition_gates.py` so the formal runtime only treats login and export as top-level phases, while helper slots remain internal to export flows.

- [ ] **Step 3: Rewrite collaboration and SOP docs**

Update docs so they describe the actual V2 chain:

`pwcli exploration -> agent analysis -> canonical component -> local verification -> version test -> stable`

and clarify that helper slots are reused internally, not scheduled as separate collection phases.

- [ ] **Step 4: Re-run boundary tests**

Run: `pytest backend/tests/test_transition_gates_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py modules/apps/collection_center/transition_gates.py docs/guides/COMPONENT_COLLABORATION.md docs/guides/PWCLI_AGENT_COLLECTION_SOP.md backend/tests/test_transition_gates_contract.py
git commit -m "refactor: simplify collection execution chain for V2"
```

### Task 5: Freeze Legacy Layers Out Of Default Surfaces

**Files:**
- Modify: `frontend/src/views/ComponentVersions.vue`
- Modify: `frontend/src/views/ComponentRecorder.vue`
- Modify: `docs/superpowers/specs/2026-03-27-collection-architecture-v2-design.md`
- Test: `frontend/scripts/componentVersionsVerificationUi.test.mjs`

- [ ] **Step 1: Write or update a failing UI/behavior test**

Cover:
- canonical registration/testing surface should prefer canonical V2 component names
- recorder UI should not imply compatibility layers are the primary maintenance path

Run: `node frontend/scripts/componentVersionsVerificationUi.test.mjs`
Expected: FAIL until the UI reflects the V2 freeze strategy.

- [ ] **Step 2: Update default UI messaging and filters**

Adjust the component management/recorder surfaces so legacy compatibility files are treated as archive/runtime artifacts rather than default edit targets.

- [ ] **Step 3: Re-run UI verification**

Run: `node frontend/scripts/componentVersionsVerificationUi.test.mjs`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ComponentVersions.vue frontend/src/views/ComponentRecorder.vue docs/superpowers/specs/2026-03-27-collection-architecture-v2-design.md frontend/scripts/componentVersionsVerificationUi.test.mjs
git commit -m "refactor: freeze legacy collection component surfaces"
```

### Task 6: End-To-End Regression Check For The New Foundation

**Files:**
- Test only

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
pytest backend/tests/test_collection_component_topology.py backend/tests/test_component_versions_canonical_registration.py backend/tests/test_collection_contracts.py backend/tests/test_collection_time_selection_contract.py backend/tests/test_component_test_runtime_config.py backend/tests/test_component_tester_runtime_config.py backend/tests/test_transition_gates_contract.py -q
```

Expected: PASS

- [ ] **Step 2: Run focused frontend verification**

Run:

```bash
node frontend/scripts/componentVersionsVerificationUi.test.mjs
```

Expected: PASS

- [ ] **Step 3: Sanity-check modified Python files**

Run:

```bash
python -m py_compile backend/routers/component_versions.py backend/routers/collection_config.py backend/routers/collection_tasks.py backend/services/collection_component_topology.py backend/services/collection_contracts.py modules/apps/collection_center/python_component_adapter.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/transition_gates.py tools/test_component.py
```

Expected: no output

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify collection architecture V2 phase 1 foundation"
```

---

## Follow-Up Plans

After this phase lands, write separate plans for:

1. `miaoshou/login` V2 migration
2. `miaoshou/orders_export` V2 migration
3. `shopee/login` and `shopee/orders_export` V2 migration
4. `tiktok/login` and `tiktok/orders_export` V2 migration
5. legacy file archival/removal after stable runtime no longer depends on them

Do not combine those platform migrations into this foundation phase.

---

## Execution Notes

- Prefer focused files over widening old monoliths.
- Do not add new business logic to legacy compatibility files.
- Keep runtime Playwright async-first.
- Keep `granularity` for output/ingest/scheduling only; page-side time behavior must flow from `time_selection`.
- Keep `pwcli` limited to development/exploration, never formal runtime.

Plan complete and saved to `docs/superpowers/plans/2026-03-27-collection-architecture-v2-phase-1.md`. Ready to execute?
