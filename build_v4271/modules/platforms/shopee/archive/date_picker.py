from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DatePickerComponent, DatePickResult, DateOption


class ShopeeDatePicker(DatePickerComponent):
    """Shopee date picker component for data center pages."""

    # Component metadata
    platform = "shopee"
    component_type = "date_picker"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any, option: DateOption) -> DatePickResult:  # type: ignore[override]
        # Thin wrapper leveraging RecipeExecutor
        try:
            from modules.services.recipe_executor import RecipeExecutor
            mapping = {
                DateOption.TODAY_REALTIME: "今日实时",
                DateOption.YESTERDAY: "昨天",
                DateOption.LAST_7_DAYS: "过去7天",
                DateOption.LAST_30_DAYS: "过去30天",
            }
            target = mapping.get(option, "昨天")
            execu = RecipeExecutor()
            ok = await execu.execute_date_picker_recipe(page, target_option=target)
            return DatePickResult(success=bool(ok), option=option, message="ok" if ok else "failed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[ShopeeDatePicker] failed: {e}")
            return DatePickResult(success=False, option=option, message=str(e))

