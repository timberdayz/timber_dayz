# Collection Output Path Unification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `data/raw/` the only formal collection output root while keeping `temp/outputs/` as legacy read compatibility only.

**Architecture:** Keep the executor’s download work directory separate from the formal raw-data store. Promote completed exports into `data/raw/YYYY/`, register catalog records as `data/raw`, and update path resolution to prefer `data/raw` while still tolerating legacy `temp/outputs` records during migration.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest, pathlib

---

### Task 1: Write the approved design into code-facing docs

**Files:**
- Create: `docs/superpowers/specs/2026-03-27-collection-output-path-unification-design.md`
- Create: `docs/superpowers/plans/2026-03-27-collection-output-path-unification.md`

- [ ] **Step 1: Save the design doc**

Include:
- formal-vs-temporary directory semantics
- scope and non-goals
- compatibility boundary for legacy `temp/outputs`

- [ ] **Step 2: Save the implementation plan**

Run:
```powershell
Get-Content docs\superpowers\specs\2026-03-27-collection-output-path-unification-design.md
```

Expected:
- design doc exists and reflects the approved direction

### Task 2: Add failing tests for canonical path semantics

**Files:**
- Create: `backend/tests/test_collection_output_path_unification.py`

- [ ] **Step 1: Write a failing test for CatalogFile default source**

```python
from modules.core.db.schema import CatalogFile

def test_catalog_file_defaults_to_data_raw_source():
    record = CatalogFile(file_path="data/raw/2026/file.xlsx", file_name="file.xlsx")
    assert record.source == "data/raw"
```

- [ ] **Step 2: Write a failing test for file path resolver canonical path**

```python
def test_file_path_resolver_rebuilds_data_raw_path():
    ...
```

Assert that the rebuilt path is under `data/raw/<year>/`.

- [ ] **Step 3: Write a failing test for legacy search ordering**

```python
def test_file_path_resolver_prefers_data_raw_before_legacy_temp_outputs():
    ...
```

- [ ] **Step 4: Run the focused tests to verify they fail**

Run:
```powershell
pytest backend\tests\test_collection_output_path_unification.py -q
```

Expected:
- FAIL because current defaults/resolution still encode legacy semantics

### Task 3: Implement canonical formal output semantics

**Files:**
- Modify: `modules/core/db/schema.py`
- Modify: `backend/services/file_path_resolver.py`
- Modify: `modules/apps/collection_center/executor_v2.py`

- [ ] **Step 1: Update `CatalogFile.source` default to `data/raw`**

Keep comments explicit about legacy compatibility.

- [ ] **Step 2: Refactor `FilePathResolver`**

Implement:
- canonical template under `data/raw/{year}/{filename}`
- search base dirs ordered as `data/raw`, `downloads`, `data/input`, legacy `temp/outputs`
- legacy fallback comments so future edits do not reintroduce dual-chain semantics

- [ ] **Step 3: Refactor executor raw-data target directory to use path manager**

Use `get_data_raw_dir()` instead of hard-coded `Path("data/raw")`.

- [ ] **Step 4: Keep temp/outputs support read-only**

Do not remove legacy fallback branches that are still needed for existing records.

### Task 4: Verify green and check for regressions

**Files:**
- Test: `backend/tests/test_collection_output_path_unification.py`
- Test: existing targeted collection/runtime tests as needed

- [ ] **Step 1: Run focused new tests**

Run:
```powershell
pytest backend\tests\test_collection_output_path_unification.py -q
```

Expected:
- PASS

- [ ] **Step 2: Run targeted existing runtime tests**

Run:
```powershell
pytest backend\tests\test_runtime_gate_contract.py -q
```

Expected:
- PASS

- [ ] **Step 3: Review git diff for scope drift**

Run:
```powershell
git diff -- modules/core/db/schema.py backend/services/file_path_resolver.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_output_path_unification.py docs/superpowers/specs/2026-03-27-collection-output-path-unification-design.md docs/superpowers/plans/2026-03-27-collection-output-path-unification.md
```

Expected:
- changes are limited to path-unification scope
