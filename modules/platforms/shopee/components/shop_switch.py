from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.products_config import ProductsSelectors


@dataclass
class ShopSelectResult:
    success: bool
    shop_name: str | None = None
    region: str | None = None
    message: str = ""


class ShopeeShopSwitch:
    platform = "shopee"
    component_type = "shop_switch"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)
        self.sel = ProductsSelectors()

    def _normalize_text(self, value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _current_shop_id_from_url(self, url: str | None) -> str | None:
        try:
            query = dict(parse_qsl(urlsplit(str(url or "")).query))
            shop_id = str(query.get("cnsc_shop_id") or "").strip()
            return shop_id or None
        except Exception:
            return None

    def _target_shop_id(self) -> str | None:
        cfg = self.ctx.config or {}
        account = self.ctx.account or {}
        shop_id = str(
            cfg.get("cnsc_shop_id")
            or cfg.get("shop_id")
            or account.get("cnsc_shop_id")
            or account.get("platform_shop_id")
            or account.get("shop_id")
            or ""
        ).strip()
        from backend.services.shopee_shop_id_resolver import (
            resolve_shopee_platform_shop_id,
        )

        resolved = resolve_shopee_platform_shop_id(
            platform=self.ctx.platform,
            account_id=account.get("shop_account_id") or account.get("account_id"),
            store_name=(
                cfg.get("shop_name")
                or account.get("store_name")
                or account.get("selected_shop_name")
                or account.get("display_shop_name")
            ),
            platform_shop_id=cfg.get("platform_shop_id") or account.get("platform_shop_id"),
            shop_id=shop_id,
        )
        if resolved:
            return resolved
        return shop_id or None

    def _rewrite_cnsc_shop_id(self, url: str | None, target_shop_id: str) -> str:
        parts = urlsplit(str(url or ""))
        query = dict(parse_qsl(parts.query))
        query["cnsc_shop_id"] = str(target_shop_id)
        rewritten_query = urlencode(query)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, rewritten_query, parts.fragment))

    def _region_text_candidates(self, region_value: str | None) -> tuple[str, ...]:
        raw = str(region_value or "").strip()
        normalized = raw.upper()
        mapping = {
            "MY": ("Malaysia", "MY", "马来西亚"),
            "SG": ("Singapore", "SG", "新加坡"),
            "PH": ("Philippines", "PH", "菲律宾"),
            "TH": ("Thailand", "TH", "泰国"),
            "VN": ("Vietnam", "VN", "越南"),
            "ID": ("Indonesia", "ID", "印度尼西亚"),
            "TW": ("Taiwan", "TW", "台湾"),
        }
        if normalized in mapping:
            return mapping[normalized]
        if raw:
            return (raw,)
        return ()

    def _shop_name_looks_selected(
        self,
        current_label: str | None,
        target_shop: str,
        target_region: str | None,
    ) -> bool:
        current = self._normalize_text(current_label)
        target = self._normalize_text(target_shop)
        if not current or not target:
            return False
        if target not in current:
            return False
        normalized_region = self._normalize_text(target_region)
        if normalized_region:
            region_candidates = self._region_text_candidates(target_region)
            normalized_candidates = tuple(self._normalize_text(candidate) for candidate in region_candidates)
            if normalized_region not in normalized_candidates:
                return False
        return target in current

    async def _first_visible_locator(self, page: Any, selectors: tuple[str, ...]) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _visible_text_content(self, page: Any, selectors: tuple[str, ...]) -> str | None:
        locator = await self._first_visible_locator(page, selectors)
        if locator is None:
            return None
        try:
            return await locator.text_content()
        except Exception:
            return None

    async def _wait_shop_selection_applied(
        self,
        page: Any,
        target_shop: str,
        target_region: str | None,
        *,
        timeout_ms: int = 2500,
        poll_ms: int = 250,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            current_shop_label = await self._visible_text_content(page, self.sel.shop_switch_triggers)
            if self._shop_name_looks_selected(current_shop_label, target_shop, target_region):
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    async def _confirm_target_shop_id(
        self,
        page: Any,
        target_shop_id: str,
        *,
        timeout_ms: int = 4000,
        poll_ms: int = 200,
    ) -> bool:
        waited = 0
        while waited <= timeout_ms:
            current_shop_id = self._current_shop_id_from_url(str(getattr(page, "url", "") or ""))
            if current_shop_id == target_shop_id:
                return True
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(poll_ms)
            waited += poll_ms
        return False

    def _target_shop(self) -> tuple[str | None, str | None]:
        cfg = self.ctx.config or {}
        account = self.ctx.account or {}
        target_shop = str(
            cfg.get("shop_name")
            or account.get("store_name")
            or account.get("menu_display_name")
            or account.get("menu_name")
            or account.get("selected_shop_name")
            or ""
        ).strip()
        target_region = str(
            cfg.get("shop_region")
            or cfg.get("region")
            or account.get("shop_region")
            or account.get("region")
            or ""
        ).strip()
        return target_shop or None, target_region or None

    async def run(self, page: Any) -> ShopSelectResult:
        target_shop, target_region = self._target_shop()
        if not target_shop:
            return ShopSelectResult(success=True, message="no target shop")

        target_shop_id = self._target_shop_id()
        current_url = str(getattr(page, "url", "") or "")
        current_shop_id = self._current_shop_id_from_url(current_url)
        if self.logger and target_shop_id:
            self.logger.info(
                "[ShopeeShopSwitch] target_shop=%s target_cnsc_shop_id=%s current_cnsc_shop_id=%s current_url=%s",
                target_shop,
                target_shop_id,
                current_shop_id,
                current_url,
            )

        if target_shop_id:
            if current_shop_id == target_shop_id:
                cfg = dict(self.ctx.config or {})
                cfg["cnsc_shop_id"] = target_shop_id
                cfg["shop_id"] = target_shop_id
                cfg["shop_name"] = target_shop
                if target_region:
                    cfg["shop_region"] = target_region
                self.ctx.config = cfg
                return ShopSelectResult(success=True, shop_name=target_shop, region=target_region, message="ok")

            target_url = self._rewrite_cnsc_shop_id(current_url, target_shop_id)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(800)

            confirmed = await self._confirm_target_shop_id(page, target_shop_id)
            if not confirmed:
                return ShopSelectResult(success=False, shop_name=target_shop, region=target_region, message="failed to confirm target shop id")

            cfg = dict(self.ctx.config or {})
            cfg["cnsc_shop_id"] = target_shop_id
            cfg["shop_id"] = target_shop_id
            cfg["shop_name"] = target_shop
            if target_region:
                cfg["shop_region"] = target_region
            self.ctx.config = cfg
            return ShopSelectResult(success=True, shop_name=target_shop, region=target_region, message="ok")

        current_shop_label = await self._visible_text_content(page, self.sel.shop_switch_triggers)
        if self._shop_name_looks_selected(current_shop_label, target_shop, target_region):
            return ShopSelectResult(success=True, shop_name=target_shop, region=target_region, message="ok")

        trigger = await self._first_visible_locator(page, self.sel.shop_switch_triggers)
        if trigger is None:
            return ShopSelectResult(success=False, shop_name=target_shop, region=target_region, message="shop switch trigger not found")

        await trigger.click(timeout=5000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(800)

        for candidate in self._region_text_candidates(target_region):
            if not candidate:
                continue
            try:
                region_locator = page.get_by_text(candidate, exact=False).first
                if await region_locator.is_visible(timeout=1000):
                    await region_locator.click(timeout=5000)
                    if hasattr(page, "wait_for_timeout"):
                        await page.wait_for_timeout(300)
                    break
            except Exception:
                continue

        try:
            target = page.get_by_text(target_shop, exact=False).first
            if await target.is_visible(timeout=1500):
                await target.click(timeout=5000)
                applied = await self._wait_shop_selection_applied(page, target_shop, target_region)
                if not applied:
                    return ShopSelectResult(success=False, shop_name=target_shop, region=target_region, message="shop switch did not apply")
                return ShopSelectResult(success=True, shop_name=target_shop, region=target_region, message="ok")
        except Exception:
            pass

        return ShopSelectResult(success=False, shop_name=target_shop, region=target_region, message="target shop not found")
