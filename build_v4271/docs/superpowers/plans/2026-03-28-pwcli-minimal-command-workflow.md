# pwcli Minimal Command Workflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal `pwcli` command workflow that lets users collect evidence for formal collection components with low-friction commands and stable output structure.

**Architecture:** Keep `scripts/pwcli.ps1` as the low-level raw CLI wrapper, then add a small workflow layer on top of it. Put naming, path, and pack-validation rules in a testable Python helper so PowerShell wrappers stay thin and deterministic. The wrappers should produce a consistent evidence package that agent can consume to generate canonical Python components.

**Tech Stack:** PowerShell, Python, playwright-cli (`npx @playwright/cli`), pytest, pathlib, json

---

### Task 1: Lock the implementation surface and document the intended command set

**Files:**
- Create: `docs/superpowers/plans/2026-03-28-pwcli-minimal-command-workflow.md`
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
- Reference: `docs/superpowers/specs/2026-03-28-pwcli-minimal-command-workflow-design.md`

- [ ] **Step 1: Re-read the design doc and SOP before implementation**

Run:
```powershell
Get-Content docs\superpowers\specs\2026-03-28-pwcli-minimal-command-workflow-design.md
Get-Content docs\guides\PWCLI_AGENT_COLLECTION_SOP.md
```

Expected:
- command names and workflow responsibilities match the approved design

- [ ] **Step 2: Add an implementation-oriented command summary to the SOP**

Document:
- `pw-open`
- `pw-step`
- `pw-note`
- `pw-shot`
- `pw-pack`

Keep the SOP explicit that these are wrappers around `pwcli`, not a replacement for canonical component generation.

- [ ] **Step 3: Freeze scope for v1**

State in the SOP that v1 does **not** include:
- automatic agent invocation
- automatic component generation
- replacement of version management / stable flow
- browser event recording / replay

### Task 2: Add failing tests for naming, pathing, and evidence-pack validation

**Files:**
- Create: `tests/test_pwcli_workflow.py`
- Create: `scripts/pwcli_workflow.py`

- [ ] **Step 1: Write a failing test for workspace directory normalization**

```python
from pathlib import Path

from scripts.pwcli_workflow import build_work_dir


def test_build_work_dir_uses_platform_and_work_tag(tmp_path: Path):
    result = build_work_dir(
        repo_root=tmp_path,
        platform="miaoshou",
        work_tag="login",
    )
    assert result == tmp_path / "output" / "playwright" / "work" / "miaoshou-login"
```

- [ ] **Step 2: Write a failing test for step evidence file naming**

```python
from scripts.pwcli_workflow import build_step_snapshot_path


def test_build_step_snapshot_path_formats_step_name_and_phase(tmp_path):
    path = build_step_snapshot_path(
        work_dir=tmp_path,
        step="01",
        name="submit-login",
        phase="before",
    )
    assert path.name == "01-submit-login-before.txt"
```

- [ ] **Step 3: Write a failing test for note file naming**

```python
from scripts.pwcli_workflow import build_note_path


def test_build_note_path_uses_step_prefix(tmp_path):
    path = build_note_path(work_dir=tmp_path, step="04")
    assert path.name == "04-note.txt"
```

- [ ] **Step 4: Write a failing test for evidence pack validation**

```python
from scripts.pwcli_workflow import validate_work_package


def test_validate_work_package_requires_before_after_pairs(tmp_path):
    (tmp_path / "01-open-login-before.txt").write_text("before", encoding="utf-8")
    report = validate_work_package(tmp_path)
    assert report["ok"] is False
    assert "missing after snapshot" in " ".join(report["errors"]).lower()
```

- [ ] **Step 5: Write a failing test for pack manifest generation**

```python
from scripts.pwcli_workflow import build_pack_manifest


def test_build_pack_manifest_sorts_steps_and_includes_notes(tmp_path):
    ...
```

Assert that the manifest:
- sorts by step id
- records available `before/after`
- includes optional note and screenshot paths

- [ ] **Step 6: Run focused tests to verify they fail**

Run:
```powershell
pytest tests\test_pwcli_workflow.py -q
```

Expected:
- FAIL because the helper module does not exist yet

### Task 3: Implement a testable workflow core in Python

**Files:**
- Create: `scripts/pwcli_workflow.py`
- Test: `tests/test_pwcli_workflow.py`

- [ ] **Step 1: Implement work directory helpers**

Implement pure functions for:
- `sanitize_token(value: str) -> str`
- `build_work_dir(repo_root: Path, platform: str, work_tag: str) -> Path`
- `build_session_name(platform: str, work_tag: str) -> str`

Keep them filesystem-safe and deterministic.

- [ ] **Step 2: Implement evidence path helpers**

Implement:
- `build_step_snapshot_path(...)`
- `build_note_path(...)`
- `build_screenshot_path(...)`

Rules:
- preserve zero-padded step ids
- normalize step names to kebab-case
- preserve `before` / `after` suffix

- [ ] **Step 3: Implement evidence scanning and validation**

Implement:
- `scan_work_dir(work_dir: Path) -> dict`
- `validate_work_package(work_dir: Path) -> dict`

Validation rules for v1:
- every step with a `before` must have a matching `after`
- unknown file names are reported as warnings, not fatal errors
- notes and screenshots are optional

