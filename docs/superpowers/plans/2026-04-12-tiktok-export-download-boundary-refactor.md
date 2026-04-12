# TikTok Export Download Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor TikTok export completion handling so each top-level export component owns its export trigger and download collection stages while sharing only low-level download primitives.

**Architecture:** Keep the current TikTok page entry, shop switch, and date-picker behavior intact. Move download capture, timeout resolution, listener cleanup, save-to-target, and file validation into a new low-level helper module, then make `products_export`, `analytics_export`, and `services_agent_export` explicitly own `trigger_export` and `collect_download_result` without depending on `TiktokExport.run()` as the semantic export implementation.

**Tech Stack:** Python, Playwright async runtime, existing `ExecutionContext` / `ExportResult` contracts, pytest unit tests, collection transition gates, @test-driven-development, @verification-before-completion.

---

## File Map

- `modules/platforms/tiktok/components/_download_helpers.py`
  Responsibility: stable download primitives only. No page-specific export meaning.
- `modules/platforms/tiktok/components/export.py`
  Responsibility: temporary compatibility shim while primitives are extracted from the old shared exporter.
- `modules/platforms/tiktok/components/products_export.py`
  Responsibility: products page flow plus explicit export trigger and download collection stages.
- `modules/platforms/tiktok/components/analytics_export.py`
  Responsibility: analytics page flow plus explicit export trigger and download collection stages.
- `modules/platforms/tiktok/components/services_agent_export.py`
  Responsibility: services-agent business readiness plus explicit export trigger and download collection stages, including current no-data success semantics.
- `backend/tests/test_tiktok_download_helpers.py`
  Responsibility: focused unit coverage for low-level TikTok download helpers.
- `backend/tests/test_tiktok_export_component.py`
  Responsibility: compatibility coverage for extracted behavior from the current shared TikTok exporter.
- `backend/tests/test_tiktok_products_export_component.py`
  Responsibility: products top-level export orchestration tests.
- `backend/tests/test_tiktok_analytics_export_component.py`
  Responsibility: analytics top-level export orchestration tests.
- `backend/tests/test_tiktok_services_agent_export_component.py`
  Responsibility: services-agent top-level export orchestration tests.
- `backend/tests/test_component_tester_gate_contract.py`
  Responsibility: gate-level validation that successful TikTok exports still surface valid `file_path` values and no-data services behavior remains accepted.

### Task 1: Lock In the Download Primitive Contract

**Files:**
- Create: `backend/tests/test_tiktok_download_helpers.py`
- Test: `backend/tests/test_tiktok_export_component.py`

- [ ] **Step 1: Write failing low-level helper tests**

Add tests for:
- adaptive timeout uses `ctx.config["export_timeout_ms"]` when present
- helper falls back to a longer default timeout when config is absent
- `page` listener miss plus `context` listener hit still yields a download object
- saved file must exist and be non-empty before success is returned

- [ ] **Step 2: Run the focused helper tests to confirm failure**

Run: `python -m pytest backend/tests/test_tiktok_download_helpers.py -q`
Expected: FAIL because the helper module does not exist yet

- [ ] **Step 3: Add one compatibility failure around the current shared exporter timeout**

Extend `backend/tests/test_tiktok_export_component.py` with a case proving the current hard-coded 10s timeout is insufficient when a longer configured timeout is provided.

- [ ] **Step 4: Run the shared exporter tests to confirm the new case fails**

Run: `python -m pytest backend/tests/test_tiktok_export_component.py -q`
Expected: at least one FAIL tied to the configured-timeout case

- [ ] **Step 5: Commit the failing-test baseline**

```bash
git add backend/tests/test_tiktok_download_helpers.py backend/tests/test_tiktok_export_component.py
git commit -m "test: add tiktok export download boundary cases"
```

### Task 2: Implement Shared TikTok Download Primitives

**Files:**
- Create: `modules/platforms/tiktok/components/_download_helpers.py`
- Modify: `modules/platforms/tiktok/components/export.py`
- Test: `backend/tests/test_tiktok_download_helpers.py`
- Test: `backend/tests/test_tiktok_export_component.py`

- [ ] **Step 1: Implement `_download_helpers.py` with stable primitives only**

Add focused helpers for:
- resolving effective export timeout
- arming `page` plus `context` listeners
- wrapping `expect_download`
- cleaning up listeners
- saving to target path
- validating non-empty file output

