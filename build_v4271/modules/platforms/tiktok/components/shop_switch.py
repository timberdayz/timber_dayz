from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from modules.components.base import ExecutionContext


@dataclass
class ShopSelectResult:
    success: bool
    region: Optional[str] = None
    shop_name: Optional[str] = None
    shop_display_name: Optional[str] = None
    message: str = ""


class TiktokShopSwitch:
    """Canonical TikTok shop switch component for V2.

    TikTok currently maps one shop to one `shop_region`, so the most stable
    switch strategy is to rewrite the current page URL with the target region
    while preserving the active path and unrelated query parameters.
    """

    platform = "tiktok"
    component_type = "shop_switch"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)

    def _account_label(self) -> str:
        account = self.ctx.account or {}
        return str(
            account.get("label")
            or account.get("store_name")
            or account.get("username")
            or "unknown"
        ).strip()

    def _current_region_from_url(self, url: str) -> Optional[str]:
        try:
            query = dict(parse_qsl(urlsplit(str(url or "")).query))
            region = str(query.get("shop_region") or "").strip().upper()
            return region or None
        except Exception:
            return None

    async def _current_shop_display_name(self, page: Any, region: str | None) -> Optional[str]:
        for candidate in filter(None, [region, "Singapore", "Malaysia", "Philippines"]):
            try:
                locator = page.get_by_text(candidate, exact=False).first
                if await locator.count() > 0 and await locator.is_visible(timeout=500):
                    text = await locator.inner_text(timeout=500)
                    raw_text = str(text or "").strip()
                    normalized_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                    if len(normalized_lines) > 2:
                        continue
                    text = " ".join(normalized_lines)
                    if len(text) > 80:
                        continue
                    if text:
                        return text
            except Exception:
                continue
        return None

    def _display_matches_region(self, display_name: str | None, region: str | None) -> bool:
        if not region:
            return False
        text = str(display_name or "").strip().upper()
        if not text:
            return False
        return text.startswith(f"{region} ") or text == region

    def _target_region(self, current_region: str | None) -> Optional[str]:
        config = self.ctx.config or {}
        account = self.ctx.account or {}
        region = str(
            config.get("shop_region")
            or account.get("shop_region")
            or current_region
            or ""
        ).strip().upper()
        return region or None

    def _rewrite_shop_region(self, url: str, target_region: str) -> str:
        parts = urlsplit(str(url or ""))
        query = dict(parse_qsl(parts.query))
        query["shop_region"] = target_region
        rewritten_query = urlencode(query)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, rewritten_query, parts.fragment))

    async def _locator_visible(self, page: Any, selector: str, timeout: int = 300) -> bool:
        try:
            locator = page.locator(selector).first
            if await locator.count() <= 0:
                return False
            return bool(await locator.is_visible(timeout=timeout))
        except Exception:
            return False

    async def _page_looks_loading(self, page: Any) -> bool:
        selectors = (
            '[data-tid="m4b_loading"]',
            ".theme-arco-spin",
            ".theme-m4b-loading",
        )
        for selector in selectors:
            if await self._locator_visible(page, selector, timeout=150):
                return True
        return False

    async def _confirm_target_region_after_refresh(
        self,
        page: Any,
        target_region: str,
        *,
        timeout_ms: int = 4000,
        poll_ms: int = 200,
    ) -> tuple[Optional[str], Optional[str]]:
        waited = 0
        last_region: Optional[str] = None
        last_display_name: Optional[str] = None

        while waited <= timeout_ms:
            current_url = str(getattr(page, "url", "") or "")
            last_region = self._current_region_from_url(current_url)
            if last_region == target_region:
                last_display_name = await self._current_shop_display_name(page, last_region)
                if last_display_name and self._display_matches_region(last_display_name, last_region):
                    return last_region, last_display_name
                if last_display_name and not self._display_matches_region(last_display_name, last_region):
                    if not await self._page_looks_loading(page):
                        return last_region, last_display_name
                elif waited >= poll_ms and not await self._page_looks_loading(page):
                    return last_region, None

            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms

        return last_region, last_display_name

    async def run(self, page: Any) -> ShopSelectResult:
        current_url = str(getattr(page, "url", "") or "")
        current_region = self._current_region_from_url(current_url)
        target_region = self._target_region(current_region)
        if not target_region:
            return ShopSelectResult(success=False, message="shop_region is required")

        if current_region != target_region:
            target_url = self._rewrite_shop_region(current_url, target_region)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(800)

        current_region, display_name = await self._confirm_target_region_after_refresh(page, target_region)
        if current_region != target_region:
            return ShopSelectResult(success=False, message="failed to confirm target shop region")

        region = current_region or target_region

        # TikTok products pages can spend a short period in a skeleton state
        # after region navigation. In that state the URL is already authoritative
        # but the header shop chip may not have rendered yet, so only reject when
        # a visible chip is present and it contradicts the resolved region.
        if display_name and not self._display_matches_region(display_name, region):
            return ShopSelectResult(success=False, message="failed to confirm target shop region")

        config = self.ctx.config or {}
        config["shop_region"] = region
        config["shop_name"] = f"{self._account_label()}_{region.lower()}"
        if display_name:
            config["shop_display_name"] = display_name
        self.ctx.config = config

        return ShopSelectResult(
            success=True,
            region=region,
            shop_name=config["shop_name"],
            shop_display_name=config.get("shop_display_name"),
            message="ok",
        )
