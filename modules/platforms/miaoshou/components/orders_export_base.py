from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.date_picker import MiaoshouCustomDateRange, MiaoshouDatePicker
from modules.platforms.miaoshou.components.filters import MiaoshouFilters
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.utils.path_sanitizer import build_filename


@dataclass(frozen=True)
class CustomDateRange:
    start_date: str
    end_date: str
    start_time: str = "00:00:00"
    end_time: str = "23:59:59"


class MiaoshouOrdersExportBase(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "orders"
    sub_domain: str | None = None

    def __init__(self, ctx: ExecutionContext, selectors: OrdersSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or OrdersSelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.date_picker_component = MiaoshouDatePicker(ctx, self.sel)
        self.filters_component = MiaoshouFilters(ctx)

    def _resolved_subtype(self) -> str:
        cfg = self.ctx.config or {}
        return str(cfg.get("orders_subtype") or self.sub_domain or "shopee").strip().lower()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    @staticmethod
    def _build_success_result(message: str, file_path: str) -> ExportResult:
        return ExportResult(success=True, message=message, file_path=file_path)

    @staticmethod
    def _build_error_result(message: str) -> ExportResult:
        return ExportResult(success=False, message=message, file_path=None)

    @staticmethod
    def _resolve_preset_option(raw: str | None) -> DateOption:
        value = str(raw or "").strip()
        normalized = value.lower()
        mapping = {
            "今天": DateOption.TODAY_REALTIME,
            "today": DateOption.TODAY_REALTIME,
            "today_realtime": DateOption.TODAY_REALTIME,
            "昨天": DateOption.YESTERDAY,
            "yesterday": DateOption.YESTERDAY,
            "近7天": DateOption.LAST_7_DAYS,
            "last_7_days": DateOption.LAST_7_DAYS,
            "last7days": DateOption.LAST_7_DAYS,
            "近30天": DateOption.LAST_30_DAYS,
            "last_30_days": DateOption.LAST_30_DAYS,
            "last30days": DateOption.LAST_30_DAYS,
            "近60天": DateOption.LAST_30_DAYS,
            "last_60_days": DateOption.LAST_30_DAYS,
        }
        return mapping.get(value, mapping.get(normalized, DateOption.YESTERDAY))

    async def _first_visible(self, page: Any, names: list[str], *, role: str = "button", timeout: int = 1500) -> Any | None:
        for name in names:
            try:
                locator = page.get_by_role(role, name=name).first
                await locator.wait_for(state="visible", timeout=timeout)
                return locator
            except Exception:
                continue
        return None

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            await page.wait_for_timeout(self.sel.close_poll_interval_ms)

    async def _ensure_orders_subtype_selected(self, page: Any, subtype: str) -> None:
        label = subtype.strip().capitalize()
        platform_label = page.get_by_text("平台", exact=True).first
        platform_row = platform_label.locator(
            "xpath=ancestor::*[.//*[@role='radiogroup']][1]"
        ).first
        target = platform_row.get_by_text(label, exact=True).first
        await target.wait_for(state="visible", timeout=5000)
        try:
            checked = await target.evaluate(
                """el => {
                    const root = el.closest('[role="radio"], label, .ant-radio-wrapper, .jx-radio, .arco-radio');
                    if (!root) return false;
                    return root.getAttribute('aria-checked') === 'true'
                        || root.className.includes('checked')
                        || !!root.querySelector('input[type="radio"]:checked');
                }"""
            )
        except Exception:
            checked = False
        if not checked:
            await target.click(timeout=1500)

    async def _click_search(self, page: Any) -> None:
        search_button = await self._first_visible(page, list(self.sel.search_button_texts))
        if search_button is None:
            raise RuntimeError("搜索按钮不可见")
        await search_button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("数据汇总", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("订单信息", exact=False).first.wait_for(state="visible", timeout=15000)

    async def _ensure_export_menu_open(self, page: Any) -> None:
        button = await self._first_visible(page, list(self.sel.export_button_texts))
        if button is None:
            raise RuntimeError("导出数据按钮不可见")
        try:
            await button.click(timeout=1500)
        except Exception:
            await button.hover(timeout=1500)
        await page.get_by_role("menuitem", name="导出全部订单").first.wait_for(state="visible", timeout=5000)

    async def _click_export_all_orders(self, page: Any) -> None:
        await page.get_by_role("menuitem", name="导出全部订单").first.click(timeout=1500)

    async def _wait_export_progress_ready(self, page: Any) -> None:
        title = page.get_by_role("heading", name="正在导出").first
        await title.wait_for(state="visible", timeout=10000)
        progress = page.get_by_role("progressbar").first
        await progress.wait_for(state="visible", timeout=10000)

    async def _wait_export_complete(self, page: Any, download: Any, *, subtype: str) -> Path:
        try:
            await self._wait_export_progress_ready(page)
        except Exception:
            pass

        out_root = build_standard_output_root(self.ctx, data_type="orders", granularity="manual", subtype=subtype)
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = getattr(download, "suggested_filename", None) or "orders.xlsx"
        tmp_path = out_root / raw_name
        await download.save_as(str(tmp_path))

        if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
            raise RuntimeError("download file missing or empty")

        account = self.ctx.account or {}
        cfg = self.ctx.config or {}
        account_label = account.get("label") or account.get("store_name") or account.get("username") or "unknown"
        shop_name = cfg.get("shop_name") or account.get("store_name") or "unknown_shop"
        target = out_root / build_filename(
            ts=datetime.now().strftime("%Y%m%d_%H%M%S"),
            account_label=account_label,
            shop_name=shop_name,
            data_type="orders",
            granularity="manual",
            start_date=cfg.get("start_date"),
            end_date=cfg.get("end_date"),
            suffix=tmp_path.suffix or ".xlsx",
        )
        try:
            tmp_path.rename(target)
        except Exception:
            if target != tmp_path:
                target.write_bytes(tmp_path.read_bytes())
                tmp_path.unlink(missing_ok=True)

        return target

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            cfg = self.ctx.config or {}
            subtype = self._resolved_subtype()
            cfg.setdefault("orders_subtype", subtype)
            self.ctx.config = cfg

            time_selection = cfg.get("time_selection") or {}
            time_mode = str(time_selection.get("mode") or "").strip().lower()
            date_preset = str(time_selection.get("preset") or "").strip()
            custom_range = cfg.get("custom_date_range")
            if not custom_range and time_mode == "custom":
                custom_range = {
                    "start_date": time_selection.get("start_date"),
                    "end_date": time_selection.get("end_date"),
                    "start_time": time_selection.get("start_time", "00:00:00"),
                    "end_time": time_selection.get("end_time", "23:59:59"),
                }

            await page.goto(
                self._orders_detail_url(subtype),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            nav_result = await self.navigation_component.run(page, TargetPage.ORDERS)
            if not nav_result.success:
                raise RuntimeError(nav_result.message or "navigation failed")
            await self._ensure_popup_closed(page)
            await self._ensure_orders_subtype_selected(page, subtype)

            if custom_range:
                date_result = await self.date_picker_component.apply_custom_range(
                    page,
                    MiaoshouCustomDateRange(
                        start_date=str(custom_range["start_date"]),
                        end_date=str(custom_range["end_date"]),
                        start_time=str(custom_range.get("start_time", "00:00:00")),
                        end_time=str(custom_range.get("end_time", "23:59:59")),
                    ),
                )
            else:
                preset_option = self._resolve_preset_option(date_preset or "昨天")
                date_result = await self.date_picker_component.run(page, preset_option)
            if not date_result.success:
                raise RuntimeError(date_result.message or "date picker failed")

            filter_result = await self.filters_component.run(page, {"select_all": True})
            if not filter_result.success:
                raise RuntimeError(filter_result.message or "filters failed")
            await self._click_search(page)
            await self._wait_search_results_ready(page)

            await self._ensure_export_menu_open(page)
            async with page.expect_download(timeout=180000) as dl_info:
                await self._click_export_all_orders(page)
            download = await dl_info.value

            target = await self._wait_export_complete(page, download, subtype=subtype)
            return self._build_success_result("download complete", str(target))
        except Exception as e:
            return self._build_error_result(str(e))
