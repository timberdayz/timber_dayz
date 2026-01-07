from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DatePickerComponent, DatePickResult, DateOption


class MiaoshouDatePicker(DatePickerComponent):
    # Component metadata (v4.8.0)
    platform = "miaoshou"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _open_panel(self, page: Any) -> None:
        # Try generic date trigger selectors
        for sel in [
            ".ant-picker-input",
            ".arco-picker-input",
            ".theme-arco-picker-suffix-icon",
            "button:has-text(日期)",
            "[role='button']:has-text(日期)",
        ]:
            try:
                await page.locator(sel).first.click(timeout=1500)
                await page.wait_for_timeout(300)
                return
            except Exception:
                continue
        # Fallback: click any calendar icon
        try:
            await page.locator("svg, i, span").filter(has_text="[DATE]").first.click(timeout=800)
        except Exception:
            pass

    async def _click_option_texts(self, page: Any, candidates: list[str]) -> bool:
        for text in candidates:
            try:
                await page.get_by_text(text, exact=False).first.click(timeout=1200)
                return True
            except Exception:
                continue
        return False

    def _calc_range(self, option: DateOption) -> tuple[str, str]:
        """Return (start, end) strings in 'YYYY-MM-DD HH:MM:SS'."""
        now = datetime.now()
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        if option == DateOption.YESTERDAY:
            y = now - timedelta(days=1)
            start = y.replace(hour=0, minute=0, second=0, microsecond=0)
            end = y.replace(hour=23, minute=59, second=59, microsecond=0)
        elif option == DateOption.LAST_7_DAYS:
            start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif option in (DateOption.LAST_28_DAYS, DateOption.LAST_30_DAYS):
            # 后端通常按30天聚合，保持与现有映射一致
            start = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # 默认近7天
            start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))

    async def _type_range_inputs(self, page: Any, start_str: str, end_str: str) -> bool:
        """Type into Miaoshou jx-date datetimerange inputs directly."""
        try:
            # 通用选择：范围输入框两个
            inputs = page.locator(".jx-date-editor--datetimerange input.jx-range-input")
            if await inputs.count() < 2:
                inputs = page.locator("input.jx-range-input")
            if await inputs.count() < 2:
                return False
            # 开始时间
            s = inputs.nth(0)
            await s.click(timeout=1500)
            try:
                await s.press("Control+A")
            except Exception:
                pass
            await s.fill(start_str, timeout=1500)
            try:
                await s.press("Enter")
            except Exception:
                pass
            await page.wait_for_timeout(120)
            # 结束时间
            e = inputs.nth(1)
            await e.click(timeout=1500)
            try:
                await e.press("Control+A")
            except Exception:
                pass
            await e.fill(end_str, timeout=1500)
            try:
                await e.press("Enter")
            except Exception:
                pass
            await page.wait_for_timeout(120)
            # ESC 关闭面板
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def run(self, page: Any, option: DateOption, apply_to_page: bool = True) -> DatePickResult:  # type: ignore[override]
        try:
            # 仅配置模式：不触碰页面控件，只写入 ctx.config 供后续导出流程使用
            if not apply_to_page:
                try:
                    cfg = self.ctx.config or {}
                    s, e = self._calc_range(option)
                    cfg["start_date"], cfg["end_date"] = s, e
                    self.ctx.config = cfg
                except Exception:
                    pass
                # config-only 模式不打印"selecting"，避免造成步骤错序的观感
                return DatePickResult(success=True, option=option, message="config-only")

            if self.logger:
                self.logger.info(f"[MiaoshouDatePicker] selecting: {option}")
            await self._open_panel(page)
            mapping = {
                DateOption.YESTERDAY: ["昨天"],
                DateOption.LAST_7_DAYS: ["过去7天", "最近7天", "近7天"],
                DateOption.LAST_28_DAYS: ["过去30天", "最近30天", "近30天", "近一个月"],
            }
            ok = await self._click_option_texts(page, mapping.get(option, []))
            # 若无快捷选项可点，直接输入设置
            if not ok:
                start_str, end_str = self._calc_range(option)
                typed = await self._type_range_inputs(page, start_str, end_str)
                ok = typed
            # 将时间范围写回 ctx.config 以便文件命名
            try:
                cfg = self.ctx.config or {}
                s, e = self._calc_range(option)
                cfg["start_date"], cfg["end_date"] = s, e
                self.ctx.config = cfg
            except Exception:
                pass
            return DatePickResult(success=ok, option=option, message="ok" if ok else "not-found")
        except Exception as e:
            return DatePickResult(success=False, option=option, message=str(e))
