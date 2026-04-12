# Shopee Export Component Boundary Refactor Design

**Date:** 2026-04-12

## Goal

Stabilize Shopee collection exports by replacing the current misleading inheritance-heavy export shape with domain-specific top-level components, explicit download-completion modes, and a small shared primitive layer that agents can understand and modify safely.

## Problem Statement

The current Shopee export runtime over-reuses [`products_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/products_export.py) as the effective semantic parent for other Shopee export components. This creates two concrete problems:

1. `analytics` and `services_ai_assistant` inherit a completion model that does not match their real download behavior.
2. Humans and agents both read the inheritance tree as evidence that these domains should behave similarly, so fixes keep being applied in the wrong abstraction layer.

This is a stability problem and a maintainability problem at the same time. Stable collection cannot be sustained if the code structure keeps steering future work toward the wrong assumptions.

## Constraints

- Preserve the repository rule that Shopee export work should reuse stable patterns from the current canonical runtime rather than restoring `archive/` code.
- Keep final export success aligned with the repository gate contract: file exists and is non-empty.
- Make component boundaries more understandable for agent-driven development.
- Avoid introducing a new “universal Shopee exporter” abstraction.

## Observed Download Models

Current live behavior indicates that Shopee exports do not all complete through the same runtime shape.

### Task-row download

Observed strongest on `services_agent`.

Likely sequence:

1. Click export.
2. Server creates or updates a report row.
3. UI shows report progress.
4. Row exposes a download action.
5. Clicking that row’s download action triggers the real browser download.

### Direct download

Observed strongest on `analytics` and `services_ai_assistant`.

Likely sequence:

1. Click export.
2. Browser download starts directly.
3. Browser-level download manager shows completion.
4. Runtime may miss the Playwright `download` object if the listener shape is wrong, even though the file is already on disk.

The key design implication is that “all exports involve clicking buttons” does not mean “all exports share one completion model.”

## Options Considered

### Option A: Keep the current shared inheritance chain and add more strategy branches

This keeps change scope small, but it preserves the main source of confusion: other components still look like variants of `products_export`.

Trade-offs:

- Lowest short-term code churn
- Highest long-term misunderstanding risk
- Encourages future fixes in the wrong parent class
- Makes agent reasoning worse as special cases accumulate

### Option B: Fully separate each Shopee export component into independent implementations

This maximizes isolation, but it duplicates stable logic such as standardized output handling, file validation, and download reconciliation.

Trade-offs:

- Strongest isolation
- Highest maintenance cost
- High risk of drift between components
- Harder to apply cross-cutting fixes consistently

### Option C: Domain-specific top-level components plus shared low-level primitives

Each export domain owns its page flow and completion model. Shared logic is limited to primitives that do not carry misleading business semantics.

Trade-offs:

- Best balance of stability and maintainability
- Matches the effective TikTok shape already used in the repo
- Improves agent comprehension by making domain boundaries explicit
- Requires moderate refactor, but with clear end-state

**Recommendation:** Option C.

## Target Architecture

## Top-Level Components

Keep one explicit top-level component per Shopee export domain:

- `shopee/products_export`
- `shopee/analytics_export`
- `shopee/services_agent_export`
- `shopee/services_ai_assistant_export`

These components should no longer be interpreted as thin behavioral variants of `products_export`.

## Shared Layer

Create or retain only a small shared primitive layer for logic that is stable across domains.

Allowed shared primitives:

- standard output path construction
- download event helper wrappers
- browser-context-level download fallback wiring
- download-directory time-window reconciliation
- file existence and non-empty validation
- common diagnostic logging
- shared date-summary verification helpers
- shared shop selection helpers when the semantics are truly the same

Disallowed shared semantics:

- one universal “latest report” abstraction
- one universal export-trigger/completion state machine
- one universal retry policy
- one universal assumption about whether export click or report-row click triggers the real download

## Explicit Stage Contract

Every Shopee top-level export component should implement the same stage names so humans and agents can reason uniformly:

1. `ensure_page_ready`
2. `ensure_shop_ready`
3. `ensure_date_ready`
4. `trigger_export`
5. `collect_download_result`

The method names are intentionally uniform. The method internals are domain-specific.

## Explicit Download Mode

Each component must declare its primary completion model explicitly instead of implying it through inheritance.

Proposed modes:

- `DIRECT_DOWNLOAD`
- `TASK_ROW_DOWNLOAD`

Initial mapping:

- `analytics`: `DIRECT_DOWNLOAD`
- `services_ai_assistant`: `DIRECT_DOWNLOAD`
- `services_agent`: `TASK_ROW_DOWNLOAD`
- `products`: keep explicit in component based on current stable evidence, but do not expose it as a parent semantic model for other domains

This removes guesswork for future agents. They no longer need to infer completion behavior from inheritance.

## Success And Retry Rules

## Final Success Rule

Final export success remains:

- file path returned
- file exists
- file is non-empty

Playwright event capture is a supporting mechanism, not the source of truth.

## Retry Rule

Retry is allowed only when both conditions are true:

1. no valid download event was captured for the active export path
2. no new matching file appeared in the download reconciliation window

If a file appears on disk and passes validation, the component must stop and return success even if the in-memory Playwright `download` object was not captured.

This directly addresses the current failure mode where the browser visibly completes the download but the runtime continues into retry behavior.

## Component Responsibilities

### `analytics_export`

- Own page-ready detection for Shopee analytics
- Treat direct browser download as the primary completion path
- Use report-row UI only as a fallback or supporting signal if needed
- Never depend on a products-style task-row assumption as the primary success path

### `services_ai_assistant_export`

- Own page-ready detection for Shopee AI assistant service export
- Treat direct browser download as the primary completion path
- Avoid blocking on “latest report top row download button” before consuming an already-started download event
- Use file reconciliation before any retry

### `services_agent_export`

- Keep task-row completion as the primary model
- Wait for report-row readiness, then trigger the row-level download
- Still use the same final file validation and reconciliation primitives as other domains

### `products_export`

- Remain valid as the products-domain runtime
- Stop serving as the semantic parent for analytics and services domains
- Share only low-level helpers outward, not business completion assumptions

## File Boundary Recommendation

Recommended structure:

- [`modules/platforms/shopee/components/products_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/products_export.py)
- [`modules/platforms/shopee/components/analytics_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/analytics_export.py)
- [`modules/platforms/shopee/components/services_agent_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/services_agent_export.py)
- [`modules/platforms/shopee/components/services_ai_assistant_export.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/services_ai_assistant_export.py)
- [`modules/platforms/shopee/components/_download_helpers.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/_download_helpers.py)
- [`modules/platforms/shopee/components/_date_helpers.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/_date_helpers.py)
- [`modules/platforms/shopee/components/_shop_helpers.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/platforms/shopee/components/_shop_helpers.py)

