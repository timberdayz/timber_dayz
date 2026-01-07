"""
Shopee 商品表现（Products）组件配置

单一入口：只修改本文件即可快速适配商品表现页面的不同布局/语言。

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

# 目标页面（商品表现）深链接
PRODUCTS_PERFORMANCE_PATH: Final[str] = "/datacenter/product/performance"

# 导出弹窗与按钮选择器集合（按优先级从上到下）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    # 精确文本
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    'text=导出数据',
    'text=导出',
    'role=button[name="导出数据"]',
    'role=button[name="导出"]',
    # 右上角/工具栏区域
    '[class*="header"] button:has-text("导出")',
    '[class*="toolbar"] button:has-text("导出")',
    '[class*="action"] button:has-text("导出")',
    # 通用/国际化
    'a:has-text("导出")',
    'button:has-text("Export")',
    'button:has-text("Export Data")',
    'button:has-text("匯出")',  # 繁体
    'button:has-text("Exportar")',  # 西语/葡语
    'button:has-text("Exporter")',  # 法语
    # iframe 内
    'iframe button:has-text("导出")',
    'iframe button:has-text("Export")',
    # 兜底
    '[role="button"]:has-text("导出")',
    '[role="button"]:has-text("Export")',
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    # 精确文本
    'button:has-text("下载")',
    'a:has-text("下载")',
    'button:has-text("Download")',
    # 更具体
    '[class*="download"]:has-text("下载")',
    'button[class*="ant-btn"]:has-text("下载")',
    '.download-btn',
    # 可能的确认按钮
    'button:has-text("确认")',
    'button:has-text("确定")',
    'button:has-text("OK")',
    'button:has-text("Confirm")',
    # 跨语言
    'button:has-text("下載")',
    'button:has-text("Descargar")',
    'button:has-text("Baixar")',
    'button:has-text("Télécharger")',
    # “最新报告/下载列表”面板
    '[class*="report"] button:has-text("下载")',
    '[class*="latest"] button:has-text("下载")',
    '[class*="recent"] button:has-text("下载")',
    '.report-list button:has-text("下载")',
    '.download-list button:has-text("下载")',
    # iframe 内
    'iframe button:has-text("下载")',
    'iframe button:has-text("Download")',
    # 兜底
    '[role="button"]:has-text("下载")',
    '[role="button"]:has-text("Download")',
]

# 表格或图表就绪的探针（用于在点击导出前确认页面加载完毕）
DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='product']",
    "[data-testid*='performance']",
    ".product-table",
    ".ant-table",
    ".performance-chart",
    ".data-table",
]

# 常见通知/升级提示弹窗的关闭按钮选择器（按优先级）
POPUP_CLOSE_SELECTORS: Final[List[str]] = [
    '.ant-modal-close',
    'button:has-text("我知道了")',
    'button:has-text("知道了")',
    'button:has-text("关闭")',
    'button:has-text("OK")',
    'button:has-text("Confirm")',
    '[aria-label="Close"]',
]

# 统一导出子目录名
DATA_TYPE_DIR: Final[str] = "products"


@dataclass(frozen=True)
class ProductsSelectors:
    """打包的选择器与常量（便于一次性传入组件）。"""

    base_url: str = BASE_URL
    performance_path: str = PRODUCTS_PERFORMANCE_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]
    popup_close_buttons: List[str] = tuple(POPUP_CLOSE_SELECTORS)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR
