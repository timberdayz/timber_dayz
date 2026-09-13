"""Miaoshou ERP 采购单 purchase 数据域导出组件（V2 canonical 独立精细类）

异步导出流程（严格 mirror orders / inventory 模式）:
  1. 导航到 /purchase/goods
  2. 选择状态 Tab（默认"全部"）+ 设置创建日期（MiaoshouDatePicker）
  3. 搜索 + 等待结果就绪
  4. 点击"导入/导出" → 下拉菜单 → "导出全部搜索结果"
  5. 字段选择对话框：三组字段全选
  6. page.expect_download 包裹点击"导出" → 浏览器异步 fire download 事件
     （与 "正在导出包裹" 进度弹窗**完全独立**，弹窗只是用户视觉反馈）
  7. download.save_as 落盘 + build_filename 重命名为标准路径

NOTE: 历史实现曾 navigate 到 /purchase/export_record → poll 表格 → click 下载链接，
连续 3 次生产失败（efd6f74e / 9575d546 / 188176b7 在 ``get_by_text("导出记录")`` 15s 超时）。
改为 orders/inventory 已验证的 ``page.expect_download`` 模式：浏览器在异步导出
完成时直接 fire download 事件，不需要导航到 /export_record 也不需要轮询表格，
**也不需要主动关闭进度弹窗**（download 事件与 UI 状态机解耦）。
"""
from __future__ import annotations

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
        # 等搜索结果表格渲染（"商品信息" 是 row group header，miaoshou 改版后唯一
        # 稳定的列标题信号；早期版本的"采购单信息"已被 miaoshou 移除）。
        # 实测截图（purchase-04-results-ready.png）确认"商品信息"视觉存在。
        await page.get_by_text("商品信息", exact=False).first.wait_for(state="visible", timeout=15000)
        # 等"导入/导出"按钮（与 inventory_export._wait_search_results_ready 设计一致，
        # 确认搜索完成后后续 export 流程可点击）。
        await page.get_by_role("button", name="导入/导出").first.wait_for(state="visible", timeout=15000)

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

    async def _trigger_async_export_and_download(self, page: Any) -> Path:
        """触发异步采购导出并捕获下载（严格 mirror orders / inventory 模式）。

        流程：
          1. 打开"导入/导出"下拉 → 点击"导出全部搜索结果" → 字段全选
          2. ``page.expect_download`` 包裹点击 dialog 内"导出"按钮：
             - 点击瞬间触发后端异步导出
             - 浏览器在异步导出完成、文件就绪时 fire download 事件
             - Playwright ``expect_download`` context 捕获该事件
          3. context 退出时 dl_info.value 即下载文件（xlsx）

        之前的旧设计是 click 导出 → close "正在导出包裹" 进度弹窗 → navigate 到
        /purchase/export_record → poll 表格 → click 下载链接 → expect_download。
        该方案在生产连续失败 3 次（efd6f74e / 9575d546 / 188176b7），全部 timeout
        在 ``get_by_text("导出记录").first to be visible`` 15s。

        严格 mirror orders_export_base (`MiaoshouOrdersExportBase.run:282-284`) 和
        inventory_export (`MiaoshouInventoryExport.run:242-244`) 的 expect_download
        写法——它们也从不在 expect_download context 内关闭进度对话框，因为：
        - download 事件是浏览器 fire 的，与页面 UI 状态完全独立
        - "正在导出包裹" 进度弹窗只是用户视觉反馈，不阻塞 download 捕获
        - 关闭弹窗的 click 操作可能 race condition / 浪费 1-2s 预算
        """
        await self._open_import_export_dropdown(page)
        await self._click_export_all_results(page)
        await self._select_all_export_fields(page)

        # 复用 export_record_poll_timeout_s 作为 expect_download 超时（300s），
        # 语义对齐：等待异步导出完成并触发下载事件的最长等待时间。
        download_timeout_ms = self.sel.export_record_poll_timeout_s * 1000
        async with page.expect_download(timeout=download_timeout_ms) as dl_info:
            await self._click_export_button_in_dialog(page)
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

            # 状态 tab 由 navigation URL 的 ?tab= 参数控制（默认 "all"），
            # 不再依赖 _select_status_tab click —— purchase 状态 tab 用 role="label"
            # 渲染，Playwright actionability 检查会超时。

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