- [ ] **Step 2: Move only low-level logic out of `export.py`**

Keep `export.py` compiling, but remove embedded ownership of timeout, listener, and save-as mechanics where they can be delegated to the new helper module.

- [ ] **Step 3: Re-run low-level helper tests**

Run: `python -m pytest backend/tests/test_tiktok_download_helpers.py -q`
Expected: PASS

- [ ] **Step 4: Re-run shared exporter compatibility tests**

Run: `python -m pytest backend/tests/test_tiktok_export_component.py -q`
Expected: PASS, including the configured-timeout case

- [ ] **Step 5: Commit the shared primitive layer**

```bash
git add modules/platforms/tiktok/components/_download_helpers.py modules/platforms/tiktok/components/export.py backend/tests/test_tiktok_download_helpers.py backend/tests/test_tiktok_export_component.py
git commit -m "refactor: extract tiktok download primitives"
```

### Task 3: Convert Services Agent to Explicit Export Stages First

**Files:**
- Modify: `modules/platforms/tiktok/components/services_agent_export.py`
- Test: `backend/tests/test_tiktok_services_agent_export_component.py`

- [ ] **Step 1: Add failing services-agent tests for explicit download collection**

Add tests proving:
- `services_agent_export` calls a dedicated download collection stage after a successful trigger
- delayed browser download within configured timeout still succeeds
- no-data success remains unchanged and still bypasses download collection

- [ ] **Step 2: Run services-agent tests to confirm failure**

Run: `python -m pytest backend/tests/test_tiktok_services_agent_export_component.py -q`
Expected: FAIL for the new staged download-collection cases

- [ ] **Step 3: Refactor `services_agent_export.py` to expose explicit stage methods**

Implement or expose:
- `ensure_page_ready`
- `ensure_shop_ready`
- `ensure_date_ready`
- `trigger_export`
- `collect_download_result`

Reuse the current readiness and no-data semantics. Do not rewrite business rules.

- [ ] **Step 4: Re-run services-agent tests**

Run: `python -m pytest backend/tests/test_tiktok_services_agent_export_component.py -q`
Expected: PASS

- [ ] **Step 5: Commit the services-agent stage refactor**

```bash
git add modules/platforms/tiktok/components/services_agent_export.py backend/tests/test_tiktok_services_agent_export_component.py
git commit -m "refactor: stage tiktok services agent export download flow"
```

### Task 4: Convert Products Export to Explicit Export Stages

**Files:**
- Modify: `modules/platforms/tiktok/components/products_export.py`
- Test: `backend/tests/test_tiktok_products_export_component.py`

- [ ] **Step 1: Add failing products export tests for explicit trigger and collection**

Add tests proving:
- products flow waits for domain-specific export readiness before click
- products flow uses a dedicated download collection stage
- delayed download within configured timeout still returns a valid `file_path`

- [ ] **Step 2: Run products export tests to confirm failure**

Run: `python -m pytest backend/tests/test_tiktok_products_export_component.py -q`
Expected: FAIL in the new delayed-download or staged-flow cases

- [ ] **Step 3: Refactor `products_export.py` to stop delegating semantic export behavior to `TiktokExport.run()`**

Keep current page/shop/date flow. Add explicit:
- `trigger_export`
- `collect_download_result`

`collect_download_result` must use `_download_helpers.py` and final file validation.

- [ ] **Step 4: Re-run products export tests**

Run: `python -m pytest backend/tests/test_tiktok_products_export_component.py -q`
Expected: PASS

- [ ] **Step 5: Commit the products export stage refactor**

```bash
git add modules/platforms/tiktok/components/products_export.py backend/tests/test_tiktok_products_export_component.py
git commit -m "refactor: stage tiktok products export download flow"
```

### Task 5: Convert Analytics Export to Explicit Export Stages

**Files:**
- Modify: `modules/platforms/tiktok/components/analytics_export.py`
- Test: `backend/tests/test_tiktok_analytics_export_component.py`

- [ ] **Step 1: Add failing analytics export tests for explicit trigger and collection**

Add tests proving:
- analytics flow waits for domain-specific export readiness before click
- analytics flow uses a dedicated download collection stage
- delayed download within configured timeout still returns a valid `file_path`

- [ ] **Step 2: Run analytics export tests to confirm failure**