- [ ] **Step 4: Implement pack manifest generation**

Implement:
- `build_pack_manifest(work_dir: Path) -> dict`
- `write_pack_manifest(work_dir: Path) -> Path`

Manifest should include:
- platform
- work tag
- sorted step list
- per-step evidence paths
- validation summary

- [ ] **Step 5: Run tests to verify green**

Run:
```powershell
pytest tests\test_pwcli_workflow.py -q
```

Expected:
- PASS

### Task 4: Add the PowerShell wrappers for the minimal command set

**Files:**
- Modify: `scripts/pwcli.ps1`
- Create: `scripts/pw-open.ps1`
- Create: `scripts/pw-step.ps1`
- Create: `scripts/pw-note.ps1`
- Create: `scripts/pw-shot.ps1`
- Create: `scripts/pw-pack.ps1`
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`

- [ ] **Step 1: Keep `scripts/pwcli.ps1` as the raw passthrough wrapper**

Do not overload it with workflow semantics. Keep it responsible only for:
- forwarding arguments to `playwright-cli`
- preserving raw access for advanced users

- [ ] **Step 2: Implement `pw-open.ps1`**

Responsibilities:
- resolve repo root
- call `build_work_dir`
- create work directory
- compute session name
- set `PLAYWRIGHT_CLI_SESSION` for the current process
- call `scripts/pwcli.ps1 open <url>`

Example command:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-open.ps1 -Platform miaoshou -WorkTag login -Url "https://erp.91miaoshou.com"
```

- [ ] **Step 3: Implement `pw-step.ps1`**

Responsibilities:
- resolve work directory
- compute output file path with helper
- call `scripts/pwcli.ps1 snapshot`
- save the **full command output** to `*.txt` using UTF-8

Example command:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-step.ps1 -Platform miaoshou -WorkTag login -Step 01 -Name open-login-page -Phase before
```

- [ ] **Step 4: Implement `pw-note.ps1`**

Responsibilities:
- write a one-line UTF-8 note to `<step>-note.txt`
- append or replace consistently (pick one behavior and document it)

- [ ] **Step 5: Implement `pw-shot.ps1`**

Responsibilities:
- compute screenshot output path
- call `scripts/pwcli.ps1 screenshot`
- move or save artifact into the work directory with the normalized name

- [ ] **Step 6: Implement `pw-pack.ps1`**

Responsibilities:
- call the Python helper validator
- print a concise summary
- write `evidence-pack.json` into the work directory
- return non-zero exit code when fatal validation errors exist

### Task 5: Document the user-facing workflow with exact commands

**Files:**
- Modify: `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md`
- Optionally create: `docs/guides/PWCLI_MINIMAL_WORKFLOW.md`

- [ ] **Step 1: Add a “minimal workflow” section to the SOP**

Include one end-to-end example:
- open session
- capture `before`
- perform manual action
- capture `after`
- add note for a complex step
- pack evidence

- [ ] **Step 2: Add command examples for login evidence collection**

Use examples like:
```powershell
.\scripts\pw-open.ps1 -Platform miaoshou -WorkTag login -Url "https://erp.91miaoshou.com"
.\scripts\pw-step.ps1 -Platform miaoshou -WorkTag login -Step 01 -Name open-login-page -Phase before
```

- [ ] **Step 3: Add explicit guidance on what is optional**

Document that:
- `note` is optional
- `step.json` is not required in v1
- `pwcli snapshot` full output is preferred over raw `.yml` alone

### Task 6: Verify the wrappers with dry-run workflow checks

**Files:**
- Test: `tests/test_pwcli_workflow.py`
- Script: `scripts/pw-open.ps1`
- Script: `scripts/pw-step.ps1`
- Script: `scripts/pw-pack.ps1`

- [ ] **Step 1: Run Python tests**

Run:
```powershell
pytest tests\test_pwcli_workflow.py -q
```

Expected:
- PASS

- [ ] **Step 2: Run `pw-open` against a harmless URL**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-open.ps1 -Platform miaoshou -WorkTag smoke -Url "https://example.com"
```

Expected:
- work directory created
- browser opens in the named session

- [ ] **Step 3: Run `pw-step` before/after on the smoke session**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-step.ps1 -Platform miaoshou -WorkTag smoke -Step 01 -Name open-example -Phase before
```

Expected:
- `01-open-example-before.txt` created under the work directory
- file contains `Page URL: https://example.com/`

- [ ] **Step 4: Run `pw-pack` on the smoke workspace**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pw-pack.ps1 -Platform miaoshou -WorkTag smoke
```

Expected:
- validation summary printed
- `evidence-pack.json` created

- [ ] **Step 5: Review diff for scope drift**

Run:
```powershell
git diff -- scripts/pwcli.ps1 scripts/pw-open.ps1 scripts/pw-step.ps1 scripts/pw-note.ps1 scripts/pw-shot.ps1 scripts/pw-pack.ps1 scripts/pwcli_workflow.py tests/test_pwcli_workflow.py docs/guides/PWCLI_AGENT_COLLECTION_SOP.md docs/superpowers/specs/2026-03-28-pwcli-minimal-command-workflow-design.md docs/superpowers/plans/2026-03-28-pwcli-minimal-command-workflow.md
```

Expected:
- changes limited to the minimal command workflow scope
