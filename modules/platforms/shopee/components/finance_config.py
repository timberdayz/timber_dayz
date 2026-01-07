"""
Shopee 财务表现（Finance）组件配置

单一入口：只修改本文件即可快速适配财务表现页面的不同布局/语言。

说明：
- URL 与选择器均集中在此处，供导航与导出组件复用
- 如页面文案语言不同（英文/繁体等），可补充同义选择器
- 若平台升级导致结构变化，只需更新这里即可
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List
from enum import Enum


class TargetPage(Enum):
    """导航目标页面枚举"""
    PRODUCTS_PERFORMANCE = "products_performance"
    TRAFFIC_OVERVIEW = "traffic_overview"
    ORDERS_PERFORMANCE = "orders_performance"
    FINANCE_OVERVIEW = "finance_overview"


BASE_URL: Final[str] = "https://seller.shopee.cn"

# 目标页面（财务表现）深链接
FINANCE_OVERVIEW_PATH: Final[str] = "/datacenter/finance/overview"

# 导出弹窗与按钮选择器集合（按优先级从上到下）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    'a:has-text("导出")',
    'button:has-text("Export")',
    'button:has-text("Export Data")',
    'button:has-text("导出报表")',
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    'button:has-text("下载")',
    'a:has-text("下载")',
    'button:has-text("Download")',
    '.download-btn',
]

# 表格或图表就绪的探针（用于在点击导出前确认页面加载完毕）
DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='finance']",
    "[data-testid*='settlement']",
    ".finance-table",
    ".ant-table",
    ".settlement-chart",
    ".data-table",
]

# 统一导出子目录名
DATA_TYPE_DIR: Final[str] = "finance"


@dataclass(frozen=True)
class FinanceSelectors:
    """打包的选择器与常量（便于一次性传入组件）。"""

    base_url: str = BASE_URL
    overview_path: str = FINANCE_OVERVIEW_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR
