from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


SERVICE_PATHS: Final[dict[str, str]] = {
    "ai_assistant": "/datacenter/services/shop-ai-assistant",
    "agent": "/datacenter/services/agent",
}

LATEST_REPORT_PANEL_SELECTORS: Final[tuple[str, ...]] = (
    'div:has-text("最新报告")',
    '[class*="report"]:has-text("最新报告")',
    '[class*="popover"]:has-text("最新报告")',
    '[class*="dropdown"]:has-text("最新报告")',
    'body > div:has-text("最新报告")',
)

PANEL_ACTION_TOKENS: Final[tuple[str, ...]] = (
    "下载",
    "进行中",
    "已下载",
)


@dataclass(frozen=True)
class ServicesSelectors:
    service_paths: dict[str, str] = field(default_factory=lambda: dict(SERVICE_PATHS))
    latest_report_panels: tuple[str, ...] = LATEST_REPORT_PANEL_SELECTORS
    panel_action_tokens: tuple[str, ...] = PANEL_ACTION_TOKENS
