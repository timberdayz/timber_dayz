"""Miaoshou ERP 仓库清单 inventory 数据域导出组件（V2 canonical 独立精细类）

流程:
  navigation → 仓库全选 → 搜索 → 等待结果 → 导出菜单 → 字段全选 → 触发导出 → page.expect_download → 落盘
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.components.export.base import (
    ExportComponent,
    ExportMode,
    ExportResult,
    build_standard_output_root,
)
from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.components.structured_error import (
    StructuredError,
    build_stage_error_message,
)
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_filters import (
    MiaoshouWarehouseFilters,
)
from modules.utils.path_sanitizer import build_filename

# 失败诊断用的「定位信号」名（《规范》§3.5.1 结构化上下文的 matched_signal）。
# 记录的是当时命中的定位信号/选择器候选名，不是具体 DOM 节点。
SIGNAL_NAVIGATION_ROUTE = "warehouse_checklist_route"
SIGNAL_POPUP_CLOSE = "popup_close_buttons"
SIGNAL_WAREHOUSE_SCOPE = "warehouse_scope_select"
SIGNAL_SEARCH_BUTTON = "role:button:搜索"
SIGNAL_EXPORT_DIALOG = "选择导出字段"
SIGNAL_EXPORT_DOWNLOAD = "page.expect_download"


# ── 模块级实现 ───────────────────────────────────────────────────────
# 组件类的行数上限是 500 行（docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md §9），
# 而本组件的流程较长；因此把「导出弹窗交互」「下载竞速守卫」等纯实现细节放在
# 模块级函数里，类只保留编排与阶段语义。


async def _first_visible_selector(
    page: Any, selectors: tuple[str, ...], *, timeout: int = 1500
) -> tuple[str, Any] | None:
    """返回第一个可见的选择器及其 locator（供点击前重建 locator 用）。"""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            return selector, locator
        except Exception:
            continue
    return None


async def _is_checkbox_selected(locator: Any) -> bool:
    """判定复选框是否处于勾选态（aria-checked / class 含 checked / input:checked）。"""
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


async def _export_dialog(page: Any) -> Any:
    """定位「选择导出字段」弹窗（每次调用都重新定位，不缓存 locator）。"""
    candidates = [
        page.get_by_role("dialog").filter(has_text="选择导出字段").last,
        page.locator('.jx-overlay[style*="display: block"]')
        .filter(has_text="选择导出字段")
        .last,
        page.locator(".jx-dialog:visible").filter(has_text="选择导出字段").last,
    ]
    for dialog in candidates:
        try:
            await dialog.wait_for(state="visible", timeout=3000)
            return dialog
        except Exception:
            continue
    raise RuntimeError("选择导出字段弹窗不可见")


async def _wait_visible(locator: Any, *, timeout: int = 3000) -> bool:
    """locator 在超时内是否可见（等待失败只算「不可见」，不算异常）。"""
    visible = True
    try:
        await locator.wait_for(state="visible", timeout=timeout)
    except Exception:
        # 不可见属于「检测结果」而非错误：交由调用方产出可诊断信息
        visible = False
    return visible


async def _detect_open_export_menu_source(
    page: Any, sel: InventorySelectors
) -> str | None:
    """判定「导入/导出商品」按钮的定位来源。

    返回 ``"role"``（role 定位命中）或命中的 CSS 选择器；都不可见时返回 None。
    """
    if await _wait_visible(page.get_by_role("button", name="导入/导出商品").first):
        return "role"
    found = await _first_visible_selector(page, sel.open_export_menu, timeout=3000)
    return found[0] if found else None


def _open_export_menu_locator(page: Any, source: str) -> Any:
    """按定位来源重建「导入/导出商品」按钮 locator。"""
    if source == "role":
        return page.get_by_role("button", name="导入/导出商品").first
    return page.locator(source).first


async def _detect_export_searched_item_source(
    page: Any, sel: InventorySelectors
) -> str | None:
    """判定「导出搜索的商品」菜单项的定位来源。"""
    if await _wait_visible(page.get_by_role("menuitem", name="导出搜索的商品").first):
        return "role"
    found = await _first_visible_selector(page, sel.menu_export_searched, timeout=3000)
    return found[0] if found else None


def _export_searched_item_locator(page: Any, source: str) -> Any:
    """按定位来源重建「导出搜索的商品」菜单项 locator。"""
    if source == "role":
        return page.get_by_role("menuitem", name="导出搜索的商品").first
    return page.locator(source).first


async def _ensure_group_check_all_selected(page: Any, sel: InventorySelectors) -> None:
    """把第一个字段分组的「全选」勾上（重新定位弹窗，不跨步骤持有 locator）。"""
    dialog = await _export_dialog(page)
    check_all_text = sel.group_check_all_text
    full_select = dialog.get_by_role("checkbox", name=check_all_text).first
    try:
        await full_select.wait_for(state="visible", timeout=1500)
    except Exception:
        full_select = dialog.locator(
            f"label:has-text('{check_all_text}') input[type='checkbox']"
        ).first
        await full_select.wait_for(state="attached", timeout=1500)

    checked = await _is_checkbox_selected(full_select)
    if not checked:
        try:
            await dialog.get_by_text(check_all_text, exact=True).first.click(
                timeout=1000
            )
        except Exception:
            await full_select.click(timeout=1000)


def _collect_pageerror_payload(error: Any) -> dict[str, Any]:
    """提取 pageerror 的定位信息（stack / filename / lineno / colno / name）。"""
    return {
        "error": str(error),
        "name": getattr(error, "name", None),
        "stack": getattr(error, "stack", None),
        "filename": getattr(error, "filename", None)
        or getattr(error, "fileName", None),
        "lineno": getattr(error, "lineno", None) or getattr(error, "lineNumber", None),
        "colno": getattr(error, "colno", None) or getattr(error, "columnNumber", None),
    }


def _format_pageerror_message(payload: dict[str, Any]) -> str:
    """pageerror 先到时的报错文案（含 filename/lineno/colno/name/stack）。"""
    return (
        f"export aborted by pageerror: filename={payload['filename']!r} "
        f"lineno={payload['lineno']} colno={payload['colno']} "
        f"name={payload['name']!r} stack={payload['stack']!r}"
    )


async def _cancel_pending_tasks(tasks: Any) -> None:
    """取消并回收挂起任务（吞掉取消异常）。"""
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def _download_triggering_export(page: Any, trigger: Any) -> Any:
    """在 expect_download 上下文里触发导出，返回下载对象。"""
    async with page.expect_download(timeout=180000) as dl_info:
        await trigger(page)
    return await dl_info.value


async def _wait_download_or_pageerror(
    download_task: Any,
    pageerror_task: Any,
    pageerror_payload: list[dict[str, Any]],
) -> Any:
    """谁先到谁赢：download 先到则返回它，pageerror 先到则抛 RuntimeError。"""
    done, pending = await asyncio.wait(
        {download_task, pageerror_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    await _cancel_pending_tasks(pending)

    if download_task in done:
        return download_task.result()
    # pageerror 赢了 — cancel download_task 后再 cancel 一次确保清理
    if not download_task.done():
        download_task.cancel()
        await _cancel_pending_tasks([download_task])
    raise RuntimeError(_format_pageerror_message(pageerror_payload[0]))


class MiaoshouInventoryExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "inventory"

    # 采集阶段名（写进步骤日志的 details.step_id，前端 getStepLabel 依赖它）
    STAGE_NAVIGATION_READY = "navigation_ready"
    STAGE_POPUP_CLEARED = "popup_cleared"
    STAGE_WAREHOUSE_SCOPE_READY = "warehouse_scope_ready"
    STAGE_SEARCH_RESULTS_READY = "search_results_ready"
    STAGE_EXPORT_DIALOG_READY = "export_dialog_ready"
    STAGE_DOWNLOAD_SAVED = "download_saved"

    def __init__(
        self, ctx: ExecutionContext, selectors: InventorySelectors | None = None
    ) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.warehouse_filters_component = MiaoshouWarehouseFilters(ctx, self.sel)
        # 当前阶段名：失败时用它给步骤日志一个准确的 step_id
        self._current_stage = self.STAGE_NAVIGATION_READY
        # 阶段失败时已经落盘的截图（避免 run() 结束时重复截图）
        self._failure_screenshot: str | None = None

    def _current_url(self, page: Any) -> str:
        """取当前页面 URL（取不到就留空字符串，不得抛）。"""
        return str(getattr(page, "url", "") or "")

    async def _stage_error(
        self,
        page: Any,
        *,
        prefix: str,
        stage: str,
        reason: str,
        matched_signal: str = "",
    ) -> RuntimeError:
        """构造带结构化字段的阶段失败异常（《规范》§3.5.1）。

        失败前缀（``prefix``）保持既有文案不变，后面追加结构化字段：
        stage / status / reason / current_url / matched_signal / screenshot_path。
        """
        screenshot_path = await self._capture_failure_screenshot(page, stage)
        self._failure_screenshot = screenshot_path
        structured = StructuredError(
            stage=stage,
            status="failed",
            reason=reason,
            current_url=self._current_url(page),
            matched_signal=matched_signal,
            screenshot_path=screenshot_path or "",
        )
        return RuntimeError(build_stage_error_message(prefix, structured))

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
        await page.get_by_text("SKU总数", exact=False).first.wait_for(
            state="visible", timeout=15000
        )
        await page.get_by_text("库存总价值", exact=False).first.wait_for(
            state="visible", timeout=15000
        )
        await page.get_by_role("button", name="导入/导出商品").first.wait_for(
            state="visible", timeout=15000
        )

    async def _open_export_dialog(self, page: Any) -> None:
        """打开导出菜单 → 点「导出搜索的商品」→ 等弹窗可见。

        每个交互都在**点击前重新定位**（不跨步骤持有 locator，《规范》§13.3）。
        """
        await self._click_open_export_menu(page)
        await self._click_export_searched_item(page)
        await _export_dialog(page)

    async def _click_open_export_menu(self, page: Any) -> None:
        """点开「导入/导出商品」按钮（点击前重新定位）。"""
        source = await _detect_open_export_menu_source(page, self.sel)
        if source is None:
            raise RuntimeError("导入/导出商品按钮不可见")
        await _open_export_menu_locator(page, source).click(timeout=1500)

    async def _click_export_searched_item(self, page: Any) -> None:
        """点「导出搜索的商品」菜单项（点击前重新定位）。"""
        source = await _detect_export_searched_item_source(page, self.sel)
        if source is None:
            raise RuntimeError("导出搜索的商品菜单项不可见")
        await _export_searched_item_locator(page, source).click(timeout=1500)

    async def _ensure_export_fields_all_selected(self, page: Any) -> None:
        """把导出弹窗里各字段分组的「全选」都勾上。"""
        dialog = await _export_dialog(page)
        for title in self.sel.group_titles:
            await dialog.get_by_text(title, exact=False).first.wait_for(
                state="visible", timeout=5000
            )

        checkboxes = dialog.get_by_role("checkbox", name=self.sel.group_check_all_text)
        count = await checkboxes.count()
        if count < 2:
            raise RuntimeError("导出字段全选复选框数量不足")

        await _ensure_group_check_all_selected(page, self.sel)

        # 关键交互前重新定位：弹窗可能因勾选动作被重渲染（《规范》§13.3）
        dialog = await _export_dialog(page)
        second_checkbox = dialog.get_by_role(
            "checkbox", name=self.sel.group_check_all_text
        ).nth(1)
        if not await _is_checkbox_selected(second_checkbox):
            try:
                await second_checkbox.click(timeout=1000)
            except Exception:
                second_label = dialog.get_by_text(
                    self.sel.group_check_all_text, exact=True
                ).nth(1)
                await second_label.click(timeout=1000)

    async def _trigger_export(self, page: Any) -> None:
        dialog = await _export_dialog(page)
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
                await page.get_by_text(text, exact=False).first.wait_for(
                    state="visible", timeout=3000
                )
                return
            except Exception:
                continue
        raise RuntimeError("未检测到导出进度提示")

    async def _wait_download_complete(self, page: Any, download: Any) -> Path:
        try:
            await self._wait_export_progress_ready(page)
        except Exception:
            pass

        out_root = build_standard_output_root(
            self.ctx, data_type=self.sel.data_type_dir, granularity="snapshot"
        )
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = (
            getattr(download, "suggested_filename", None)
            or f"{self.sel.data_type_dir}_snapshot.xlsx"
        )
        tmp_path = out_root / raw_name
        await download.save_as(str(tmp_path))

        if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
            raise RuntimeError("download file missing or empty")

        account = self.ctx.account or {}
        cfg = self.ctx.config or {}
        account_label = (
            account.get("label")
            or account.get("store_name")
            or account.get("username")
            or "unknown"
        )
        shop_name = cfg.get("shop_name") or account.get("store_name") or "unknown_shop"
        target = out_root / build_filename(
            ts=datetime.now().strftime("%Y%m%d_%H%M%S"),
            account_label=account_label,
            shop_name=shop_name,
            data_type=self.sel.data_type_dir,
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

    async def _expect_download_with_pageerror_guard(self, page: Any) -> Any:
        """Race ``page.expect_download`` against ``pageerror`` event (ID=621 fix).

        ID=621 (2026-09-14 19:32:33 UTC, 253s, failed): ``/warehouse/checklist``
        页面 JS 抛 pageerror 后，``expect_download(timeout=180000)`` 仍干等 180s
        才超时，浪费 253s。本实现：

          1. 注册 pageerror listener，捕获 stack/filename/lineno/colno/name
          2. ``asyncio.create_task`` 启动 expect_download 和 pageerror.wait()
          3. ``asyncio.wait(..., return_when=FIRST_COMPLETED)`` — 谁先到谁赢
          4. pageerror 先到：cancel expect_download task + 抛 RuntimeError
             （message 包含 filename/lineno/colno/name/stack）
          5. download 先到：cancel pageerror task + return download
          6. ``finally`` 清理 pageerror listener（避免重复运行累积）

        Raises:
            RuntimeError: pageerror fired before download.
            asyncio.TimeoutError: expect_download timed out (180s).
        """
        pageerror_event = asyncio.Event()
        pageerror_payload: list[dict[str, Any]] = []

        def _on_pageerror(error: Any) -> None:
            if pageerror_event.is_set():
                return
            pageerror_payload.append(_collect_pageerror_payload(error))
            pageerror_event.set()

        page.on("pageerror", _on_pageerror)
        try:
            download_task = asyncio.create_task(
                _download_triggering_export(page, self._trigger_export)
            )
            pageerror_task = asyncio.create_task(pageerror_event.wait())
            try:
                return await _wait_download_or_pageerror(
                    download_task, pageerror_task, pageerror_payload
                )
            except BaseException:
                if not download_task.done():
                    download_task.cancel()
                raise
        finally:
            try:
                page.remove_listener("pageerror", _on_pageerror)
            except Exception:
                pass

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        self._failure_screenshot = None
        try:
            await self._navigate_to_warehouse_checklist(page)
            await self._select_warehouse_scope(page)
            await self._search_and_wait(page)
            await self._open_export_dialog_and_select_all(page)
            target = await self._export_and_save(page)
            return ExportResult(
                success=True, message="download complete", file_path=str(target)
            )
        except Exception as e:
            screenshot_path = (
                self._failure_screenshot
                or await self._capture_failure_screenshot(page, "export")
            )
            message = str(e)
            if screenshot_path:
                message = f"{message} (screenshot: {screenshot_path})"
            await self.report_step(
                "step_failed",
                step_id=self._current_stage,
                action="导出流程失败",
                error=message,
                screenshot_path=screenshot_path or "",
            )
            return ExportResult(success=False, message=message, file_path=None)

    async def _navigate_to_warehouse_checklist(self, page: Any) -> None:
        self._current_stage = self.STAGE_NAVIGATION_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_NAVIGATION_READY, action="导航到仓库清单"
        )
        nav_result = await self.navigation_component.run(
            page, TargetPage.WAREHOUSE_CHECKLIST
        )
        if not nav_result.success:
            raise await self._stage_error(
                page,
                prefix="navigation_failed",
                stage=self.STAGE_NAVIGATION_READY,
                reason=nav_result.message or "navigation failed",
                matched_signal=SIGNAL_NAVIGATION_ROUTE,
            )
        await self.report_step(
            "step_success", step_id=self.STAGE_NAVIGATION_READY, action="已到仓库清单"
        )

        # 弹窗清理的**生产主责不在组件**：执行器在每域导出前调 close_popups，
        # navigation 内部已有 stabilize_safe_notices 调用。组件侧这一份
        # _ensure_popup_closed 是历史重复实现，收回统一机制属 L4-2（批次 4）。
        # 本批次只保留调用（删掉会改变行为），并如实记录阶段事件。
        self._current_stage = self.STAGE_POPUP_CLEARED
        try:
            await self._ensure_popup_closed(page)
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="popup_cleanup_failed",
                stage=self.STAGE_POPUP_CLEARED,
                reason=str(e),
                matched_signal=SIGNAL_POPUP_CLOSE,
            )
            raise error from e
        await self.report_step(
            "step_success",
            step_id=self.STAGE_POPUP_CLEARED,
            action="弹窗清理阶段结束",
        )

    async def _select_warehouse_scope(self, page: Any) -> None:
        self._current_stage = self.STAGE_WAREHOUSE_SCOPE_READY
        await self.report_step(
            "step_start",
            step_id=self.STAGE_WAREHOUSE_SCOPE_READY,
            action="仓库范围筛选",
        )
        filter_result = await self.warehouse_filters_component.run(
            page, {"select_all": True}
        )
        if not filter_result.success:
            raise await self._stage_error(
                page,
                prefix="warehouse_scope_failed",
                stage=self.STAGE_WAREHOUSE_SCOPE_READY,
                reason=filter_result.message or "warehouse filters failed",
                matched_signal=SIGNAL_WAREHOUSE_SCOPE,
            )
        await self.report_step(
            "step_success",
            step_id=self.STAGE_WAREHOUSE_SCOPE_READY,
            action="仓库范围已全选",
        )

    async def _search_and_wait(self, page: Any) -> None:
        self._current_stage = self.STAGE_SEARCH_RESULTS_READY
        await self.report_step(
            "step_start",
            step_id=self.STAGE_SEARCH_RESULTS_READY,
            action="搜索并等待结果",
        )
        try:
            await self._click_search(page)
            await self._wait_search_results_ready(page)
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="search_failed",
                stage=self.STAGE_SEARCH_RESULTS_READY,
                reason=str(e),
                matched_signal=SIGNAL_SEARCH_BUTTON,
            )
            raise error from e
        await self.report_step(
            "step_success",
            step_id=self.STAGE_SEARCH_RESULTS_READY,
            action="搜索结果就绪",
        )

    async def _open_export_dialog_and_select_all(self, page: Any) -> None:
        self._current_stage = self.STAGE_EXPORT_DIALOG_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_EXPORT_DIALOG_READY, action="打开导出弹窗"
        )
        try:
            await self._open_export_dialog(page)
            await self._ensure_export_fields_all_selected(page)
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="export_dialog_failed",
                stage=self.STAGE_EXPORT_DIALOG_READY,
                reason=str(e),
                matched_signal=SIGNAL_EXPORT_DIALOG,
            )
            raise error from e
        await self.report_step(
            "step_success",
            step_id=self.STAGE_EXPORT_DIALOG_READY,
            action="导出字段已全选",
        )

    async def _export_and_save(self, page: Any) -> Path:
        self._current_stage = self.STAGE_DOWNLOAD_SAVED
        await self.report_step(
            "step_start", step_id=self.STAGE_DOWNLOAD_SAVED, action="触发导出并落盘"
        )
        try:
            download = await self._expect_download_with_pageerror_guard(page)
            target = await self._wait_download_complete(page, download)
        except Exception as e:
            error = await self._stage_error(
                page,
                prefix="download_failed",
                stage=self.STAGE_DOWNLOAD_SAVED,
                reason=str(e),
                matched_signal=SIGNAL_EXPORT_DOWNLOAD,
            )
            raise error from e
        await self.report_step(
            "step_success", step_id=self.STAGE_DOWNLOAD_SAVED, action="文件已落盘"
        )
        return target

    async def _capture_failure_screenshot(self, page: Any, stage: str) -> str | None:
        """失败时截图落盘到 ctx.config['task']['screenshot_dir']（对齐 TikTok products_export）。

        截图失败不得影响主流程。
        """
        screenshot_dir = ""
        config = self.ctx.config or {}
        task_cfg = config.get("task") if isinstance(config, dict) else None
        if isinstance(task_cfg, dict):
            screenshot_dir = str(task_cfg.get("screenshot_dir") or "")
        if not screenshot_dir:
            return None

        try:
            target_dir = Path(screenshot_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = target_dir / f"miaoshou_inventory_{stage}_{stamp}.png"
            await page.screenshot(path=str(path))
            return str(path)
        except Exception as e:
            logger = self.logger
            if logger:
                logger.warning(f"inventory export 截图失败（已忽略）: {e}")
            return None
