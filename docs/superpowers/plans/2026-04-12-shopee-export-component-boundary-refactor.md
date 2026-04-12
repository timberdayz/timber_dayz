# Shopee Export Component Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Shopee export components so each domain owns its completion model while sharing only stable low-level primitives, improving both collection stability and agent comprehension.

**Architecture:** Convert Shopee export components from inheritance-led semantics to domain-led top-level implementations with uniform stage methods. Centralize only download/file reconciliation primitives and keep direct-download versus task-row behavior explicit inside each component.

**Tech Stack:** Python, Playwright async runtime, existing `ExecutionContext` / `ExportResult` contracts, pytest unit tests, collection transition gates.

---

### Task 1: Define Shared Download Primitive Boundary

**Files:**
- Create: `modules/platforms/shopee/components/_download_helpers.py`
- Modify: `modules/platforms/shopee/components/analytics_export.py`
- Modify: `modules/platforms/shopee/components/services_agent_export.py`
- Modify: `modules/platforms/shopee/components/services_ai_assistant_export.py`
- Test: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Write failing tests for direct-download reconciliation**

Add tests proving a component returns success when:
- download event is captured directly
- download event is missed but a new non-empty file appears in the expected reconciliation window

- [ ] **Step 2: Run the new targeted tests and confirm failure**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -q`
Expected: failures for the new direct-download reconciliation cases

- [ ] **Step 3: Implement `_download_helpers.py`**

Add focused helpers for:
- `expect_download` wrapping
- optional context-level listener fallback
- download-directory time-window reconciliation
- file existence and non-empty validation

- [ ] **Step 4: Wire `analytics` and `services_ai_assistant` to the shared helper**

Keep this step minimal. Do not refactor unrelated page logic here.

- [ ] **Step 5: Re-run the targeted tests**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -q`
Expected: new reconciliation tests pass

### Task 2: Make Shopee Analytics Own a Direct-Download Completion Model

**Files:**
- Modify: `modules/platforms/shopee/components/analytics_export.py`
- Test: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Add failing analytics-specific tests**

Add tests that prove:
- `analytics` treats export click as primary download trigger
- `analytics` suppresses retry if file reconciliation already succeeded

- [ ] **Step 2: Run the analytics-focused tests and confirm failure**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k analytics -q`
Expected: at least one new analytics-specific failure

- [ ] **Step 3: Refactor `analytics_export.py` into explicit stage methods**

Implement or expose:
- `ensure_page_ready`
- `ensure_shop_ready`
- `ensure_date_ready`
- `trigger_export`
- `collect_download_result`

`collect_download_result` must prefer direct-download capture and then file reconciliation.

- [ ] **Step 4: Re-run analytics-focused tests**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k analytics -q`
Expected: analytics tests pass

### Task 3: Make Shopee Services AI Assistant Own a Direct-Download Completion Model

**Files:**
- Modify: `modules/platforms/shopee/components/services_ai_assistant_export.py`
- Modify: `modules/platforms/shopee/components/services_export_base.py`
- Test: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Add failing AI-assistant-specific tests**

Add tests proving:
- already-started direct download is consumed before waiting on report-row UI
- file reconciliation prevents duplicate export retry

- [ ] **Step 2: Run the AI-assistant-focused tests and confirm failure**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k ai_assistant -q`
Expected: at least one failure tied to the new AI assistant completion path

- [ ] **Step 3: Reduce `services_export_base.py` to stable shared behavior only**

Remove assumptions that all services exports are task-row downloads. Keep only helpers that are truly shared.

- [ ] **Step 4: Make `services_ai_assistant_export.py` own its completion strategy**

Its `collect_download_result` must use direct-download-first behavior.

- [ ] **Step 5: Re-run AI-assistant-focused tests**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k ai_assistant -q`
Expected: AI assistant tests pass

### Task 4: Preserve Services Agent as Task-Row Download Without Shared Semantic Leakage

**Files:**
- Modify: `modules/platforms/shopee/components/services_agent_export.py`
- Modify: `modules/platforms/shopee/components/services_export_base.py`
- Test: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Add failing regression tests for services agent**

