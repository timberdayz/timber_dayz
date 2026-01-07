from __future__ import annotations

"""TikTok 服务表现（Service Analytics）配置

- 仅在此维护深链接路径（不含域名）与关键选择器
- 域名统一：seller.tiktokshopglobalselling.com
- 模块导入零副作用
"""
from dataclasses import dataclass
from typing import Final, List

BASE_URL: Final[str] = "https://seller.tiktokshopglobalselling.com"

# 服务表现 Compass 页（仅路径部分）
SERVICE_PATH: Final[str] = "/compass/service-analytics"

EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"导出数据\")",
    "button:has-text(\"导出\")",
    "button:has-text(\"Export\")",
    "[data-testid*='export']",
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"下载\")",
    "a:has-text(\"下载\")",
    "button:has-text(\"Download\")",
    "[data-testid*='download']",
]

DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='service']",
    "table",
    "[role='grid']",
]


@dataclass(frozen=True)
class ServiceSelectors:
    base_url: str = BASE_URL
    service_path: str = SERVICE_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]

