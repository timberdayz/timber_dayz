from __future__ import annotations

from typing import Any


LOADING_SELECTORS: tuple[str, ...] = (
    '[data-tid="m4b_loading"]',
    ".theme-m4b-loading",
    ".theme-arco-spin-mask",
)


async def _locator_visible(page: Any, selector: str, timeout: int = 150) -> bool:
    try:
        locator = page.locator(selector).first
        if await locator.count() <= 0:
            return False
        return bool(await locator.is_visible(timeout=timeout))
    except Exception:
        return False


async def page_looks_loading(page: Any) -> bool:
    # NOTE:
    # TikTok Seller Center uses Arco's `.theme-arco-spin` in many non-blocking places
    # (inline button spinners, etc.). Treating ANY `.theme-arco-spin` as "loading"
    # makes readiness detection too strict and can cause false timeouts.
    for selector in LOADING_SELECTORS:
        if await _locator_visible(page, selector):
            return True

    # Fallback heuristic: detect a *blocking* Arco spinner even if selectors above miss it.
    # We consider it blocking when it has a mask, covers a large area, or is fixed-position.
    try:
        return bool(
            await page.evaluate(
                """() => {
                const isVisible = (el) => {
                  const r = el.getBoundingClientRect();
                  const s = getComputedStyle(el);
                  return r.width > 0 && r.height > 0 &&
                    s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                };
                const spins = Array.from(document.querySelectorAll('.theme-arco-spin')).filter(isVisible);
                for (const el of spins) {
                  const r = el.getBoundingClientRect();
                  const area = r.width * r.height;
                  const style = getComputedStyle(el);
                  if (el.querySelector('.theme-arco-spin-mask')) return true;
                  if (area >= 40000) return true; // >= 200*200
                  if (style.position === 'fixed' && area >= 10000) return true;
                }
                return false;
              }"""
            )
        )
    except Exception:
        return False
    return False


async def wait_until_page_settles(
    page: Any,
    *,
    timeout_ms: int = 6000,
    poll_ms: int = 200,
    stable_cycles: int = 2,
) -> str:
    try:
        if hasattr(page, "wait_for_load_state"):
            await page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 1500))
    except Exception:
        pass

    waited = 0
    stable_hits = 0
    last_url = str(getattr(page, "url", "") or "")
    current_url = last_url

    while waited <= timeout_ms:
        current_url = str(getattr(page, "url", "") or "")
        loading = await page_looks_loading(page)

        if not loading:
            if current_url == last_url:
                stable_hits += 1
            else:
                stable_hits = 1
            if stable_hits >= stable_cycles:
                return current_url
        else:
            stable_hits = 0

        last_url = current_url
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(poll_ms)
        waited += poll_ms

    return current_url


async def wait_until_bootstrap_finishes(
    page: Any,
    *,
    timeout_ms: int = 30000,
    poll_ms: int = 500,
    stable_cycles: int = 4,
) -> str:
    for state, timeout in (
        ("domcontentloaded", min(timeout_ms, 5000)),
        ("load", min(timeout_ms, 5000)),
        ("networkidle", min(timeout_ms, 3000)),
    ):
        try:
            await page.wait_for_load_state(state, timeout=timeout)
        except Exception:
            continue

    waited = 0
    stable_hits = 0
    last_url = str(getattr(page, "url", "") or "")
    current_url = last_url

    while waited <= timeout_ms:
        current_url = str(getattr(page, "url", "") or "")
        loading = await page_looks_loading(page)
        ready_state = "unknown"
        try:
            ready_state = str(await page.evaluate("() => document.readyState") or "unknown").strip().lower()
        except Exception:
            ready_state = "unknown"

        if not loading and ready_state == "complete":
            if current_url == last_url:
                stable_hits += 1
            else:
                stable_hits = 1
            if stable_hits >= stable_cycles:
                return current_url
        else:
            stable_hits = 0

        last_url = current_url
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(poll_ms)
        waited += poll_ms

    return current_url


async def goto_when_ready(
    page: Any,
    url: str,
    *,
    goto_timeout: int = 60000,
    settle_timeout_ms: int = 6000,
    poll_ms: int = 200,
) -> str:
    await wait_until_page_settles(
        page,
        timeout_ms=settle_timeout_ms,
        poll_ms=poll_ms,
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout)
    return await wait_until_page_settles(
        page,
        timeout_ms=settle_timeout_ms,
        poll_ms=poll_ms,
    )
