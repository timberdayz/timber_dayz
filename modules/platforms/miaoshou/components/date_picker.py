from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption, DatePickResult, DatePickerComponent
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


@dataclass(frozen=True)
class MiaoshouCustomDateRange:
    start_date: str
    end_date: str
    start_time: str = "00:00:00"
    end_time: str = "23:59:59"


class MiaoshouDatePicker(DatePickerComponent):
    platform = "miaoshou"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: OrdersSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or OrdersSelectors()

    async def _open(self, page: Any) -> None:
        trigger = None
        for name in ("开始时间", "结束时间"):
            try:
                candidate = page.get_by_role("combobox", name=name).first
                await candidate.click(timeout=1500)
                trigger = candidate
                break
            except Exception:
                continue
        if trigger is None:
            trigger = page.get_by_text("下单时间", exact=False).first
            await trigger.click(timeout=1500)
        await self._wait_ready(page)

    async def _wait_ready(self, page: Any) -> None:
        shortcut_found = False
        for name in self.sel.date_shortcuts:
            try:
                locator = page.get_by_role("button", name=name).first
                await locator.wait_for(state="visible", timeout=5000)
                shortcut_found = True
                break
            except Exception:
                continue
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

    async def apply_custom_range(self, page: Any, date_range: MiaoshouCustomDateRange) -> DatePickResult:
        await self._open(page)
        await self._fill_input_by_name(page, "开始日期", date_range.start_date)
        await self._fill_input_by_name(page, "开始时间", date_range.start_time)
        await self._fill_input_by_name(page, "结束日期", date_range.end_date)
        await self._fill_input_by_name(page, "结束时间", date_range.end_time)
        await page.get_by_role("button", name="确定").first.click(timeout=1000)
        return DatePickResult(success=True, message="ok", option=DateOption.YESTERDAY)

    async def run(self, page: Any, option: DateOption) -> DatePickResult:  # type: ignore[override]
        await self._open(page)
        preset_map = {
            DateOption.TODAY_REALTIME: "今天",
            DateOption.YESTERDAY: "昨天",
            DateOption.LAST_7_DAYS: "近7天",
            DateOption.LAST_28_DAYS: "近30天",
            DateOption.LAST_30_DAYS: "近30天",
        }
        label = preset_map.get(option, "昨天")
        button = page.get_by_role("button", name=label).first
        await button.wait_for(state="visible", timeout=5000)
        await button.click(timeout=1000)
        return DatePickResult(success=True, message="ok", option=option)
