from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from modules.platforms.shopee.components.business_analysis_common import (
    build_domain_path,
    granularity_label,
    preset_label,
)


EXPORT_BUTTON_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("\u4e0b\u8f7d\u6570\u636e")',
    'button:has-text("\u5bfc\u51fa\u6570\u636e")',
    'button:has-text("\u4e0b\u8f7d")',
    'button:has-text("\u5bfc\u51fa")',
    '[role="button"]:has-text("\u4e0b\u8f7d\u6570\u636e")',
    '[role="button"]:has-text("\u5bfc\u51fa\u6570\u636e")',
    '[role="button"]:has-text("\u4e0b\u8f7d")',
    '[role="button"]:has-text("\u5bfc\u51fa")',
)

THROTTLED_TEXTS: Final[tuple[str, ...]] = (
    "\u70b9\u51fb\u8fc7\u5feb",
    "\u64cd\u4f5c\u8fc7\u4e8e\u9891\u7e41",
    "\u8bf7\u7a0d\u540e\u518d\u8bd5",
)

BUSINESS_ANALYSIS_ENTRY_SELECTORS: Final[tuple[str, ...]] = (
    'a:has-text("\u5546\u4e1a\u5206\u6790")',
    'a[href*="/datacenter"]',
)

ANALYTICS_ENTRY_SELECTORS: Final[tuple[str, ...]] = (
    'a:has-text("\u6d41\u91cf")',
    'a:has-text("\u6d41\u91cf\u6982\u89c8")',
    'a[href*="/datacenter/traffic/overview"]',
)

SHOP_SWITCH_TRIGGER_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("/")',
    '[role="button"]:has-text("/")',
    '[class*="shop"]:has-text("/")',
    '[class*="shop"]',
)

DATE_PICKER_TRIGGER_SELECTORS: Final[tuple[str, ...]] = (
    'button:has-text("\u6628\u5929")',
    'button:has-text("\u8fd17\u5929")',
    'button:has-text("\u8fd130\u5929")',
    'button:has-text("\u6309\u65e5")',
    'button:has-text("\u6309\u5468")',
    'button:has-text("\u6309\u6708")',
    '[role="button"]:has-text("\u6628\u5929")',
    '[role="button"]:has-text("\u8fd17\u5929")',
    '[role="button"]:has-text("\u8fd130\u5929")',
    '[role="button"]:has-text("\u6309\u65e5")',
    '[role="button"]:has-text("\u6309\u5468")',
    '[role="button"]:has-text("\u6309\u6708")',
)


@dataclass(frozen=True)
class AnalyticsSelectors:
    overview_path: str = build_domain_path("analytics")
    export_buttons: tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    throttled_texts: tuple[str, ...] = THROTTLED_TEXTS
    business_analysis_entries: tuple[str, ...] = BUSINESS_ANALYSIS_ENTRY_SELECTORS
    analytics_entries: tuple[str, ...] = ANALYTICS_ENTRY_SELECTORS
    shop_switch_triggers: tuple[str, ...] = SHOP_SWITCH_TRIGGER_SELECTORS
    date_picker_triggers: tuple[str, ...] = DATE_PICKER_TRIGGER_SELECTORS

    @property
    def preset_labels(self) -> dict[str, str]:
        return {
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