Run: `python -m pytest backend/tests/test_tiktok_analytics_export_component.py -q`
Expected: FAIL in the new delayed-download or staged-flow cases

- [ ] **Step 3: Refactor `analytics_export.py` to stop delegating semantic export behavior to `TiktokExport.run()`**

Keep current page/shop/date flow. Add explicit:
- `trigger_export`
- `collect_download_result`

`collect_download_result` must use `_download_helpers.py` and final file validation.

- [ ] **Step 4: Re-run analytics export tests**

Run: `python -m pytest backend/tests/test_tiktok_analytics_export_component.py -q`
Expected: PASS

- [ ] **Step 5: Commit the analytics export stage refactor**

```bash
git add modules/platforms/tiktok/components/analytics_export.py backend/tests/test_tiktok_analytics_export_component.py
git commit -m "refactor: stage tiktok analytics export download flow"
```

### Task 6: Reduce the Shared Exporter to Compatibility-Only Behavior

**Files:**
- Modify: `modules/platforms/tiktok/components/export.py`
- Modify: `backend/tests/test_tiktok_export_component.py`

- [ ] **Step 1: Add a structural regression test**

Add a test proving the top-level TikTok domain components no longer rely on `TiktokExport.run()` as their semantic export implementation path.

- [ ] **Step 2: Run shared export tests to confirm failure**

Run: `python -m pytest backend/tests/test_tiktok_export_component.py -q`
Expected: FAIL for the new structural regression case

- [ ] **Step 3: Reduce `export.py` to compatibility-only behavior**

Make `export.py` retain only:
- primitive compatibility wrappers
- shared metadata helpers if still needed

Remove domain-specific click-chain assumptions from the file.

- [ ] **Step 4: Re-run shared export tests**

Run: `python -m pytest backend/tests/test_tiktok_export_component.py -q`
Expected: PASS

- [ ] **Step 5: Commit the compatibility cleanup**

```bash
git add modules/platforms/tiktok/components/export.py backend/tests/test_tiktok_export_component.py
git commit -m "refactor: reduce tiktok shared exporter to compatibility layer"
```

### Task 7: Verify Gates and Final Targeted Suite

**Files:**
- Modify: `backend/tests/test_component_tester_gate_contract.py`
- Modify: `docs/superpowers/specs/2026-04-12-tiktok-export-download-boundary-design.md` only if implementation requires a documented correction
- Modify: `docs/superpowers/plans/2026-04-12-tiktok-export-download-boundary-refactor.md` to check off completed steps if execution happens in-plan

- [ ] **Step 1: Add gate-level regression coverage**

Add tests proving:
- successful TikTok `products` and `analytics` exports still surface valid `file_path` values accepted by the export gate
- `services_agent` no-data success remains accepted without a file

- [ ] **Step 2: Run gate tests to confirm failure if expectations changed**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
Expected: either FAIL for new cases before fixes or PASS if existing contract already holds

- [ ] **Step 3: Run the full targeted verification set**

Run:
- `python -m pytest backend/tests/test_tiktok_download_helpers.py -q`
- `python -m pytest backend/tests/test_tiktok_export_component.py -q`
- `python -m pytest backend/tests/test_tiktok_products_export_component.py -q`
- `python -m pytest backend/tests/test_tiktok_analytics_export_component.py -q`
- `python -m pytest backend/tests/test_tiktok_services_agent_export_component.py -q`
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`

Expected:
- all targeted tests pass

- [ ] **Step 4: Review the diff for scope discipline**

Run: `git diff -- modules/platforms/tiktok/components backend/tests docs/superpowers/specs/2026-04-12-tiktok-export-download-boundary-design.md docs/superpowers/plans/2026-04-12-tiktok-export-download-boundary-refactor.md`
Expected: only export/download-boundary files changed; navigation, shop-switch, and date-picker behavior is untouched except through existing interfaces

- [ ] **Step 5: Commit the completed refactor**

```bash
git add modules/platforms/tiktok/components backend/tests docs/superpowers/specs/2026-04-12-tiktok-export-download-boundary-design.md docs/superpowers/plans/2026-04-12-tiktok-export-download-boundary-refactor.md
git commit -m "refactor: split tiktok export download semantics by component"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-12-tiktok-export-download-boundary-refactor.md`. Ready to execute?
