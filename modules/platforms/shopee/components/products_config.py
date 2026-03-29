from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from modules.platforms.shopee.components.business_analysis_common import build_domain_path


EXPORT_BUTTON_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    '[role="button"]:has-text("导出数据")',
    '[role="button"]:has-text("导出")',
)

THROTTLED_TEXTS: Final[tuple[str, ...]] = (
    "点击过快",
    "操作过于频繁",
    "请稍后再试",
)


@dataclass(frozen=True)
class ProductsSelectors:
    overview_path: str = build_domain_path("products")
    export_buttons: tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    throttled_texts: tuple[str, ...] = THROTTLED_TEXTS
