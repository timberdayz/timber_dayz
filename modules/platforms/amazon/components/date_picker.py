from __future__ import annotations

from typing import Any
from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DatePickerComponent, DatePickResult, DateOption


class AmazonDatePicker(DatePickerComponent):
    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def run(self, page: Any, option: DateOption) -> DatePickResult:  # type: ignore[override]
        # Skeleton: simply return success; real implementation will interact with UI
        if self.logger:
            self.logger.info(f"[AmazonDatePicker] pick: {option}")
        return DatePickResult(success=True, option=option, message="skeleton")