If existing helpers already cover some of these roles, reuse rather than duplicate. The design goal is boundary clarity, not helper proliferation.

## Why This Is More Agent-Friendly

This design deliberately optimizes for correct modification by agentic workers.

An agent reading the new shape should be able to answer these questions without reading unrelated domains:

- Which page flow does this component own?
- What is the completion model for this export?
- Where does retry decision happen?
- Where is final file success validated?
- Which shared helper is safe to reuse without changing business semantics?

The current inheritance-heavy shape fails this test. The recommended structure passes it.

## Testing Strategy

Required regression coverage:

1. `analytics` succeeds when direct download event is captured normally
2. `analytics` succeeds when event capture is missed but a new non-empty file appears in the reconciliation window
3. `services_ai_assistant` succeeds under the same direct-download-plus-reconcile shape
4. `services_agent` still succeeds with task-row download
5. retry is suppressed when a valid file already exists
6. retry still occurs when neither event nor file appears
7. component tester / transition gate still accept the returned `file_path` as the final success signal

## Migration Strategy

Refactor in this order:

1. Introduce or normalize shared download/file primitives
2. Move `analytics` to an explicit direct-download completion path
3. Move `services_ai_assistant` to the same direct-download completion path
4. Keep `services_agent` task-row behavior but convert it to shared primitive usage
5. Remove semantic reuse of `products_export` by other Shopee domains
6. Update regression tests and component-gate coverage

## Final Recommendation

For stable Shopee collection and reliable agent-driven maintenance:

- do not continue expanding the current shared inheritance tree
- do not fully duplicate each component into isolated scripts
- adopt domain-specific top-level components with explicit completion modes and a minimal shared primitive layer

This is the smallest change that improves both runtime stability and future correctness of agent-made modifications.
