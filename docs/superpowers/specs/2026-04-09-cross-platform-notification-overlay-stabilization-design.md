# Cross-Platform Notification Overlay Stabilization Design

**Date:** 2026-04-09

**Goal:** Add a cross-platform "page stabilization" capability for post-login and post-navigation notification overlays so canonical collection components can continue working when sites show non-business announcement dialogs after the page has already loaded.

## 1. Background

Collection failures are increasingly caused by platform-side notice dialogs that appear after login succeeds or after the homepage / target page finishes rendering.

These dialogs are not part of the collection business flow:

- activity notices
- announcement popups
- new-feature prompts
- marketing notices
- message-center reminders

They have three important properties:

1. They are not deterministic. The same page may or may not show them.
2. The text and image content changes frequently.
3. The close interaction is usually structurally stable even when the content changes.

The current repository already has some popup-related building blocks:

- shared popup closing engine: `modules/apps/collection_center/popup_handler.py`
- per-platform popup config modules:
  - `modules/platforms/shopee/popup_config.py`
  - `modules/platforms/tiktok/popup_config.py`
  - `modules/platforms/miaoshou/popup_config.py`
- Miaoshou-specific overlay helper: `modules/platforms/miaoshou/components/overlay_guard.py`

However, these pieces do not yet form a formal cross-platform stabilization path used consistently by canonical `login`, `navigation`, and `export` components.

## 2. Evidence

### 2.1 Component Test Failure Artifacts

The repository already defines a component-test failure artifact contract:

- `temp/component_tests/<test_id>/config.json`
- `temp/component_tests/<test_id>/progress.json`
- `temp/component_tests/<test_id>/result.json`
- `temp/component_tests/<test_id>/<failure>.json`
- `temp/component_tests/<test_id>/<failure>.html`
- `temp/component_tests/<test_id>/<failure>.txt`
- `temp/test_results/<latest-error>.png`

This is not hypothetical. For the recent Miaoshou orders failure:

- screenshot:
  - `temp/test_results/orders_shopee_export_error_20260409_205825.png`
- structure artifacts:
  - `temp/component_tests/test_3d80a41b44a1/orders_shopee_export_python_component_1_20260409_205826.json`
  - `temp/component_tests/test_3d80a41b44a1/orders_shopee_export_python_component_1_20260409_205826.html`
  - `temp/component_tests/test_3d80a41b44a1/orders_shopee_export_python_component_1_20260409_205826.txt`

The failure was not "download never works" in the abstract. The failure log explicitly shows pointer interception by an overlay dialog:

- `jx-overlay`
- `jx-overlay-dialog`
- `notice-message-box-dialog`
- close button structure under `.jx-dialog__headerbtn`

### 2.2 pwcli Evidence

The repository also preserves page-structure evidence under `output/playwright/work/...`.

Relevant Miaoshou evidence exists here:

- `output/playwright/work/miaoshou/orders-shopee/`
- `output/playwright/work/miaoshou/inventory-checklist/`

This means the repository already has the right evidence loop:

- formal component-test failure artifacts for "what failed now"
- pwcli snapshots/screenshots for "what the page structure looks like under controlled exploration"

## 3. Problem Statement

The current runtime treats transient post-login / post-navigation notice overlays as a local component problem, but the failure mode is actually cross-platform and page-lifecycle-specific.

This causes three issues:

1. Logic duplication
   - individual components add local popup cleanup ad hoc
   - behavior diverges across login / navigation / export

2. Wrong abstraction boundary
   - a page-level stabilization concern is handled inside feature-level export logic

3. Incomplete diagnosis loop
   - failures are observable, but there is no formal rule saying the platform popup config must be updated from failure structure artifacts / pwcli evidence

## 4. Design Goals

1. Introduce a single cross-platform stabilization model for safe notification overlays.
2. Keep the shared engine generic, but keep notice-identification rules platform-specific.
3. Use structural selectors, not mutable text or image content, to detect removable notice dialogs.
4. Run stabilization at the correct lifecycle boundaries:
   - after login success
   - after navigation success
   - before the first critical interaction
   - after pointer-intercept failures
