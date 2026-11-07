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

    # 店铺切换器上代表「全部店铺」的聚合标签：命中即代表当前没有落到具体某一家店铺
    _AGGREGATE_SHOP_LABEL_TOKENS: tuple[str, ...] = (
        "所有店铺",
        "全部店铺",
        "所有商店",
        "全部商店",
        "all shops",
        "all store",
        "allshop",
    )

    # 店铺切换器标签里可能出现的区域文案 -> 规范区域键
    # 与 _region_text_candidates（用于点击目标区域）分开维护：这里只用于「读标签里的区域」
    _LABEL_REGION_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("MY", ("malaysia", "my", "马来西亚")),
        ("SG", ("singapore", "sg", "新加坡")),
        ("PH", ("philippines", "ph", "菲律宾")),
        ("TH", ("thailand", "th", "泰国")),
        ("VN", ("vietnam", "vn", "越南")),
        ("ID", ("indonesia", "id", "印度尼西亚")),
        ("TW", ("taiwan", "tw", "台湾")),
        ("BR", ("brazil", "br", "巴西")),
        ("MX", ("mexico", "mx", "墨西哥")),
        ("CL", ("chile", "cl", "智利")),
        ("CO", ("colombia", "co", "哥伦比亚")),
    )

    def __init__(self, ctx: ExecutionContext, selectors: ProductsSelectors | None = None) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)
        # 选择器与调用方同源，避免店铺切换触发器出现两套口径
        self.sel = selectors or ProductsSelectors()

    def _normalize_text(self, value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _current_shop_id_from_url(self, url: str | None) -> str | None:
        try:
            query = dict(parse_qsl(urlsplit(str(url or "")).query))
            shop_id = str(query.get("cnsc_shop_id") or "").strip()
            return shop_id or None
        except Exception:
            return None

    async def _target_shop_id(self) -> str | None:
        """目标店铺编号 = 主数据 core.shop_accounts.platform_shop_id。

        取不到(账号查无 / 主数据未登记)→ 返回 None, 由调用方走「按店名 UI 兜底切换」。
        绝不回退到 ctx.config / ctx.account 里的来路不明编号。
        """
        account = self.ctx.account or {}
        shop_account_id = str(
            account.get("shop_account_id") or account.get("account_id") or ""
        ).strip()
        if not shop_account_id:
            return None

        from backend.services.shop_account_identity_service import (
            resolve_master_platform_shop_id,
        )

        resolved = await resolve_master_platform_shop_id(shop_account_id)
        return resolved or None

    def _rewrite_cnsc_shop_id(self, url: str | None, target_shop_id: str) -> str:
        parts = urlsplit(str(url or ""))
        query = dict(parse_qsl(parts.query))
        query["cnsc_shop_id"] = str(target_shop_id)
        rewritten_query = urlencode(query)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, rewritten_query, parts.fragment)
        )

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

    def _is_aggregate_shop_label(self, current_label: str) -> bool:
        """标签是否代表「所有店铺」这类聚合视图（而非落到某一家具体店铺）。"""
        for token in self._AGGREGATE_SHOP_LABEL_TOKENS:
            if token and token in current_label:
                return True
        return False

    def _extract_label_region(self, current_label: str) -> str | None:
        """从「区域 / 店铺」形态的标签里读出区域规范键；读不出返回 None。"""
        head = current_label.split(" / ", 1)[0].strip()
        if not head or head == current_label.strip():
            # 没有「区域 / 店铺」分隔结构 → 标签未显式带区域
            return None
        for region_key, candidates in self._LABEL_REGION_CANDIDATES:
            for candidate in candidates:
                if candidate and candidate == head:
                    return region_key
        return None

    def _label_region_matches_target(
        self, current_label: str, target_region: str | None
    ) -> bool:
        """标签里显式带出的区域必须与目标区域一致；标签没带区域时不据此否决。"""
        if not target_region:
            return True
        label_region = self._extract_label_region(current_label)
        if label_region is None:
            return True
        return label_region == self._normalize_text(target_region).upper()

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
        # 「所有店铺」聚合标签下即便出现了目标店名，也不代表已落到该店
        if self._is_aggregate_shop_label(current):
            return False
        if target not in current:
            return False
        if not self._label_region_matches_target(current, target_region):
            return False
        return True

    async def _first_visible_locator(
        self, page: Any, selectors: tuple[str, ...]
    ) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _visible_text_content(
        self, page: Any, selectors: tuple[str, ...]
    ) -> str | None:
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
            current_shop_label = await self._visible_text_content(
                page, self.sel.shop_switch_triggers
            )
            if self._shop_name_looks_selected(
                current_shop_label, target_shop, target_region
            ):
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
            current_shop_id = self._current_shop_id_from_url(
                str(getattr(page, "url", "") or "")
            )
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

        target_shop_id = await self._target_shop_id()
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
                return ShopSelectResult(
                    success=True,
                    shop_name=target_shop,
                    region=target_region,
                    message="ok",
                )

            target_url = self._rewrite_cnsc_shop_id(current_url, target_shop_id)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            if hasattr(page, "wait_for_timeout"):
                await page.wait_for_timeout(800)

            confirmed = await self._confirm_target_shop_id(page, target_shop_id)
            if not confirmed:
                return ShopSelectResult(
                    success=False,
                    shop_name=target_shop,
                    region=target_region,
                    message="failed to confirm target shop id",
                )

            cfg = dict(self.ctx.config or {})
            cfg["cnsc_shop_id"] = target_shop_id
            cfg["shop_id"] = target_shop_id
            cfg["shop_name"] = target_shop
            if target_region:
                cfg["shop_region"] = target_region
            self.ctx.config = cfg
            return ShopSelectResult(
                success=True, shop_name=target_shop, region=target_region, message="ok"
            )

        current_shop_label = await self._visible_text_content(
            page, self.sel.shop_switch_triggers
        )
        if self._shop_name_looks_selected(
            current_shop_label, target_shop, target_region
        ):
            return ShopSelectResult(
                success=True, shop_name=target_shop, region=target_region, message="ok"
            )

        trigger = await self._first_visible_locator(page, self.sel.shop_switch_triggers)
        if trigger is None:
            return ShopSelectResult(
                success=False,
                shop_name=target_shop,
                region=target_region,
                message="shop switch trigger not found",
            )

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
                applied = await self._wait_shop_selection_applied(
                    page, target_shop, target_region
                )
                if not applied:
                    return ShopSelectResult(
                        success=False,
                        shop_name=target_shop,
                        region=target_region,
                        message="shop switch did not apply",
                    )
                return ShopSelectResult(
                    success=True,
                    shop_name=target_shop,
                    region=target_region,
                    message="ok",
                )
        except Exception:
            pass

        return ShopSelectResult(
            success=False,
            shop_name=target_shop,
            region=target_region,
            message="target shop not found",
        )
