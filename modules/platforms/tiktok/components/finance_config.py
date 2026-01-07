from __future__ import annotations

"""TikTok 财务数据（Finance）组件配置

- 深链接路径、关键选择器集中维护；业务层禁止硬编码 URL
- 仅常量与类定义；导入零副作用
- 路径为占位默认值，录制验证后再精准化
"""
from dataclasses import dataclass
from typing import Final, List

BASE_URL: Final[str] = "https://seller.tiktokshopglobalselling.com"

# 财务中心/账单等（仅路径部分；后续按录制结果细化）
FINANCE_PATH: Final[str] = "/finance/overview"

DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='finance']",
    "table",
    "[role='grid']",
]

EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
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

DATA_TYPE_DIR: Final[str] = "finance"


@dataclass(frozen=True)
class FinanceSelectors:
    """财务数据页面的路径与选择器打包"""

    base_url: str = BASE_URL
    finance_path: str = FINANCE_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR

