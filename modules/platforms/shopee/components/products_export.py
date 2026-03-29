from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlparse

from modules.components.base import ExecutionContext
from modules.components.export.base import (
    ExportComponent,
    ExportMode,
    ExportResult,
    build_standard_output_root,
)
from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    normalize_time_request,
    preset_label,
)
from modules.platforms.shopee.components.products_config import ProductsSelectors


class ShopeeProductsExport(ExportComponent):
    platform = "shopee"
    component_type = "export"
    data_domain = "products"

    def __init__(self, ctx: ExecutionContext, selectors: ProductsSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or ProductsSelectors()
        self._download_waiter: asyncio.Task | None = None

    def _products_page_looks_ready(self, url: str) -> bool:
        current = str(url or "").strip().lower()
        if not current:
            return False
        return self.sel.overview_path in current

    def _known_throttled_texts(self) -> tuple[str, ...]:
        return self.sel.throttled_texts

    def _is_export_throttled(self, text: str) -> bool:
        content = str(text or "").strip().lower()
        if not content:
            return False
        return any(token.lower() in content for token in self._known_throttled_texts())

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...]) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _visible_text(self, page: Any, text: str) -> bool:
        try:
            locator = page.get_by_text(text, exact=False).first
            return bool(await locator.is_visible(timeout=1000))
        except Exception:
            return False

    def _current_shop_id(self, page: Any) -> str | None:
        try:
            parsed = urlparse(str(getattr(page, "url", "") or ""))
            values = parse_qs(parsed.query).get("cnsc_shop_id") or []
            if values:
                return values[0]
        except Exception:
            pass
        cfg = self.ctx.config or {}
        account = self.ctx.account or {}
        return (
            str(cfg.get("shop_id") or "").strip()
            or str(account.get("shop_id") or "").strip()
            or str(account.get("cnsc_shop_id") or "").strip()
            or None
        )

    async def _cancel_download_waiter(self) -> None:
        waiter = self._download_waiter
        self._download_waiter = None
        if waiter is None:
            return
        if waiter.done():
            try:
                await waiter
            except Exception:
                pass
            return
        waiter.cancel()
        try:
            await waiter
        except Exception:
            pass

    async def _ensure_products_page_ready(self, page: Any) -> None:
        if self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            return
        target_url = f"https://seller.shopee.cn{build_domain_path('products')}"
        shop_id = self._current_shop_id(page)
        if shop_id:
            target_url = f"{target_url}?cnsc_shop_id={shop_id}"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1200)
        if not self._products_page_looks_ready(str(getattr(page, "url", "") or "")):
            raise RuntimeError("products overview page is not ready")

    async def _ensure_shop_selected(self, page: Any) -> None:
        cfg = self.ctx.config or {}
        account = self.ctx.account or {}
        target_shop = str(
            cfg.get("shop_name")
            or account.get("menu_display_name")
            or account.get("menu_name")
            or account.get("selected_shop_name")
            or ""
        ).strip()
        if not target_shop:
            return
        if await self._visible_text(page, target_shop):
            return

        trigger = await self._first_visible_locator(page, self.sel.shop_switch_triggers)
        if trigger is None:
            return
        await trigger.click(timeout=5000)
        await page.wait_for_timeout(800)

        try:
            target = page.get_by_text(target_shop, exact=False).first
            if await target.is_visible(timeout=1500):
                await target.click(timeout=5000)
                await page.wait_for_timeout(1200)
        except Exception:
            pass

    async def _ensure_date_selection(self, page: Any) -> None:
        config = self.ctx.config or {}
        if "preset" in config:
            normalized = normalize_time_request(
                "products",
                time_mode="preset",
                value=str(config["preset"]),
            )
            target_text = preset_label(normalized["value"])
            await self._open_date_picker(page)
            await self._click_text_option(page, target_text)
            return
        granularity = str(config.get("granularity") or "daily")
        normalized = normalize_time_request(
            "products",
            time_mode="granularity",
            value=granularity,
        )
        target_text = granularity_label(normalized["value"])
        await self._open_date_picker(page)
        await self._click_text_option(page, target_text)

    async def _open_date_picker(self, page: Any) -> None:
        trigger = await self._first_visible_locator(page, self.sel.date_picker_triggers)
        if trigger is None:
            return
        await trigger.click(timeout=5000)
        await page.wait_for_timeout(600)

    async def _click_text_option(self, page: Any, text: str) -> None:
        locator = page.get_by_text(text, exact=False).first
        if await locator.is_visible(timeout=2000):
            await locator.click(timeout=5000)
            await page.wait_for_timeout(900)

    async def _trigger_export(self, page: Any) -> None:
        button = await self._first_visible_locator(page, self.sel.export_buttons)
        if button is None:
            raise RuntimeError("export button not found")
        await self._cancel_download_waiter()
        if hasattr(page, "wait_for_event"):
            self._download_waiter = asyncio.create_task(
                page.wait_for_event("download", timeout=60000)
            )
        await button.click(timeout=5000)
        await page.wait_for_timeout(500)

    async def _detect_export_throttled(self, page: Any) -> bool:
        for token in self._known_throttled_texts():
            if await self._visible_text(page, token):
                return True
        return False

    async def _wait_export_retry_ready(self, page: Any) -> bool:
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(1500)
        return not await self._detect_export_throttled(page)

    async def _wait_download_complete(self, page: Any) -> str | None:
        waiter = self._download_waiter
        if waiter is None:
            if not hasattr(page, "wait_for_event"):
                return None
            try:
                download = await page.wait_for_event("download", timeout=60000)
            except Exception:
                return None
        else:
            try:
                download = await waiter
            except Exception:
                return None
            finally:
                self._download_waiter = None

        granularity = str((self.ctx.config or {}).get("granularity") or "manual")
        out_root = build_standard_output_root(self.ctx, data_type="products", granularity=granularity)
        out_root.mkdir(parents=True, exist_ok=True)
        suggested = getattr(download, "suggested_filename", None) or "products-export.xlsx"
        target = out_root / suggested
        try:
            await download.save_as(str(target))
        except Exception:
            return None
        return str(target)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self._ensure_products_page_ready(page)
            await self._ensure_shop_selected(page)
            await self._ensure_date_selection(page)

            await self._trigger_export(page)
            throttled = await self._detect_export_throttled(page)
            if throttled:
                retry_ready = await self._wait_export_retry_ready(page)
                if not retry_ready:
                    return ExportResult(success=False, message="export throttled and retry not ready")
                await self._trigger_export(page)
                throttled = await self._detect_export_throttled(page)
                if throttled:
                    await self._cancel_download_waiter()
                    return ExportResult(success=False, message="export throttled and retry not ready")

            file_path = await self._wait_download_complete(page)
            if file_path:
                return ExportResult(success=True, message="download complete", file_path=file_path)
            return ExportResult(success=False, message="download did not complete", file_path=None)
        except Exception as exc:
            return ExportResult(success=False, message=str(exc), file_path=None)
