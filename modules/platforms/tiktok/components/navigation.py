from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage


class TiktokNavigation(NavigationComponent):
    """TikTok Shop navigation component."""

    # Component metadata
    platform = "tiktok"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def _build_time_params(self, days: int) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=days)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        """Deep-link navigation for TikTok Shop (globalselling compass).

        Rules:
        - Domain is seller.tiktokshopglobalselling.com
        - Query requires `shop_region` (e.g., SG/MY/PH)
        - Default: include timeRange/shortcut, EXCEPT traffic overview where it must be omitted
        """
        try:
            # Resolve selectors/config by target
            if target == TargetPage.PRODUCTS_PERFORMANCE:
                from modules.platforms.tiktok.components.products_config import ProductsSelectors as Sel
                path = getattr(Sel, "performance_path", None) or getattr(Sel, "PRODUCTS_PERFORMANCE_PATH", None) or getattr(Sel, "PRODUCTS_PATH", None)
            elif target == TargetPage.TRAFFIC_OVERVIEW:
                from modules.platforms.tiktok.components.analytics_config import AnalyticsSelectors as Sel
                path = getattr(Sel, "traffic_path", None) or getattr(Sel, "TRAFFIC_PATH", None)
            elif target == TargetPage.SERVICE_ANALYTICS:
                from modules.platforms.tiktok.components.service_config import ServiceSelectors as Sel
                path = getattr(Sel, "service_path", None) or getattr(Sel, "SERVICE_PATH", None)
            elif target == TargetPage.ORDERS:
                from modules.platforms.tiktok.components.orders_config import OrdersSelectors as Sel
                path = getattr(Sel, "orders_path", None) or getattr(Sel, "ORDERS_PATH", None)
            elif target == TargetPage.FINANCE:
                from modules.platforms.tiktok.components.finance_config import FinanceSelectors as Sel
                path = getattr(Sel, "finance_path", None) or getattr(Sel, "FINANCE_PATH", None)
            else:
                return NavigationResult(success=False, url="", message=f"unsupported target: {target}")

            base = getattr(Sel, "base_url", None) or getattr(Sel, "BASE_URL", "https://seller.tiktokshopglobalselling.com")
            if not path:
                return NavigationResult(success=False, url="", message="missing deep-link path in selectors")

            # Parameters
            cfg = self.ctx.config or {}
            region = cfg.get("shop_region") or self.ctx.account.get("shop_region") or "SG"
            days = int(cfg.get("days", 28))
            default_nav_with_timerange = False if target == TargetPage.TRAFFIC_OVERVIEW else True
            nav_with_timerange = bool(cfg.get("nav_with_timerange", default_nav_with_timerange))

            params = [("shop_region", region)]
            if nav_with_timerange:
                start, end = self._build_time_params(days)
                params += [
                    ("timeRange", f"{start}%7C{end}"),  # encode '|'
                    ("shortcut", f"last{days}days"),
                ]
            qs = "&".join([f"{k}={v}" for k, v in params if v])
            url = f"{base}{path}?{qs}"

            if self.logger:
                self.logger.info(f"[TiktokNavigation] goto: {url}")
            # Prefer domcontentloaded; fallback to full load on slow pages
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                await page.goto(url, wait_until="load", timeout=60000)

            # Watchdog: 某些情况下（ServiceWorker/缓存损坏、会话切域），页面会白屏或无限旋转
            # 若 10s 仍未渲染出主容器内容，则清理 SW/Cache 并强制刷新一次
            try:
                await page.wait_for_timeout(1000)
                async def _is_blank() -> bool:
                    try:
                        return await page.evaluate(
                            "(() => {"
                            "const st = document.readyState;"
                            "const root = document.querySelector('#root, #app');"
                            "const hasKids = root ? (root.childElementCount > 0) : (document.body && document.body.childElementCount > 0);"
                            "return (st === 'complete' || st === 'interactive') ? !hasKids : false;"
                            "})()"
                        )
                    except Exception:
                        return False
                # 等待最多 10s（20 * 500ms）；若始终 blank，执行自愈
                blank_ticks = 0
                for _ in range(20):
                    if not await _is_blank():
                        break
                    blank_ticks += 1
                    await page.wait_for_timeout(500)
                if blank_ticks >= 20:
                    if self.logger:
                        self.logger.warning("[TiktokNavigation] blank watchdog triggered; clearing SW/cache and hard-reload")
                    try:
                        await page.evaluate(
                            "(() => {"
                            "try { if (window.caches) { caches.keys().then(keys => keys.forEach(k => caches.delete(k))); } } catch(e){}"
                            "try { if (navigator.serviceWorker) { navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister())); } } catch(e){}"
                            "})()"
                        )
                    except Exception:
                        pass
                    try:
                        await page.reload(wait_until="load", timeout=45000)
                    except Exception:
                        try:
                            await page.keyboard.down("Control")
                            await page.keyboard.press("Shift+R")
                            await page.keyboard.up("Control")
                        except Exception:
                            pass
                    await page.wait_for_timeout(1200)
            except Exception:
                pass

            await page.wait_for_timeout(800)
            return NavigationResult(success=True, url=url, message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[TiktokNavigation] failed: {e}")
            return NavigationResult(success=False, url="", message=str(e))
