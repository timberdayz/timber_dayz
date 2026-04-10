# Cross-Platform Notification Overlay Stabilization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a shared, platform-configurable safe-notice stabilization path so canonical collection components can automatically dismiss post-login and post-navigation announcement overlays without relying on mutable notice text.

**Architecture:** Keep the popup-closing behavior in the shared `UniversalPopupHandler`, but move platform-specific "what is safe to close" rules into `modules/platforms/<platform>/popup_config.py`. Integrate the new safe-notice stabilization hook into canonical login components across platforms, add post-navigation stabilization for Miaoshou, and add a lightweight pre-first-action cleanup in Miaoshou orders export where the current failure occurs.

**Tech Stack:** Python, Playwright async API, canonical collection components under `modules/platforms/`, shared executor utilities under `modules/apps/collection_center/`, pytest

---

## File Structure

### Existing files to modify

- `modules/apps/collection_center/popup_handler.py`
  Responsibility: add a safe-notice-only stabilization mode, support platform exclusion selectors, and preserve the current generic popup behavior for existing callers.
- `modules/components/base.py`
  Responsibility: add a runtime-safe component helper that invokes safe-notice stabilization without requiring test mode.
- `modules/platforms/miaoshou/popup_config.py`
  Responsibility: define the first real safe-notice structural rules from the confirmed Miaoshou failure artifacts.
- `modules/platforms/shopee/popup_config.py`
  Responsibility: expose the new popup-config interface even if Shopee starts with empty rule sets.
- `modules/platforms/tiktok/popup_config.py`
  Responsibility: expose the new popup-config interface even if TikTok starts with empty rule sets.
- `modules/platforms/miaoshou/components/login.py`
  Responsibility: switch post-login cleanup onto the shared safe-notice hook.
- `modules/platforms/shopee/components/login.py`
  Responsibility: wire post-login cleanup into the shared safe-notice hook.
- `modules/platforms/tiktok/components/login.py`
  Responsibility: wire post-login cleanup into the shared safe-notice hook.
- `modules/platforms/miaoshou/components/navigation.py`
  Responsibility: perform post-navigation stabilization after the orders / warehouse page is considered ready.
- `modules/platforms/miaoshou/components/orders_export_base.py`
  Responsibility: perform a lightweight pre-first-action stabilization before the first interactive date/search/export sequence.
- `modules/platforms/miaoshou/components/overlay_guard.py`
  Responsibility: either delegate to the shared handler or remain as a thin compatibility wrapper instead of an independent Miaoshou-only popup system.
- `backend/tests/test_miaoshou_login_component.py`
  Responsibility: update login cleanup expectations to the new shared hook behavior.

### New files to create

- `backend/tests/test_popup_handler_safe_notice.py`
  Responsibility: verify safe-notice selector loading, exclusion behavior, and no-op behavior for platforms with empty rules.
- `backend/tests/test_cross_platform_login_overlay_cleanup.py`
  Responsibility: verify Shopee, TikTok, and Miaoshou login components all invoke the shared stabilization path after login success.
- `backend/tests/test_miaoshou_navigation_overlay_cleanup.py`
  Responsibility: verify Miaoshou navigation stabilizes the page after the target view becomes ready.
- `backend/tests/test_miaoshou_orders_overlay_cleanup.py`
  Responsibility: verify Miaoshou orders export performs a pre-first-action stabilization before interacting with page controls.

---

### Task 1: Add Failing Tests For Safe-Notice Popup Rules

**Files:**
- Create: `backend/tests/test_popup_handler_safe_notice.py`
- Create: `backend/tests/test_cross_platform_login_overlay_cleanup.py`
- Create: `backend/tests/test_miaoshou_navigation_overlay_cleanup.py`
- Create: `backend/tests/test_miaoshou_orders_overlay_cleanup.py`
- Modify: `backend/tests/test_miaoshou_login_component.py`

- [ ] **Step 1: Write the failing shared handler contract test**

Add tests that prove:
- `UniversalPopupHandler` can load platform safe-notice selectors separately from generic selectors
- exclusion selectors prevent closing critical dialogs
- empty Shopee/TikTok rule sets are valid and do not raise errors

- [ ] **Step 2: Run the shared handler test to verify it fails**

Run:

```bash
python -m pytest backend/tests/test_popup_handler_safe_notice.py -q
```

Expected: FAIL because the current popup handler has no safe-notice-only mode or exclusion-rule contract.

- [ ] **Step 3: Write failing login cleanup tests across the three platforms**

Add tests that prove:
- `miaoshou/login.py` uses the shared stabilization path
- `shopee/login.py` uses the shared stabilization path
- `tiktok/login.py` uses the shared stabilization path

