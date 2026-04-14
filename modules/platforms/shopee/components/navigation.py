from __future__ import annotations

from typing import Any, Awaitable, Callable

from modules.components.base import ExecutionContext


class ShopeeNavigation:
    platform = "shopee"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)

    def page_looks_ready(self, url: str, overview_path: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return str(overview_path or "").strip().lower() in current

    async def ensure_overview_ready(
        self,
        page: Any,
        *,
        overview_path: str,
        error_message: str,
        target_url: str | None = None,
        wait_ms: int = 1200,
        business_ready: Callable[[Any], Awaitable[bool]] | None = None,
        business_error_message: str | None = None,
        business_timeout_ms: int = 10000,
        business_poll_ms: int = 500,
    ) -> None:
        if not self.page_looks_ready(str(getattr(page, "url", "") or ""), overview_path):
            resolved_target = str(target_url or f"https://seller.shopee.cn{overview_path}")
            await page.goto(resolved_target, wait_until="domcontentloaded", timeout=60000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(wait_ms)

        if not self.page_looks_ready(str(getattr(page, "url", "") or ""), overview_path):
            raise RuntimeError(error_message)

        if business_ready is not None:
            waited = 0
            while True:
                ready = await business_ready(page)
                if ready:
                    break
                if waited >= business_timeout_ms:
                    raise RuntimeError(business_error_message or error_message)
                if hasattr(page, "wait_for_timeout"):
                    await page.wait_for_timeout(business_poll_ms)
                waited += business_poll_ms
