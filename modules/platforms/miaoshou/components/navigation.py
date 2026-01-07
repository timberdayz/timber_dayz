from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors
from modules.platforms.miaoshou.components.products_config import ProductsSelectors
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


class MiaoshouNavigation(NavigationComponent):
    # Component metadata (v4.8.0)
    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _close_announcements(self, page: Any) -> None:
        """
        关闭 Miaoshou 页面上的公告/通知/抽屉等常见遮挡组件。
        - 选择器与轮询策略来源于 *_config.py，可随配置调整
        - 顶层与所有 frame 并行尝试 + ESC 兜底
        """
        try:
            # 读取配置（优先 Warehouse，其次 Products 补充）
            ws = WarehouseSelectors()
            from modules.platforms.miaoshou.components.products_config import ProductsSelectors as _PS
            try:
                ps = _PS()
            except Exception:
                ps = None  # 可选
            rounds = int(getattr(ws, "close_poll_max_rounds", 20))
            interval = int(getattr(ws, "close_poll_interval_ms", 300))
            sels = set(getattr(ws, "popup_close_buttons", []))
            if ps:
                sels.update(getattr(ps, "popup_close_buttons", []))
            # 常见兜底
            sels.update({
                ".ant-modal-close",
                ".ant-modal-wrap .ant-modal-close",
                ".ant-drawer-close",
                ".ant-notification-notice-close",
                ".ant-notification .anticon-close",
                ".ant-message-notice-close",
                ".ant-popover .ant-popover-close",
                "[aria-label='Close']",
                "[aria-label='关闭']",
                "button[aria-label='关闭此对话框']",
                ".jx-dialog__headerbtn",
                ".jx-dialog__close",
                "button:has-text(我知道了)",
                "button:has-text(知道了)",
                "button:has-text(关闭)",
                "button:has-text(确认)",
                "button:has-text(确定)",
                "button:has-text(取消)",
                "button:has-text(OK)",
            })
            sels = list(sels)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            for _ in range(rounds):
                closed = False
                for s in sels:
                    try:
                        await page.locator(s).first.click(timeout=600)
                        closed = True
                    except Exception:
                        pass
                try:
                    for fr in page.frames:
                        for s in sels:
                            try:
                                await fr.locator(s).first.click(timeout=600)
                                closed = True
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    await page.wait_for_timeout(interval)
                except Exception:
                    pass
        except Exception:
            pass

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        # Prefer deep-link when available; fallback to sidebar text navigation.
        selectors = WarehouseSelectors()
        base = selectors.base_url
        try:
            if self.logger:
                self.logger.info(f"[MiaoshouNavigation] target: {target}")
            # Ensure we're on site (prefer account.login_url)
            cur = str(getattr(page, "url", ""))
            try:
                print(f"[MiaoshouNavigation] [START] cur={cur}")
            except Exception:
                pass
            if "miaoshou" not in cur:
                acc = self.ctx.account or {}
                login_url = acc.get("login_url") or f"{base}/?redirect=%2Fwelcome"
                try:
                    print(f"[MiaoshouNavigation] -> goto login_url: {login_url}")
                except Exception:
                    pass
                await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(400)
            # Deep links
            # Fast path: if already on target page, do a quick readiness check and return
            try:
                cur2 = str(getattr(page, "url", ""))
                # Fast-path: only when the target itself is the checklist/products page
                try:
                    if target in (TargetPage.WAREHOUSE_CHECKLIST, TargetPage.PRODUCTS_PERFORMANCE) and "/warehouse/checklist" in cur2:
                        try:
                            print("[MiaoshouNavigation] [FAST] fast-path on checklist (skip readiness)")
                        except Exception:
                            pass
                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        try:
                            await page.wait_for_timeout(120)
                        except Exception:
                            pass
                        return NavigationResult(success=True, url=str(getattr(page, 'url', '')), message="already-on-checklist")
                except Exception:
                    pass

                if target in (TargetPage.WAREHOUSE_CHECKLIST, TargetPage.PRODUCTS_PERFORMANCE) and "/warehouse/checklist" in cur2:
                    try:
                        # Wait up to ~3s for a key control to appear to mark page ready
                        ready_ok = False
                        for _ in range(6):
                            try:
                                if await page.get_by_text("导入/导出商品", exact=False).first.is_visible():
                                    ready_ok = True
                                    break
                            except Exception:
                                pass
                            try:
                                await page.wait_for_timeout(500)
                            except Exception:
                                pass
                        try:
                            print(f"[MiaoshouNavigation]  fast-path on checklist, ready={ready_ok}")
                        except Exception:
                            pass
                        if self.logger:
                            self.logger.info("[MiaoshouNavigation] detected checklist page (fast path)")
                    except Exception:
                        pass
                    return NavigationResult(success=True, url=str(getattr(page, 'url', '')), message="already on checklist")
            except Exception:
                pass

            deep_url = None
            if target == TargetPage.WAREHOUSE_CHECKLIST:
                deep_url = f"{selectors.base_url}{selectors.checklist_path}"
            elif target == TargetPage.PRODUCTS_PERFORMANCE:
                ps = ProductsSelectors()
                # Try candidate deep links in order
                for path in list(ps.deep_link_paths):
                    try:
                        test_url = f"{ps.base_url}{path}"
                        await page.goto(test_url, wait_until="domcontentloaded", timeout=40000)
                        deep_url = test_url
                        break
                    except Exception:
                        continue
            elif target == TargetPage.ORDERS:
                osel = OrdersSelectors()
                # Preferred subtype from context, fallback to trying all
                cfg = self.ctx.config or {}
                preferred = str(cfg.get("orders_subtype") or "").lower().strip()
                try_list = [s for s in [preferred] if s] + [s for s in osel.subtypes if s != preferred]
                for sub in try_list:
                    try:
                        test_url = f"{osel.base_url}{osel.deep_link_template.format(platform=sub)}"
                        await page.goto(test_url, wait_until="domcontentloaded", timeout=40000)
                        deep_url = test_url
                        break
                    except Exception:
                        continue
            if deep_url:
                # Minimal, non-blocking readiness: press ESC once, close quick announcements, short sleep, return.
                try:
                    print(f"[MiaoshouNavigation] [OK] deep-link chosen: {deep_url} (skip heavy readiness)")
                except Exception:
                    pass
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                try:
                    await page.wait_for_timeout(120)
                except Exception:
                    pass
                return NavigationResult(success=True, url=str(getattr(page, 'url', '')), message="deep-link-fast")

            # Sidebar/menu text candidates (heuristic)
            candidates_map = {
                TargetPage.PRODUCTS_PERFORMANCE: ["商品", "商品表现", "商品分析", "产品"],
                TargetPage.TRAFFIC_OVERVIEW: ["流量", "客流", "数据总览", "概览"],
                TargetPage.SERVICE_ANALYTICS: ["服务", "客服", "聊天", "服务分析"],
                TargetPage.ORDERS: ["订单"],
                TargetPage.FINANCE: ["财务", "结算", "资金"],
            }
            labels = candidates_map.get(target, [])
            navigated = False
            for label in labels:
                try:
                    await page.get_by_text(label, exact=False).first.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    navigated = True
                    break
                except Exception:
                    continue
            if not navigated:
                try:
                    await page.goto(base, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
            return NavigationResult(success=True, url=str(getattr(page, 'url', '')), message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[MiaoshouNavigation] failed: {e}")
            return NavigationResult(success=False, url=str(getattr(page, 'url', '')), message=str(e))