- [ ] **Step 4: Run the login cleanup tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py -q
```

Expected: FAIL because only Miaoshou currently does custom cleanup and Shopee/TikTok still no-op.

- [ ] **Step 5: Write failing Miaoshou navigation and orders cleanup tests**

Add tests that prove:
- `miaoshou/navigation.py` stabilizes after target-page ready
- `miaoshou/orders_export_base.py` stabilizes before the first critical interactive action

- [ ] **Step 6: Run the Miaoshou cleanup tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py -q
```

Expected: FAIL because navigation currently has no stabilization step and orders export still uses only local popup-close loops.

- [ ] **Step 7: Commit the red tests**

```bash
git add backend/tests/test_popup_handler_safe_notice.py backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py
git commit -m "test: add failing overlay stabilization coverage"
```

---

### Task 2: Implement Shared Safe-Notice Handling And Platform Rule Contracts

**Files:**
- Modify: `modules/apps/collection_center/popup_handler.py`
- Modify: `modules/platforms/miaoshou/popup_config.py`
- Modify: `modules/platforms/shopee/popup_config.py`
- Modify: `modules/platforms/tiktok/popup_config.py`
- Test: `backend/tests/test_popup_handler_safe_notice.py`

- [ ] **Step 1: Extend the popup-config contract**

Implement explicit platform rule functions:

```python
def get_safe_notice_close_selectors() -> list[str]: ...
def get_safe_notice_overlay_selectors() -> list[str]: ...
def get_safe_notice_exclusion_selectors() -> list[str]: ...
def get_poll_strategy() -> dict[str, Any]: ...
```

Use empty lists for Shopee/TikTok initially.

- [ ] **Step 2: Encode Miaoshou's confirmed safe-notice structure**

In `modules/platforms/miaoshou/popup_config.py`, add selectors derived from the failure artifacts:

```python
SAFE_NOTICE_CLOSE_SELECTORS = [
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    ".notice-message-box-dialog button[aria-label='关闭此对话框']",
]
SAFE_NOTICE_OVERLAY_SELECTORS = [
    ".jx-overlay:has(.notice-message-box-dialog)",
    ".jx-overlay-dialog",
]
SAFE_NOTICE_EXCLUSION_SELECTORS = [
    ".captcha",
    "[data-nc-idx]",
    "input[autocomplete='one-time-code']",
]
```

Adapt exact selectors if needed, but keep them structural and not title-text-based.

- [ ] **Step 3: Add a safe-notice-only mode to `UniversalPopupHandler`**

Implement a shared API shaped like:

```python
async def close_safe_notices(self, page, platform: str | None = None, ...) -> int: ...
```

Behavior requirements:
- only use platform safe-notice selectors
- skip any visible match under exclusion selectors
- leave existing `close_popups()` behavior intact for current executor callers

- [ ] **Step 4: Run the shared handler tests**

Run:

```bash
python -m pytest backend/tests/test_popup_handler_safe_notice.py -q
```

Expected: PASS

- [ ] **Step 5: Commit the shared handler and config contract**

```bash
git add modules/apps/collection_center/popup_handler.py modules/platforms/miaoshou/popup_config.py modules/platforms/shopee/popup_config.py modules/platforms/tiktok/popup_config.py backend/tests/test_popup_handler_safe_notice.py
git commit -m "feat: add shared safe-notice popup handling"
```

---

### Task 3: Add Runtime Stabilization Hooks To Canonical Components

**Files:**
- Modify: `modules/components/base.py`
- Modify: `modules/platforms/miaoshou/components/login.py`
- Modify: `modules/platforms/shopee/components/login.py`
- Modify: `modules/platforms/tiktok/components/login.py`
- Modify: `modules/platforms/miaoshou/components/navigation.py`
- Modify: `modules/platforms/miaoshou/components/orders_export_base.py`
- Modify: `modules/platforms/miaoshou/components/overlay_guard.py`
- Test: `backend/tests/test_cross_platform_login_overlay_cleanup.py`
- Test: `backend/tests/test_miaoshou_navigation_overlay_cleanup.py`
- Test: `backend/tests/test_miaoshou_orders_overlay_cleanup.py`
- Test: `backend/tests/test_miaoshou_login_component.py`

- [ ] **Step 1: Add a shared component-level stabilization helper**

In `modules/components/base.py`, add a helper shaped like:

```python
async def stabilize_safe_notices(self, page: Any, *, label: str | None = None) -> int:
    ...
```

Requirements:
- not gated by `ctx.is_test_mode`
- uses `UniversalPopupHandler.close_safe_notices(...)`
- logs but never raises on cleanup failures

- [ ] **Step 2: Switch all canonical login post-success cleanup hooks to the shared helper**

