from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.utils.path_sanitizer import build_filename


@dataclass(frozen=True)
class CustomDateRange:
    start_date: str
    end_date: str
    start_time: str = "00:00:00"
    end_time: str = "23:59:59"


class MiaoshouOrdersExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "orders"

    def __init__(self, ctx: ExecutionContext, selectors: OrdersSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or OrdersSelectors()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    @staticmethod
    def _build_success_result(message: str, file_path: str) -> ExportResult:
        return ExportResult(success=True, message=message, file_path=file_path)

    @staticmethod
    def _build_error_result(message: str) -> ExportResult:
        return ExportResult(success=False, message=message, file_path=None)

    async def _first_visible(self, page: Any, names: list[str], *, role: str = "button") -> Any | None:
        for name in names:
            try:
                locator = page.get_by_role(role, name=name).first
                await locator.wait_for(state="visible", timeout=1200)
                return locator
            except Exception:
                continue
        return None

    async def _wait_navigation_ready(self, page: Any) -> None:
        await page.get_by_text("利润明细", exact=False).first.wait_for(state="visible", timeout=15000)
        export_btn = await self._first_visible(page, ["导出数据"])
        if export_btn is None:
            raise RuntimeError("导出数据按钮不可见")

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0:
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            await page.wait_for_timeout(self.sel.close_poll_interval_ms)

    async def _ensure_orders_subtype_selected(self, page: Any, subtype: str) -> None:
        label = subtype.strip().capitalize()
        target = page.get_by_text(label, exact=True).first
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

    async def _open_date_picker(self, page: Any) -> None:
        trigger = page.get_by_text("下单时间", exact=False).first
        await trigger.click(timeout=1500)
        await self._wait_date_picker_ready(page)

    async def _wait_date_picker_ready(self, page: Any) -> None:
        shortcut_found = False
        for name in self.sel.date_shortcuts:
            locator = page.get_by_role("button", name=name).first
            if await locator.count() > 0:
                await locator.wait_for(state="visible", timeout=5000)
                shortcut_found = True
                break
        if not shortcut_found:
            raise RuntimeError("日期快捷按钮不可见")
        await page.get_by_role("button", name="确定").first.wait_for(state="visible", timeout=5000)

    async def _fill_input_by_name(self, page: Any, name: str, value: str) -> None:
        locator = page.get_by_role("textbox", name=name).first
        await locator.wait_for(state="visible", timeout=5000)
        await locator.click(timeout=1000)
        try:
            await locator.press("Control+A")
        except Exception:
            pass
        await locator.fill(value, timeout=1500)

    async def _ensure_date_preset_selected(self, page: Any, preset: str) -> None:
        button = page.get_by_role("button", name=preset).first
        await button.wait_for(state="visible", timeout=5000)
        await button.click(timeout=1000)
        await page.get_by_role("button", name="确定").first.click(timeout=1000)

    async def _ensure_custom_date_range_selected(self, page: Any, date_range: CustomDateRange) -> None:
        await self._fill_input_by_name(page, "开始日期", date_range.start_date)
        await self._fill_input_by_name(page, "开始时间", date_range.start_time)
        await self._fill_input_by_name(page, "结束日期", date_range.end_date)
        await self._fill_input_by_name(page, "结束时间", date_range.end_time)
        await page.get_by_role("button", name="确定").first.click(timeout=1000)

    async def _wait_filters_ready(self, page: Any) -> None:
        full_select = page.get_by_role("checkbox", name="全选").first
        await full_select.wait_for(state="visible", timeout=5000)

    async def _ensure_order_statuses_selected(self, page: Any, statuses: list[str] | None = None, *, select_all: bool = True) -> None:
        trigger = page.get_by_role("combobox", name="订单状态 :").first
        await trigger.click(timeout=1500)
        await self._wait_filters_ready(page)
        if select_all:
            full_select = page.get_by_role("checkbox", name="全选").first
            checked = await full_select.is_checked()
            if not checked:
                await full_select.click(timeout=1000)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return

        for status in statuses or []:
            box = page.get_by_role("checkbox", name=status).first
            if not await box.is_checked():
                await box.click(timeout=1000)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    async def _click_search(self, page: Any) -> None:
        search_button = await self._first_visible(page, list(self.sel.search_button_texts))
        if search_button is None:
            raise RuntimeError("搜索按钮不可见")
        await search_button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("数据汇总", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("订单信息", exact=False).first.wait_for(state="visible", timeout=15000)

    async def _ensure_export_menu_open(self, page: Any) -> None:
        button = await self._first_visible(page, ["导出数据"])
        if button is None:
            raise RuntimeError("导出数据按钮不可见")
        await button.hover(timeout=1500)
        await page.get_by_role("menuitem", name="导出全部订单").first.wait_for(state="visible", timeout=5000)

    async def _click_export_all_orders(self, page: Any) -> None:
        await page.get_by_role("menuitem", name="导出全部订单").first.click(timeout=1500)

    async def _wait_export_progress_ready(self, page: Any) -> None:
        title = page.get_by_role("heading", name="正在导出").first
        await title.wait_for(state="visible", timeout=10000)
        progress = page.get_by_role("progressbar").first
        await progress.wait_for(state="visible", timeout=10000)

    async def _wait_export_complete(self, page: Any, download: Any) -> Path:
        try:
            await self._wait_export_progress_ready(page)
        except Exception:
            pass

        out_root = build_standard_output_root(self.ctx, data_type="orders", granularity="manual", subtype="shopee")
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
            subtype = str(cfg.get("orders_subtype") or "shopee").strip().lower()
            time_selection = cfg.get("time_selection") or {}
            time_mode = str(time_selection.get("mode") or "").strip().lower()
            date_preset = str(
                time_selection.get("preset")
                or cfg.get("date_preset")
                or ""
            ).strip()
            custom_range = cfg.get("custom_date_range")
            if not custom_range and time_mode == "custom":
                custom_range = {
                    "start_date": time_selection.get("start_date"),
                    "end_date": time_selection.get("end_date"),
                    "start_time": time_selection.get("start_time", "00:00:00"),
                    "end_time": time_selection.get("end_time", "23:59:59"),
                }

            await self._wait_navigation_ready(page)
            await self._ensure_popup_closed(page)
            await self._ensure_orders_subtype_selected(page, subtype)

            await self._open_date_picker(page)
            if custom_range:
                await self._ensure_custom_date_range_selected(
                    page,
                    CustomDateRange(
                        start_date=str(custom_range["start_date"]),
                        end_date=str(custom_range["end_date"]),
                        start_time=str(custom_range.get("start_time", "00:00:00")),
                        end_time=str(custom_range.get("end_time", "23:59:59")),
                    ),
                )
            else:
                await self._ensure_date_preset_selected(page, date_preset or "昨天")

            await self._ensure_order_statuses_selected(page, select_all=True)
            await self._click_search(page)
            await self._wait_search_results_ready(page)

            await self._ensure_export_menu_open(page)
            async with page.context.expect_download(timeout=180000) as dl_info:
                await self._click_export_all_orders(page)
            download = await dl_info.value

            target = await self._wait_export_complete(page, download)
            return self._build_success_result("download complete", str(target))
        except Exception as e:
            return self._build_error_result(str(e))
