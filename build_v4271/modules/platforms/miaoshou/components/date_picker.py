from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

    async def _type_range_inputs(self, page: Any, date_range: MiaoshouCustomDateRange) -> bool:
        start_str = f"{date_range.start_date} {date_range.start_time}"
        end_str = f"{date_range.end_date} {date_range.end_time}"
        try:
            inputs = page.locator(".jx-date-editor--datetimerange input.jx-range-input")
            if await inputs.count() < 2:
                inputs = page.locator("input.jx-range-input")
            if await inputs.count() < 2:
                return False

            start_input = inputs.nth(0)
            await start_input.click(timeout=1500)
            try:
                await start_input.press("Control+A")
            except Exception:
                pass
            await start_input.fill(start_str, timeout=1500)
            try:
                await start_input.press("Enter")
            except Exception:
                pass
            await page.wait_for_timeout(120)

            end_input = inputs.nth(1)
            await end_input.click(timeout=1500)
            try:
                await end_input.press("Control+A")
            except Exception:
                pass
            await end_input.fill(end_str, timeout=1500)
            try:
                await end_input.press("Enter")
            except Exception:
                pass
            await page.wait_for_timeout(120)
            return True
        except Exception:
            return False

    async def _read_combobox_value(self, page: Any, name: str) -> str:
        locator = page.get_by_role("combobox", name=name).first
        await locator.wait_for(state="visible", timeout=5000)
        try:
            value = (await locator.input_value()).strip()
            if value:
                return value
        except Exception:
            pass
        try:
            value = (await locator.text_content() or "").strip()
            if value:
                return value
        except Exception:
            pass
        return ""

    @staticmethod
    def _matches_expected_display(actual: str, date_str: str, time_str: str) -> bool:
        normalized = " ".join((actual or "").split())
        if not normalized:
            return False
        if date_str not in normalized:
            return False

        variants = {
            time_str,
            time_str[:5],
        }
        try:
            variants.add(datetime.strptime(time_str, "%H:%M:%S").strftime("%H:%M"))
        except Exception:
            pass
        return any(part and part in normalized for part in variants)

    async def _wait_custom_range_applied(self, page: Any, date_range: MiaoshouCustomDateRange) -> None:
        for _ in range(10):
            start_value = await self._read_combobox_value(page, "开始时间")
            end_value = await self._read_combobox_value(page, "结束时间")
            if self._matches_expected_display(start_value, date_range.start_date, date_range.start_time) and self._matches_expected_display(
                end_value, date_range.end_date, date_range.end_time
            ):
                return
            try:
                await page.wait_for_timeout(200)
            except Exception:
                continue

        raise RuntimeError("自定义时间范围未正确应用")

    async def _click_confirm_if_visible(self, page: Any) -> None:
        try:
            confirm = page.get_by_role("button", name="确定").first
            await confirm.click(timeout=1000)
        except Exception:
            return

    async def apply_custom_range(self, page: Any, date_range: MiaoshouCustomDateRange) -> DatePickResult:
        await self._open(page)
        used_range_inputs = await self._type_range_inputs(page, date_range)
        if not used_range_inputs:
            await self._fill_input_by_name(page, "开始日期", date_range.start_date)
            await self._fill_input_by_name(page, "开始时间", date_range.start_time)
            await self._fill_input_by_name(page, "结束日期", date_range.end_date)
            await self._fill_input_by_name(page, "结束时间", date_range.end_time)
        await self._click_confirm_if_visible(page)
        await self._wait_custom_range_applied(page, date_range)
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
