from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from modules.components.base import ComponentBase, ResultBase


class DateOption(str, Enum):
    TODAY_REALTIME = "today_realtime"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_28_DAYS = "last_28_days"
    LAST_30_DAYS = "last_30_days"


@dataclass
class DatePickResult(ResultBase):
    option: DateOption = DateOption.YESTERDAY


class DatePickerComponent(ComponentBase):
    def run(self, page: Any, option: DateOption) -> DatePickResult:  # type: ignore[override]
        raise NotImplementedError

