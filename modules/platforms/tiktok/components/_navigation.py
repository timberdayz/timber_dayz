from __future__ import annotations

from typing import Any


LOADING_SELECTORS: tuple[str, ...] = (
    '[data-tid="m4b_loading"]',
    ".theme-arco-spin",
    ".theme-m4b-loading",
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
    for selector in LOADING_SELECTORS:
        if await _locator_visible(page, selector):
            return True
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
