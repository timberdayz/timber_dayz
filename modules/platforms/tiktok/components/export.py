from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable
import json

from modules.components.base import ExecutionContext
from modules.components.export.base import (
    ExportComponent,
    ExportResult,
    ExportMode,
    build_standard_output_root,
)
from modules.utils.path_sanitizer import build_filename


class TiktokExporterComponent(ExportComponent):
    """TikTok Shop exporter component."""

    # Component metadata
    platform = "tiktok"
    component_type = "export"
    data_domain = None  # Will be inferred from URL

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _is_clickable(self, el) -> bool:
        """Return True if element appears clickable.
        Criteria: visible and NOT explicitly disabled (aria/attr/class/style).
        Note: Some Arco elements may report is_enabled()=False but still clickable;
        we avoid relying on it.
        """
        try:
            is_vis = await el.is_visible()
        except Exception:
            is_vis = False
        # explicit disabled detection
        try:
            aria_disabled = (await el.get_attribute("aria-disabled") or "").lower() == "true"
            has_disabled_attr = await el.get_attribute("disabled") is not None
            klass = (await el.get_attribute("class") or "").lower()
            # handle both theme-arco-btn-disabled and arco-btn-disabled etc.
            class_disabled = any(sub in klass for sub in ("theme-arco-btn-disabled", "arco-btn-disabled", "is-disabled", " disabled", "-disabled"))
            style_attr = (await el.get_attribute("style") or "").lower()
            style_block = ("pointer-events: none" in style_attr) or ("not-allowed" in style_attr)
        except Exception:
            aria_disabled = False
            has_disabled_attr = False
            class_disabled = False
            style_block = False
        return bool(is_vis and not (aria_disabled or has_disabled_attr or class_disabled or style_block))

    async def _first_click(self, page: Any, selectors: Iterable[str], *, timeout: int = 5000) -> bool:
        """Click the first visible AND enabled element among selectors.
        Avoid clicking greyed/disabled buttons that would never trigger download.
        """
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    first = loc.first
                    try:
                        await first.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    if await self._is_clickable(first):
                        try:
                            await first.hover(timeout=1000)
                        except Exception:
                            pass
                        await first.click(timeout=timeout)
                        return True
            except Exception:
                continue
        return False

    def _write_manifest(self, target: Path, cfg: dict, account_label: str, shop_name: str, data_type: str) -> None:
        try:
            from datetime import datetime
            meta = {
                "platform": getattr(self.ctx, "platform", "tiktok"),
                "account_label": account_label,
                "shop_name": shop_name,
                "shop_id": (self.ctx.config or {}).get("shop_id") or (self.ctx.account or {}).get("shop_id"),
                "region": (self.ctx.account or {}).get("shop_region") or (self.ctx.account or {}).get("region"),
                "data_type": data_type,
                "granularity": (cfg or {}).get("granularity"),
                "start_date": (cfg or {}).get("start_date"),
                "end_date": (cfg or {}).get("end_date"),
                "exported_at": datetime.now().isoformat(),
                "file_path": str(target),
            }
            (Path(str(target) + ".json")).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        """Click "导出数据/Export" and capture download on current TikTok Compass page.

        - 支持商品/流量/服务页面（合并按钮选择器）
        - 输出与命名遵循 Shopee 规则（统一目录结构 + 规范文件名 + manifest）
        """
        try:
            # Load selectors from all tiktok configs
            from modules.platforms.tiktok.components.products_config import ProductsSelectors
            from modules.platforms.tiktok.components.analytics_config import AnalyticsSelectors
            from modules.platforms.tiktok.components.service_config import ServiceSelectors

            products_sel = ProductsSelectors()
            analytics_sel = AnalyticsSelectors()
            service_sel = ServiceSelectors()

            # Merge export/download button selectors (preserve order, remove dups)
            export_buttons = list(
                dict.fromkeys(
                    [
                        *list(products_sel.export_buttons),
                        *list(
                            analytics_sel.EXPORT_BUTTON_SELECTORS
                            if hasattr(analytics_sel, "EXPORT_BUTTON_SELECTORS")
                            else getattr(analytics_sel, "export_buttons", [])
                        ),
                        *list(
                            service_sel.EXPORT_BUTTON_SELECTORS
                            if hasattr(service_sel, "EXPORT_BUTTON_SELECTORS")
                            else getattr(service_sel, "export_buttons", [])
                        ),
                    ]
                )
            ) or list(products_sel.export_buttons)

            download_buttons = list(
                dict.fromkeys(
                    [
                        *list(getattr(products_sel, "download_buttons", [])),
                        *list(
                            getattr(analytics_sel, "DOWNLOAD_BUTTON_SELECTORS", getattr(analytics_sel, "download_buttons", []))
                        ),
                        *list(
                            getattr(service_sel, "DOWNLOAD_BUTTON_SELECTORS", getattr(service_sel, "download_buttons", []))
                        ),
                        # 额外兜底
                        "button:has-text(\"确认\")",
                        "button:has-text(\"确定\")",
                        "button:has-text(\"导出\")",
                        "button:has-text(\"Export\")",
                    ]
                )
            )

            # Optional: wait for page data to be ready (any probe)
            probes = list(
                dict.fromkeys(
                    [
                        *list(getattr(products_sel, "data_ready_probes", [])),
                        *list(getattr(analytics_sel, "DATA_READY_PROBES", getattr(analytics_sel, "data_ready_probes", []))),
                        *list(getattr(service_sel, "DATA_READY_PROBES", getattr(service_sel, "data_ready_probes", []))),
                    ]
                )
            )
            for p in probes:
                try:
                    await page.wait_for_selector(p, timeout=2000, state="visible")
                    break
                except Exception:
                    continue

            if self.logger:
                self.logger.info("[TiktokExporter] clicking export...")
            # service-analytics: switch to "聊天详情" tab to reveal export button
            try:
                _u = str(getattr(page, "url", ""))
            except Exception:
                _u = ""
            if "/service-analytics" in _u:
                switched = False
                for sel in [
                    ".theme-m4b-tabs .theme-arco-tabs-header-title:has(.theme-arco-tabs-header-title-text:has-text(\"聊天详情\"))",
                    ".theme-arco-tabs-header-title:has(span.theme-arco-tabs-header-title-text:has-text(\"聊天详情\"))",
                    "[role='tab']:has-text(\"聊天详情\")",
                    "button:has-text(\"聊天详情\")",
                    "a:has-text(\"聊天详情\")",
                    "text=聊天详情",
                ]:
                    try:
                        await page.locator(sel).first.click(timeout=2500)
                        switched = True
                        break
                    except Exception:
                        continue
                if not switched:
                    try:
                        await page.get_by_role("tab", name="聊天详情").click(timeout=2500)
                        switched = True
                    except Exception:
                        pass
                if switched:
                    try:
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass


            # Before waiting for download, ensure export is available and enabled
            try:
                current_url = str(getattr(page, "url", ""))
            except Exception:
                current_url = ""

            # Probe export button state without clicking; if none clickable on service-analytics, treat as no data and skip
            # Only consider button-like selectors during precheck to avoid matching wrapper spans by "text=..."
            precheck_selectors = [s for s in export_buttons if not s.startswith("text=")]
            has_clickable_export = False
            disabled_found = False
            for sel in precheck_selectors:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        el = loc.first
                        if await self._is_clickable(el):
                            has_clickable_export = True
                            break
                        else:
                            # record disabled state for later decision
                            try:
                                aria_disabled = (await el.get_attribute("aria-disabled") or "").lower() == "true"
                                has_disabled_attr = await el.get_attribute("disabled") is not None
                                klass = (await el.get_attribute("class") or "").lower()
                                style_attr = (await el.get_attribute("style") or "").lower()
                                if (
                                    aria_disabled
                                    or has_disabled_attr
                                    or ("-disabled" in klass or "theme-arco-btn-disabled" in klass or "arco-btn-disabled" in klass)
                                    or ("pointer-events: none" in style_attr)
                                ):
                                    disabled_found = True
                            except Exception:
                                pass
                except Exception:
                    continue

            # Additional page-wide disabled evidence (service analytics often wraps button in span with cursor: not-allowed)
            try:
                page_disabled_probe = page.locator(
                    "button:has-text(\"导出数据\")[disabled], button[disabled]:has-text(\"Export\"), .theme-arco-btn-disabled:has-text(\"导出\"), span[style*='not-allowed'] >> button:has-text(\"导出数据\")"
                )
                if await page_disabled_probe.count() > 0:
                    disabled_found = True
            except Exception:
                pass

            if not has_clickable_export:
                if "/service-analytics" in current_url and disabled_found:
                    msg = "skip: service analytics has no data (export disabled)"
                    if self.logger:
                        self.logger.info(f"[TiktokExporter] {msg}")
                    return ExportResult(success=True, message=msg)
                # 对于其他页面（如商品表现/流量），不做早退，继续尝试点击触发下载

            # Expect download after attempting export click (some pages open a dropdown/modal)
            # 1) Build adaptive timeout
            cfg = self.ctx.config or {}
            try:
                days = int(cfg.get("days") or 0)
            except Exception:
                days = 0
            default_timeout = 90000
            timeout_ms = int(
                cfg.get("export_timeout_ms")
                or (240000 if (cfg.get("one_click") or days >= 28 or str(cfg.get("granularity") or "").lower() == "monthly") else default_timeout)
            )

            # 2) Install global download taps (page + context)
            _latest: dict[str, Any] = {"dl": None}
            def _on_dl(ev):
                try:
                    _latest["dl"] = ev
                except Exception:
                    pass
            try:
                page.on("download", _on_dl)
            except Exception:
                pass
            try:
                page.context.on("download", _on_dl)
            except Exception:
                pass

            download = None
            for attempt in range(2):
                # early exit if global tap already captured
                if _latest.get("dl") is not None:
                    download = _latest.get("dl")
                    break
                try:
                    async with page.expect_download(timeout=timeout_ms) as dl_info:
                        # Now click export and then any confirm/download buttons
                        if not await self._first_click(page, export_buttons, timeout=8000):
                            return ExportResult(success=False, message="export button not found or disabled")
                        try:
                            await page.wait_for_timeout(800)
                        except Exception:
                            pass
                        # Some UIs show a confirm/download step after opening menu/dialog
                        for _ in range(2):
                            if await self._first_click(page, download_buttons, timeout=3000):
                                break
                            try:
                                await page.wait_for_timeout(400)
                            except Exception:
                                pass
                    download = dl_info.value
                    break
                except Exception as ex:
                    # if listener caught the download, use it
                    if _latest.get("dl") is not None:
                        download = _latest.get("dl")
                        break
                    # soft retry once on timeout
                    if attempt == 0 and ("Timeout" in str(ex) or "timeout" in str(ex)):
                        try:
                            await page.wait_for_timeout(800)
                        except Exception:
                            pass
                        continue
                    # propagate other errors or second timeout
                    raise

            if download is None:
                return ExportResult(success=False, message=f"download timeout after {timeout_ms}ms")

            # Infer data_type from URL
            url = str(getattr(page, 'url', ''))
            if "/product-analysis" in url:
                data_type = getattr(products_sel, 'data_type_dir', 'products')
            elif "/data-overview" in url:
                data_type = "traffic"
            elif "/service-analytics" in url:
                data_type = "services"
            else:
                data_type = "unknown"

            # Compute output dir
            cfg = self.ctx.config or {}
            gran = (cfg.get("granularity") or "range").lower()
            out_root: Path = build_standard_output_root(self.ctx, data_type=data_type, granularity=gran)
            out_root.mkdir(parents=True, exist_ok=True)

            # Save to temp then normalize filename
            tmp_name = download.suggested_filename or f"{data_type}.xlsx"
            tmp_path = out_root / tmp_name
            await download.save_as(str(tmp_path))

            # Build normalized filename
            from datetime import datetime as _dt
            account = self.ctx.account or {}
            account_label = account.get("label") or account.get("store_name") or account.get("username") or "unknown"
            # 优先使用上下文中的规范化店铺名（店铺名__区域/代码）
            shop_name = (
                (self.ctx.config or {}).get("shop_name")
                or account.get("menu_display_name")
                or account.get("menu_name")
                or account.get("selected_shop_name")
                or account.get("display_shop_name")
                or account.get("display_name")
                or account.get("store_name")
                or "unknown_shop"
            )
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            target_name = build_filename(
                ts=ts,
                account_label=account_label,
                shop_name=shop_name,
                data_type=data_type,
                granularity=gran,
                start_date=cfg.get("start_date"),
                end_date=cfg.get("end_date"),
                suffix=tmp_path.suffix,
            )
            target = out_root / target_name
            try:
                tmp_path.rename(target)
            except Exception:
                import shutil
                shutil.copy2(tmp_path, target)
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

            # Manifest
            try:
                self._write_manifest(target, cfg, account_label, shop_name, data_type)
            except Exception:
                pass

            if self.logger:
                self.logger.info(f"[TiktokExporter] saved: {target}")
            print(f"\n[OK] 导出成功: {target}")
            return ExportResult(success=True, file_path=str(target), message="ok")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[TiktokExporter] failed: {e}")
            return ExportResult(success=False, message=str(e))
