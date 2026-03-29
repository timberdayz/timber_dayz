from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    preset_label,
)


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

BUSINESS_ANALYSIS_ENTRY_SELECTORS: Final[tuple[str, ...]] = (
    'a:has-text("商业分析")',
    'a[href*="/datacenter"]',
)

PRODUCTS_ENTRY_SELECTORS: Final[tuple[str, ...]] = (
    'a:has-text("商品")',
    'a:has-text("商品概览")',
    'a[href*="/datacenter/product/overview"]',
)

SHOP_SWITCH_TRIGGER_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("/")',
    '[role="button"]:has-text("/")',
    '[class*="shop"]:has-text("/")',
    '[class*="shop"]',
)

DATE_PICKER_TRIGGER_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("今天实时")',
    'button:has-text("今日实时")',
    'button:has-text("昨天")',
    'button:has-text("过去7天")',
    'button:has-text("过去30天")',
    '[role="button"]:has-text("昨天")',
    '[role="button"]:has-text("过去7天")',
    '[role="button"]:has-text("过去30天")',
)


@dataclass(frozen=True)
class ProductsSelectors:
    overview_path: str = build_domain_path("products")
    export_buttons: tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    throttled_texts: tuple[str, ...] = THROTTLED_TEXTS
    business_analysis_entries: tuple[str, ...] = BUSINESS_ANALYSIS_ENTRY_SELECTORS
    products_entries: tuple[str, ...] = PRODUCTS_ENTRY_SELECTORS
    shop_switch_triggers: tuple[str, ...] = SHOP_SWITCH_TRIGGER_SELECTORS
    date_picker_triggers: tuple[str, ...] = DATE_PICKER_TRIGGER_SELECTORS

    @property
    def preset_labels(self) -> dict[str, str]:
        return {
            "today_realtime": preset_label("today_realtime"),
            "yesterday": preset_label("yesterday"),
            "last_7_days": preset_label("last_7_days"),
            "last_30_days": preset_label("last_30_days"),
        }

    @property
    def granularity_labels(self) -> dict[str, str]:
        return {
            "daily": granularity_label("daily"),
            "weekly": granularity_label("weekly"),
            "monthly": granularity_label("monthly"),
        }