5. Preserve safety:
   - never auto-close business-critical dialogs such as captcha, export confirmation, permission prompts, or risk dialogs
6. Keep the evidence loop explicit:
   - component test failure artifacts drive rule updates
   - pwcli snapshots confirm real page structure before rule changes

## 5. Non-Goals

1. Do not build a universal "close any dialog" system.
2. Do not use dialog title text, notice message text, or image URLs as the primary detection rule.
3. Do not replace component tests with pwcli.
4. Do not treat database / schema drift as the root cause of these overlay failures.
5. Do not move popup logic into every export component independently.

## 6. Recommended Architecture

The recommended design is:

- shared popup engine in `modules/apps/collection_center/popup_handler.py`
- per-platform safe-notice rules in `modules/platforms/<platform>/popup_config.py`
- lifecycle integration in canonical platform components:
  - `login.py`
  - `navigation.py`
  - selective lightweight fallback in `export` components

This keeps responsibilities clear:

- shared layer decides **how** to observe and close
- platform layer decides **what is safe to close**
- components decide **when stabilization should run**

## 7. Functional Model

### 7.1 Safe Notice Overlay

A dialog qualifies as a safe auto-close target only when it is informational and non-business-critical.

Examples:

- announcement popup
- activity notice
- marketing prompt
- new-feature reminder
- message-center notice

Examples that are explicitly excluded:

- captcha dialog
- OTP / manual verification dialog
- export confirmation dialog
- login confirmation dialog
- permission / authorization dialog
- destructive confirmation dialog

### 7.2 Stabilization Phases

Introduce four formal stabilization triggers:

1. `post_login`
   - after login success signal is reached
   - before handing control to navigation / export

2. `post_navigation`
   - after target page is judged ready
   - before the first feature interaction

3. `before_first_action`
   - just before the first critical input / click on the page

4. `on_intercept_retry`
   - when Playwright reports pointer interception or overlay blocking

### 7.3 Platform Rule Sources

Each platform popup config should define only structurally stable rules, such as:

- root dialog classes
- overlay classes
- close-button selectors
- footer dismiss-button selectors
- exclusion selectors for critical dialogs
- poll strategy overrides

The platform rule file must not depend on:

- full notice title text
- image URLs
- campaign copy
- exact marketing body text

## 8. File-Level Design

### 8.1 Shared Engine

File:

- `modules/apps/collection_center/popup_handler.py`

Extend the existing shared engine with a safe-notice mode.

Recommended additions:

- explicit mode separation:
  - `safe_notice_only`
  - `generic_component_cleanup`
- support for exclusion selectors
- support for platform-specific rule groups rather than only raw selector concatenation
- helper that recognizes pointer-intercept failures and re-runs stabilization in a bounded retry path

The shared engine remains cross-platform and must not hardcode Miaoshou / Shopee / TikTok business assumptions.

### 8.2 Platform Popup Config

Files:

- `modules/platforms/shopee/popup_config.py`
- `modules/platforms/tiktok/popup_config.py`
- `modules/platforms/miaoshou/popup_config.py`

These should become the single source of truth for platform-safe notice rules.

Recommended logical shape:

- `get_safe_notice_close_selectors()`
- `get_safe_notice_overlay_selectors()`
- `get_safe_notice_exclusion_selectors()`
- `get_poll_strategy()`

The exact function names may be adapted to fit the current handler API, but the semantics should remain explicit.

### 8.3 Lifecycle Integration

Primary integration points:

- `modules/platforms/<platform>/components/login.py`
- `modules/platforms/<platform>/components/navigation.py`

Design rule:

- login handles stabilization immediately after login success
- navigation handles stabilization immediately after page-ready detection
- export only does a lightweight recheck before the first critical interaction

This keeps the main responsibility at the page lifecycle layer instead of duplicating cleanup deep inside feature components.

