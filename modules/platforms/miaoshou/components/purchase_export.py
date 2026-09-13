"""Miaoshou ERP 采购单 purchase 数据域导出组件（V2 canonical 独立精细类）

异步导出流程:
  1. 导航到 /purchase/goods
  2. 选择状态 Tab（默认"全部"）+ 设置创建日期（MiaoshouDatePicker）
  3. 搜索 + 等待结果就绪
  4. 点击"导入/导出" → 下拉菜单 → "导出全部搜索结果"
  5. 字段选择对话框：三组字段全选
  6. 点击"导出" → 关闭"正在导出"进度弹窗
  7. 导航到 /purchase/export_record
  8. 轮询最新记录直到状态变为"可下载/导出成功"
  9. 点击"下载"链接 → page.expect_download → 落盘
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.date_picker import MiaoshouCustomDateRange, MiaoshouDatePicker
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
from modules.utils.path_sanitizer import build_filename


class MiaoshouPurchaseExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "purchase"

    def __init__(self, ctx: ExecutionContext, selectors: PurchaseSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or PurchaseSelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.date_picker_component = MiaoshouDatePicker(ctx, self.sel)

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
            try:
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def _click_search(self, page: Any) -> None:
        button = page.get_by_role("button", name="搜索").first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("采购单信息", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("商品信息", exact=False).first.wait_for(state="visible", timeout=15000)

    async def _select_status_tab(self, page: Any, tab_name: str = "全部") -> None:
        try:
            tab = page.get_by_role("tab", name=tab_name).first
            await tab.click(timeout=2000)
        except Exception:
            label = page.get_by_text(re.compile(rf"^{re.escape(tab_name)}\s*\(\d+\)$")).first
            await label.click(timeout=2000)

    async def _open_import_export_dropdown(self, page: Any) -> None:
        button = page.get_by_role("button", name="导入/导出").first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _click_export_all_results(self, page: Any) -> None:
        menu_item = page.get_by_role("menuitem", name="导出全部搜索结果").first
        await menu_item.wait_for(state="visible", timeout=10000)
        await menu_item.click(timeout=1500)

    async def _field_dialog(self, page: Any) -> Any:
        dialog = page.get_by_role("dialog").filter(has_text="选择导出字段").last
        await dialog.wait_for(state="visible", timeout=10000)
        return dialog

    async def _select_all_export_fields(self, page: Any) -> None:
        dialog = await self._field_dialog(page)
        for group_name in self.sel.export_field_groups:
            try:
                group_root = dialog.get_by_text(group_name, exact=True).first
                await group_root.wait_for(state="visible", timeout=3000)
                full_select = group_root.locator(
                    "xpath=ancestor::*[1]"
                ).get_by_role("checkbox", name=self.sel.export_field_groups_full_select_text).first
                await full_select.wait_for(state="visible", timeout=2000)
                checked = await full_select.is_checked()
                if not checked:
                    try:
                        await group_root.locator(
                            "xpath=ancestor::*[1]"
                        ).get_by_text(self.sel.export_field_groups_full_select_text, exact=True).first.click(timeout=1000)
                    except Exception:
                        await full_select.click(timeout=1000)
            except Exception:
                continue

    async def _click_export_button_in_dialog(self, page: Any) -> None:
        dialog = await self._field_dialog(page)
        button = dialog.get_by_role("button", name="导出").last
        await button.wait_for(state="visible", timeout=5000)
        await button.click(timeout=1500)

    async def _close_progress_dialog(self, page: Any) -> None:
        try:
            title = page.get_by_role("heading", name=self.sel.progress_dialog_title).first
            await title.wait_for(state="visible", timeout=10000)
        except Exception:
            return

        for close_text in self.sel.close_btn_texts:
            try:
                close_button = page.get_by_role("button", name=close_text).first
                await close_button.wait_for(state="visible", timeout=2000)
                await close_button.click(timeout=1000)
                return
            except Exception:
                continue

    async def _navigate_to_export_record(self, page: Any) -> None:
        await page.goto(
            f"{self.sel.base_url}{self.sel.export_record_path}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.get_by_text("导出记录", exact=False).first.wait_for(state="visible", timeout=15000)
        await self.stabilize_safe_notices(page, label="export-record nav cleanup")

    async def _poll_export_record_until_ready(self, page: Any) -> None:
        deadline_s = self.sel.export_record_poll_timeout_s
        interval_s = self.sel.export_record_poll_interval_s
        elapsed = 0
        while elapsed < deadline_s:
            try:
                first_row = page.locator("table tbody tr").first
                if await first_row.count() > 0 and await first_row.is_visible():
                    row_text = " ".join(((await first_row.text_content()) or "").split())
                    if any(token in row_text for token in self.sel.export_record_row_ready_texts):
                        return
            except Exception:
                pass

            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            await asyncio.sleep(interval_s)
            elapsed += interval_s

        raise RuntimeError(
            f"导出记录轮询超时（{deadline_s}s），未检测到可下载状态"
        )

    async def _click_download_in_export_record(self, page: Any) -> None:
        first_row = page.locator("table tbody tr").first
        download_link = first_row.get_by_role("link", name=re.compile(r"下载")).first
        try:
            await download_link.wait_for(state="visible", timeout=5000)
        except Exception:
            download_link = first_row.get_by_role("button", name=re.compile(r"下载")).first
            await download_link.wait_for(state="visible", timeout=5000)

    async def _trigger_async_export_and_download(self, page: Any) -> Path:
        await self._open_import_export_dropdown(page)
        await self._click_export_all_results(page)
        await self._select_all_export_fields(page)
        await self._click_export_button_in_dialog(page)
        await self._close_progress_dialog(page)
        await self._navigate_to_export_record(page)
        await self._poll_export_record_until_ready(page)

        async with page.expect_download(timeout=180000) as dl_info:
            await self._click_download_in_export_record(page)
        download = await dl_info.value

        out_root = build_standard_output_root(self.ctx, data_type="purchase", granularity="manual")
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = getattr(download, "suggested_filename", None) or "purchase.xlsx"
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
            data_type="purchase",
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
            time_selection = cfg.get("time_selection") or {}
            date_preset = str(time_selection.get("preset") or "").strip()
            custom_range = cfg.get("custom_date_range")

            nav_result = await self.navigation_component.run(page, TargetPage.PURCHASE)
            if not nav_result.success:
                raise RuntimeError(nav_result.message or "navigation failed")

            await self.stabilize_safe_notices(page, label="before-first-action cleanup")
            await self._ensure_popup_closed(page)

            await self._select_status_tab(page, "全部")

            if custom_range:
                date_result = await self.date_picker_component.apply_custom_range(
                    page,
                    MiaoshouCustomDateRange(
                        start_date=str(custom_range.get("start_date")),
                        end_date=str(custom_range.get("end_date")),
                        start_time=str(custom_range.get("start_time", "00:00:00")),
                        end_time=str(custom_range.get("end_time", "23:59:59")),
                    ),
                )
            elif date_preset:
                # NOTE: DateOption 没有 LAST_90_DAYS；只有 LAST_28_DAYS / LAST_30_DAYS。
                # 因此 "近90天" 临时 fallback 到 LAST_30_DAYS，避免 KeyError。
                # 如需真正"近90天"语义，应在 DateOption 枚举中新增 LAST_90_DAYS 值。
                preset_map = {
                    "今天": DateOption.TODAY_REALTIME,
                    "昨天": DateOption.YESTERDAY,
                    "近7天": DateOption.LAST_7_DAYS,
                    "近30天": DateOption.LAST_30_DAYS,
                    "近90天": DateOption.LAST_30_DAYS,
                }
                option = preset_map.get(date_preset, DateOption.LAST_30_DAYS)
                date_result = await self.date_picker_component.run(page, option)
            else:
                date_result = None

            if date_result is not None and not date_result.success:
                raise RuntimeError(date_result.message or "date picker failed")

            await self._click_search(page)
            await self._wait_search_results_ready(page)

            target = await self._trigger_async_export_and_download(page)
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            return ExportResult(success=False, message=str(e), file_path=None)