Update:
- `modules/platforms/miaoshou/components/login.py`
- `modules/platforms/shopee/components/login.py`
- `modules/platforms/tiktok/components/login.py`

Target pattern:

```python
async def _cleanup_after_login(self, page: Any) -> None:
    await self.stabilize_safe_notices(page, label="post-login cleanup")
```

- [ ] **Step 3: Add post-navigation stabilization to Miaoshou**

In `modules/platforms/miaoshou/components/navigation.py`, after the target page-ready signal succeeds, call:

```python
await self.stabilize_safe_notices(page, label="post-navigation cleanup")
```

Do this for both orders and warehouse navigation branches.

- [ ] **Step 4: Add a lightweight pre-first-action stabilization to Miaoshou orders export**

In `modules/platforms/miaoshou/components/orders_export_base.py`, run a bounded cleanup before interacting with the first critical control sequence on the page.

Keep this narrow:
- after navigation success
- before subtype selection / date input / search/export flow starts

Do not add broad retry trees from the archived exporter.

- [ ] **Step 5: Collapse `overlay_guard.py` into a compatibility wrapper**

Refactor `modules/platforms/miaoshou/components/overlay_guard.py` so it delegates to the shared safe-notice handler instead of maintaining a separate selector engine.

- [ ] **Step 6: Run the component-level cleanup tests**

Run:

```bash
python -m pytest backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py -q
```

Expected: PASS

- [ ] **Step 7: Run the existing Miaoshou contract tests**

Run:

```bash
python -m pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_component_tester_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 8: Commit the runtime stabilization integration**

```bash
git add modules/components/base.py modules/platforms/miaoshou/components/login.py modules/platforms/shopee/components/login.py modules/platforms/tiktok/components/login.py modules/platforms/miaoshou/components/navigation.py modules/platforms/miaoshou/components/orders_export_base.py modules/platforms/miaoshou/components/overlay_guard.py backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py
git commit -m "feat: stabilize collection pages against safe notice overlays"
```

---

### Task 4: Verify Against Real Failure Evidence And Keep The Debug Loop Intact

**Files:**
- Modify: `docs/superpowers/plans/2026-04-09-cross-platform-notification-overlay-stabilization.md`
- Test: existing failure artifacts under `temp/component_tests/` and `temp/test_results/`
- Test: existing pwcli evidence under `output/playwright/work/miaoshou/orders-shopee/`

- [ ] **Step 1: Re-read the confirmed Miaoshou failure artifacts**

Review:
- `temp/component_tests/test_3d80a41b44a1/result.json`
- `temp/component_tests/test_3d80a41b44a1/orders_shopee_export_python_component_1_20260409_205826.json`
- `temp/component_tests/test_3d80a41b44a1/orders_shopee_export_python_component_1_20260409_205826.html`
- `temp/test_results/orders_shopee_export_error_20260409_205825.png`

Expected: the implementation still matches the real `notice-message-box-dialog` structure.

- [ ] **Step 2: Re-read the related pwcli evidence**

Review:
- `output/playwright/work/miaoshou/orders-shopee/06-export-menu-open.md`
- `output/playwright/work/miaoshou/orders-shopee/07-export-progress.md`

Expected: the normal orders export flow remains unaffected when the notice overlay is absent.

- [ ] **Step 3: Run the focused regression bundle one more time**

Run:

```bash
python -m pytest backend/tests/test_popup_handler_safe_notice.py backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_component_tester_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 4: Commit the verified final state**

```bash
git add modules/apps/collection_center/popup_handler.py modules/components/base.py modules/platforms/miaoshou/popup_config.py modules/platforms/shopee/popup_config.py modules/platforms/tiktok/popup_config.py modules/platforms/miaoshou/components/login.py modules/platforms/shopee/components/login.py modules/platforms/tiktok/components/login.py modules/platforms/miaoshou/components/navigation.py modules/platforms/miaoshou/components/orders_export_base.py modules/platforms/miaoshou/components/overlay_guard.py backend/tests/test_popup_handler_safe_notice.py backend/tests/test_cross_platform_login_overlay_cleanup.py backend/tests/test_miaoshou_login_component.py backend/tests/test_miaoshou_navigation_overlay_cleanup.py backend/tests/test_miaoshou_orders_overlay_cleanup.py docs/superpowers/specs/2026-04-09-cross-platform-notification-overlay-stabilization-design.md docs/superpowers/plans/2026-04-09-cross-platform-notification-overlay-stabilization.md
git commit -m "feat: add cross-platform notification overlay stabilization"
```

---

## Notes

- This plan intentionally does **not** expand into a universal "close every dialog" system.
- This plan intentionally treats Shopee/TikTok as framework participants first and evidence-backed rule providers later.
- Database / schema drift remains a separate workstream and should not be folded into this implementation slice.