### 8.4 Miaoshou Transitional Wrapper

File:

- `modules/platforms/miaoshou/components/overlay_guard.py`

This helper already exists. It should either:

- be refactored into a thin Miaoshou adapter around the shared popup engine
or
- be retired after the shared handler + popup config path fully replaces it

The repository should not keep two independent Miaoshou popup systems long term.

## 9. Artifact and Evidence Rules

### 9.1 Component Test Failures

When a component test fails due to overlay interference, the rule update workflow must begin from:

- `temp/component_tests/<test_id>/result.json`
- `temp/component_tests/<test_id>/<failure>.json`
- `temp/component_tests/<test_id>/<failure>.html`
- `temp/component_tests/<test_id>/<failure>.txt`
- `temp/test_results/<latest-error>.png`

These files answer:

- what component failed
- in which phase it failed
- what the final DOM looked like
- what the final visible text summary looked like
- what the final screenshot looked like

### 9.2 pwcli Confirmation

If component failure artifacts are insufficient, use `pwcli` to reproduce only the failed phase and preserve:

- before snapshot
- after snapshot
- optional note
- screenshot when needed

The preferred work directory remains:

- `output/playwright/work/<platform>/<tag>/`

### 9.3 Rule-Update Gate

A platform popup rule should be added or changed only when one of these is true:

1. failure artifact HTML proves a stable overlay structure
2. pwcli evidence proves the same structure under controlled reproduction

This prevents speculative selector accumulation.

## 10. Safety Model

Auto-close is allowed only for dialogs that satisfy both:

1. the platform marks them as safe notice overlays
2. they do not match exclusion selectors for critical dialogs

If the handler cannot confidently classify a dialog as safe, it must do nothing.

The system should prefer a missed cleanup over accidentally dismissing a business-critical dialog.

## 11. Testing Strategy

### 11.1 Contract Tests

Add or extend tests that verify:

- failure artifact files are still written
- platform popup config returns explicit safe-notice rules
- shared handler honors exclusion selectors

### 11.2 Platform-Specific Regression Tests

For each platform, add at least one regression test proving:

- post-login / post-navigation stabilization is invoked
- pointer-intercept retry path re-runs safe notice cleanup

### 11.3 Evidence-Driven Regression

For a newly discovered platform notice type:

1. preserve the failure artifact set
2. optionally preserve pwcli evidence
3. add the platform rule
4. add a regression test tied to the discovered structure pattern

## 12. Rollout Plan

Recommended rollout order:

1. Miaoshou
   - already has confirmed overlay evidence
2. Shopee
   - add platform popup rules when failures are reproduced
3. TikTok
   - add platform popup rules when failures are reproduced

Do not try to perfect all platforms before shipping the framework.

Ship the shared architecture first, then evolve per-platform rules from real evidence.

## 13. Risks

### 13.1 Overbroad Selectors

Risk:

- dismissing business-critical dialogs by mistake

Mitigation:

- use platform-specific safe-notice rules
- require exclusion selectors
- avoid title-text-based matching

### 13.2 Rule Explosion

Risk:

- accumulating too many one-off selectors

Mitigation:

- only add rules from failure artifacts / pwcli evidence
- prefer structural roots over page-copy fragments
- regularly consolidate duplicate selectors

### 13.3 Logic Duplication

Risk:

- popup cleanup implemented separately in login / navigation / export

Mitigation:

- shared engine for behavior
- platform config for rules
- lifecycle ownership defined explicitly

## 14. Recommendation

Implement a cross-platform page stabilization path based on:

- shared popup-closing engine
- platform-specific safe-notice rule modules
- lifecycle-triggered stabilization in `login` and `navigation`
- lightweight export fallback
- evidence-driven rule updates from component-test failure artifacts and pwcli snapshots

This approach is preferred because it:

- matches the real failure mode
- avoids over-general global behavior
- avoids per-component duplication
- scales to multiple platforms without depending on mutable notice text
