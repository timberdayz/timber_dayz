"""
Shopee 服务表现（Services）组件配置

集中管理“服务表现”数据域的两个子页面：
- 商店 AI 助手（shop-ai-assistant）
- 人工聊天（agent）

说明：
- URL 与选择器均集中在此处，供导出组件复用
- 如页面语言不同（中文/英文/繁体），可在选择器列表中补充同义项
- 若平台结构升级，仅需更新本文件即可
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List, Tuple, Dict

# 基础域名
BASE_URL: Final[str] = "https://seller.shopee.cn"

# 服务表现两个子页面（按 key 标识）
PAGES: Final[Tuple[Dict[str, str], ...]] = (
    {"key": "ai_assistant", "path": "/datacenter/services/shop-ai-assistant"},
    {"key": "agent", "path": "/datacenter/services/agent"},
)

# 导出按钮（按优先级尝试）
EXPORT_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    'a:has-text("导出")',
    'button:has-text("Export")',
    'button:has-text("Export Data")',
    # 兼容更多主题/结构
    'button:has(span:has-text("导出"))',
    '[data-testid*="export"]',
    '[class*="export"] button',
    '.ant-dropdown-trigger:has(svg)',  # 可能在更多菜单里
)

# 下载按钮（弹窗中的“下载/Download”或直接下载入口）
DOWNLOAD_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("下载")',
    'a:has-text("下载")',
    'button:has-text("Download")',
    '.download-btn',
    'a[download]',
    'a[href*="download"]',
    'a[href*="export"]',
    'button:has([class*="download"])',
)

# 页面就绪探针（表格、统计卡、数据区域等）
DATA_READY_PROBES: Final[Tuple[str, ...]] = (
    "[data-testid*='service']",
    "[data-testid*='chat']",
    ".ant-table",
    ".data-table",
    ".summary-cards",
    'text=AI 助手',
    'text=人工聊天',
)

# 统一导出目录名
DATA_TYPE_DIR: Final[str] = "services"


@dataclass(frozen=True)
class ServicesSelectors:
    """打包的选择器与常量（一次性传入组件）。"""

    base_url: str = BASE_URL
    pages: Tuple[Dict[str, str], ...] = PAGES
    export_buttons: Tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    download_buttons: Tuple[str, ...] = DOWNLOAD_BUTTON_SELECTORS
    data_ready_probes: Tuple[str, ...] = DATA_READY_PROBES
    data_type_dir: str = DATA_TYPE_DIR