Add coverage proving:
- task-row detection still works
- row-level download remains the primary trigger
- final file reconciliation still confirms success if needed

- [ ] **Step 2: Run services-agent-focused tests and confirm failure where expected**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k services_agent -q`
Expected: failures in any new cases added for reconciled task-row behavior

- [ ] **Step 3: Make `services_agent_export.py` explicit about its task-row mode**

Do not rely on inherited products semantics. Keep the domain flow visible in the component file.

- [ ] **Step 4: Re-run services-agent-focused tests**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -k services_agent -q`
Expected: services agent tests pass

### Task 5: Remove Products Export as Semantic Parent for Other Shopee Domains

**Files:**
- Modify: `modules/platforms/shopee/components/products_export.py`
- Modify: `modules/platforms/shopee/components/analytics_export.py`
- Modify: `modules/platforms/shopee/components/services_agent_export.py`
- Modify: `modules/platforms/shopee/components/services_ai_assistant_export.py`
- Test: `tests/unit/test_shopee_products_export.py`

- [ ] **Step 1: Write a structural regression test**

Add a test or lightweight assertion proving other Shopee domains no longer rely on `products_export` as their semantic implementation parent.

- [ ] **Step 2: Run the structural regression test and confirm failure**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -q`
Expected: failure before the inheritance boundary is removed

- [ ] **Step 3: Refactor imports and class boundaries**

Make each Shopee top-level component own its domain behavior and depend only on helper modules or shared stable utilities.

- [ ] **Step 4: Re-run the full Shopee export unit suite**

Run: `python -m pytest tests/unit/test_shopee_products_export.py -q`
Expected: all Shopee export unit tests pass

### Task 6: Verify Component Tester and Transition Gates Still Accept the Refactored Outputs

**Files:**
- Modify: `backend/tests/test_component_tester_gate_contract.py`
- Modify: `modules/apps/collection_center/transition_gates.py` only if required
- Test: `backend/tests/test_component_tester_gate_contract.py`

- [ ] **Step 1: Add failing gate-level coverage for reconciled success**

Add coverage proving the export gate still accepts a component result when the component now succeeds through file reconciliation rather than direct event capture.

- [ ] **Step 2: Run the gate tests and confirm failure**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
Expected: new gate case fails before code or fixture updates

- [ ] **Step 3: Update gate-facing expectations if needed**

Prefer not to change the gate contract. The component should still return a valid `file_path`.

- [ ] **Step 4: Re-run the gate tests**

Run: `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
Expected: all gate tests pass

### Task 7: Final Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-12-shopee-export-component-boundary-refactor-design.md` only if implementation reality requires a documented correction
- Modify: `docs/superpowers/plans/2026-04-12-shopee-export-component-boundary-refactor.md` to check off completed tasks if executed in-plan

- [ ] **Step 1: Run the full targeted verification set**

Run:
- `python -m pytest tests/unit/test_shopee_products_export.py -q`
- `python -m pytest backend/tests/test_component_tester_gate_contract.py -q`
- `python -m pytest modules/apps/shopee/analytics_contract_tests.py modules/apps/shopee/services_contract_tests.py -q`

Expected:
- all targeted tests pass

- [ ] **Step 2: Review diff for boundary clarity**

Run: `git diff -- modules/platforms/shopee/components tests/unit/test_shopee_products_export.py backend/tests/test_component_tester_gate_contract.py docs/superpowers/specs/2026-04-12-shopee-export-component-boundary-refactor-design.md docs/superpowers/plans/2026-04-12-shopee-export-component-boundary-refactor.md`
Expected: Shopee domain behavior is explicit in each top-level component and shared helpers contain only low-level primitives

- [ ] **Step 3: Commit**

```bash
git add modules/platforms/shopee/components tests/unit/test_shopee_products_export.py backend/tests/test_component_tester_gate_contract.py docs/superpowers/specs/2026-04-12-shopee-export-component-boundary-refactor-design.md docs/superpowers/plans/2026-04-12-shopee-export-component-boundary-refactor.md
git commit -m "refactor: split shopee export completion models by domain"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-12-shopee-export-component-boundary-refactor.md`. Ready to execute?
