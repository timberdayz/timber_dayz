from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, List, Optional

from modules.components.base import ExecutionContext


@dataclass
class ShopSelectResult:
    success: bool
    region: Optional[str] = None
    shop_name: Optional[str] = None
    shop_code: Optional[str] = None
    message: str = ""


class TiktokShopSwitch:
    """Canonical TikTok shop switch component for V2."""

    platform = "tiktok"
    component_type = "shop_switch"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.logger = getattr(ctx, "logger", None)

    def _log(self, level: str, msg: str) -> None:
        try:
            if self.logger and hasattr(self.logger, level):
                getattr(self.logger, level)(f"[TiktokShopSwitch] {msg}")
        except Exception:
            pass

    def _extract_shop_name(self) -> Optional[str]:
        acc = self.ctx.account or {}
        return (
            acc.get("menu_display_name")
            or acc.get("display_shop_name")
            or acc.get("store_name")
            or acc.get("label")
            or acc.get("username")
        )

    @staticmethod
    def _extract_shop_code_from_text(text: str) -> Optional[str]:
        m = re.search(r"搴楅摵浠ｇ爜\s*[::]\s*([A-Z0-9]+)", text)
        if not m:
            m = re.search(r"Shop\s*code\s*[::]\s*([A-Z0-9]+)", text, re.I)
        return m.group(1) if m else None

    async def run(self, page: Any) -> ShopSelectResult:
        try:
            acc = self.ctx.account or {}
            allowed: List[str] = []
            cfg_allowed = acc.get("allowed_regions") or []
            if isinstance(cfg_allowed, list):
                allowed = [str(x).upper() for x in cfg_allowed if str(x).strip()]
            if not allowed:
                allowed = ["MY", "PH", "SG"]

            candidates: list[tuple[str, Optional[str], Optional[str]]] = []
            for region in allowed:
                url = f"https://seller.tiktokshopglobalselling.com/homepage?shop_region={region}"
                nav_ok = False
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    nav_ok = True
                except Exception:
                    try:
                        await page.goto(url, wait_until="load", timeout=25000)
                        nav_ok = True
                    except Exception:
                        nav_ok = False
                if nav_ok:
                    try:
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass

                shop_name = self._extract_shop_name() or "unknown_shop"
                shop_code = None
                if nav_ok:
                    try:
                        loc = page.locator("div.text-p4-regular.text-neutral-text4.mb-4.px-24.break-all")
                        texts = []
                        try:
                            texts = await loc.all_inner_texts() or []
                        except Exception:
                            try:
                                texts = [await loc.inner_text(timeout=1000)]
                            except Exception:
                                texts = []
                        for text in texts:
                            shop_code = self._extract_shop_code_from_text(text)
                            if shop_code:
                                break
                        if not shop_code:
                            html = await page.content()
                            shop_code = self._extract_shop_code_from_text(html)
                    except Exception:
                        pass

                candidates.append((region, shop_name, shop_code))

            if not candidates:
                return ShopSelectResult(success=False, message="no region selected")

            picked_region, shop_name, shop_code = candidates[0]
            self.ctx.config = self.ctx.config or {}
            self.ctx.config["shop_region"] = picked_region
            if shop_code:
                self.ctx.config["shop_id"] = shop_code
            account_label = (acc.get("label") or acc.get("store_name") or acc.get("username") or "unknown")
            self.ctx.config["shop_name"] = f"{account_label}_{picked_region.lower()}"
            self._log(
                "info",
                f"selected region={picked_region}, shop_name={self.ctx.config.get('shop_name')}, shop_id={self.ctx.config.get('shop_id')}",
            )
            return ShopSelectResult(
                success=True,
                region=picked_region,
                shop_name=self.ctx.config.get("shop_name"),
                shop_code=shop_code,
                message="ok",
            )
        except Exception as e:
            self._log("error", f"failed: {e}")
            return ShopSelectResult(success=False, message=str(e))
