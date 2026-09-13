from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors
from modules.utils.path_sanitizer import build_filename


class MiaoshouInventorySnapshotExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "inventory"

    def __init__(self, ctx: ExecutionContext, selectors: WarehouseSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or WarehouseSelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)

    async def _first_visible_selector(self, page: Any, selectors: tuple[str, ...] | list[str], *, timeout: int = 1500) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                return locator
            except Exception:
                continue
        return None

    async def _is_checkbox_selected(self, locator: Any) -> bool:
        try:
            if await locator.is_checked():
                return True
        except Exception:
            pass

        try:
            checked = await locator.evaluate(
                """el => {
                    const root = el.closest(
                        '[role="checkbox"], label, .ant-checkbox-wrapper, .arco-checkbox, .jx-checkbox, .el-checkbox'
                    ) || el;
                    return root.getAttribute('aria-checked') === 'true'
                        || root.className.includes('checked')
                        || !!root.querySelector('input[type="checkbox"]:checked');
                }"""
            )
            return bool(checked)
        except Exception:
            return False

    async def _wait_overlay_ready(self, page: Any) -> Any:
        candidates = [
            page.get_by_role("tooltip").last,
            page.locator(".el-select-dropdown:visible").last,
            page.locator(".ant-select-dropdown:visible").last,
            page.locator(".jx-select-dropdown:visible").last,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=2000)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库筛选下拉未出现")

    async def _warehouse_scope_trigger(self, page: Any) -> Any:
        candidates = [
            page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first,
            page.get_by_text(re.compile(r"^仓库\\s*:?$", re.IGNORECASE)).first.locator("xpath=following::*[@role='combobox' or self::input][1]"),
            page.get_by_role("combobox").first,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=1500)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库范围筛选器不可见")

    async def _ensure_scope_filter_all_selected(self, page: Any) -> None:
        trigger = await self._warehouse_scope_trigger(page)
        await trigger.click(timeout=1500)
        overlay = await self._wait_overlay_ready(page)

        full_select = overlay.get_by_role("checkbox", name="全选").first
        try:
            await full_select.wait_for(state="visible", timeout=2000)
        except Exception:
            full_select = overlay.locator("label:has-text('全选') input[type='checkbox']").first
            await full_select.wait_for(state="attached", timeout=2000)

        checked = await self._is_checkbox_selected(full_select)
        if not checked:
            try:
                await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
            except Exception:
                await full_select.click(timeout=1000)

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    async def _click_search(self, page: Any) -> None:
        button = page.get_by_role("button", name="搜索").first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("SKU总数", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("库存总价值", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_role("button", name="导入/导出商品").first.wait_for(state="visible", timeout=15000)

    async def _export_dialog(self, page: Any) -> Any:
        candidates = [
            page.get_by_role("dialog").filter(has_text="选择导出字段").last,
            page.locator('.jx-overlay[style*="display: block"]').filter(has_text="选择导出字段").last,
            page.locator('.jx-dialog:visible').filter(has_text="选择导出字段").last,
        ]
        for dialog in candidates:
            try:
                await dialog.wait_for(state="visible", timeout=3000)
                return dialog
            except Exception:
                continue
        raise RuntimeError("选择导出字段弹窗不可见")

    async def _open_export_dialog(self, page: Any) -> None:
        button = page.get_by_role("button", name="导入/导出商品").first
        try:
            await button.wait_for(state="visible", timeout=3000)
        except Exception:
            button = await self._first_visible_selector(page, self.sel.open_export_menu, timeout=3000)
        if button is None:
            raise RuntimeError("导入/导出商品按钮不可见")
        await button.click(timeout=1500)

        menu_item = page.get_by_role("menuitem", name="导出搜索的商品").first
        try:
            await menu_item.wait_for(state="visible", timeout=3000)
        except Exception:
            menu_item = await self._first_visible_selector(page, self.sel.menu_export_searched, timeout=3000)
        if menu_item is None:
            raise RuntimeError("导出搜索的商品菜单项不可见")
        await menu_item.click(timeout=1500)

        await self._export_dialog(page)

    async def _ensure_group_check_all_selected(self, container: Any) -> None:
        full_select = container.get_by_role("checkbox", name="全选").first
        try:
            await full_select.wait_for(state="visible", timeout=1500)
        except Exception:
            full_select = container.locator("label:has-text('全选') input[type='checkbox']").first
            await full_select.wait_for(state="attached", timeout=1500)

        checked = await self._is_checkbox_selected(full_select)
        if not checked:
            try:
                await container.get_by_text("全选", exact=True).first.click(timeout=1000)
            except Exception:
                await full_select.click(timeout=1000)

    async def _ensure_export_fields_all_selected(self, page: Any) -> None:
        dialog = await self._export_dialog(page)
        await dialog.get_by_text("商品信息", exact=False).first.wait_for(state="visible", timeout=5000)
        await dialog.get_by_text("其他信息", exact=False).first.wait_for(state="visible", timeout=5000)

        checkboxes = dialog.get_by_role("checkbox", name="全选")
        count = await checkboxes.count()
        if count < 2:
            raise RuntimeError("导出字段全选复选框数量不足")

        await self._ensure_group_check_all_selected(dialog.locator("xpath=.").first)
        second_checkbox = checkboxes.nth(1)
        if not await self._is_checkbox_selected(second_checkbox):
            try:
                await second_checkbox.click(timeout=1000)
            except Exception:
                second_label = dialog.get_by_text("全选", exact=True).nth(1)
                await second_label.click(timeout=1000)

    async def _trigger_export(self, page: Any) -> None:
        dialog = await self._export_dialog(page)
        button = None
        for selector in self.sel.export_buttons:
            try:
                candidate = dialog.locator(selector).first
                await candidate.wait_for(state="visible", timeout=1000)
                button = candidate
                break
            except Exception:
                continue
        if button is None:
            button = dialog.get_by_role("button", name="导出").first
            await button.wait_for(state="visible", timeout=2000)
        await button.click(timeout=1500)

    async def _wait_export_progress_ready(self, page: Any) -> None:
        for text in self.sel.progress_texts:
            try:
                await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=3000)
                return
            except Exception:
                continue
        raise RuntimeError("未检测到导出进度提示")

    async def _wait_download_complete(self, page: Any, download: Any) -> Path:
        try:
            await self._wait_export_progress_ready(page)
        except Exception:
            pass

        out_root = build_standard_output_root(self.ctx, data_type="inventory", granularity="snapshot")
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = getattr(download, "suggested_filename", None) or "inventory_snapshot.xlsx"
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
            data_type="inventory",
            granularity="snapshot",
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
            nav_result = await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)
            if not nav_result.success:
                raise RuntimeError(nav_result.message or "navigation failed")

            await self._ensure_scope_filter_all_selected(page)
            await self._click_search(page)
            await self._wait_search_results_ready(page)
            await self._open_export_dialog(page)
            await self._ensure_export_fields_all_selected(page)

            async with page.expect_download(timeout=180000) as dl_info:
                await self._trigger_export(page)
            download = await dl_info.value

            target = await self._wait_download_complete(page, download)
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            return ExportResult(success=False, message=str(e), file_path=None)
