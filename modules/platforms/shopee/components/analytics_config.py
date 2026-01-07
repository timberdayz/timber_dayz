"""
Shopee 流量表现（Analytics）组件配置

单一入口：只修改本文件即可快速适配不同页面布局/语言。

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
    ORDER_PERFORMANCE = "order_performance"
    FINANCE_PERFORMANCE = "finance_performance"

BASE_URL: Final[str] = "https://seller.shopee.cn"

# 目标页面深链接
TRAFFIC_OVERVIEW_PATH: Final[str] = "/datacenter/traffic/overview"
ORDER_PERFORMANCE_PATH: Final[str] = "/datacenter/order/performance"
FINANCE_PERFORMANCE_PATH: Final[str] = "/datacenter/finance/performance"

# 日期控件及预设选择器
DATE_OPENERS: Final[List[str]] = [
    'div:has-text("统计时间") button',
    'div:has-text("统计时间") .ant-picker-input input',
    '.ant-picker-input input',
]
PRESET_YESTERDAY: Final[List[str]] = [
    'button:has-text("昨天")',
    'div[role="dialog"] >> text=昨天',
    'button:has-text("Yesterday")',
]
PRESET_LAST_7: Final[List[str]] = [
    'button:has-text("过去7天")',
    'button:has-text("近7天")',
    'button:has-text("Last 7 days")',
]
PRESET_LAST_30: Final[List[str]] = [
    'button:has-text("过去30天")',
    'button:has-text("近30天")',
    'button:has-text("Last 30 days")',
]
DATE_APPLY_BUTTONS: Final[List[str]] = [
    'button:has-text("确定")',
    'button:has-text("应用")',
    'button:has-text("Apply")',
]

# 导出弹窗与按钮选择器集合（按优先级从上到下）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    # 基于截图的精确选择器
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    # 文本/Role 兜底
    'text=导出数据',
    'text=导出',
    'role=button[name="导出数据"]',
    'role=button[name="导出"]',

    # 右上角区域的按钮
    '[class*="header"] button:has-text("导出")',
    '[class*="toolbar"] button:has-text("导出")',
    '[class*="action"] button:has-text("导出")',
    # 通用选择器
    'a:has-text("导出")',
    'button:has-text("Export")',
    'button:has-text("Export Data")',
    # 更具体的选择器
    '[class*="export"]:has-text("导出")',
    '[class*="download"]:has-text("导出")',
    'button[class*="ant-btn"]:has-text("导出")',
    # 位置相关选择器
    '[style*="float: right"] button:has-text("导出")',
    '[style*="text-align: right"] button:has-text("导出")',
    # 跨地区差异选择器（英文/繁体/其他语言）
    'button:has-text("匯出")',  # 繁体中文
    'button:has-text("匯出數據")',
    'button:has-text("Exportar")',  # 西班牙语/葡萄牙语
    'button:has-text("Exporter")',  # 法语
    # iframe 内的选择器
    'iframe button:has-text("导出")',
    'iframe button:has-text("Export")',
    # 更宽泛的兜底选择器
    '[role="button"]:has-text("导出")',
    '[role="button"]:has-text("Export")',
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    'button:has-text("下载")',
    'a:has-text("下载")',
    'button:has-text("Download")',
    # 更具体的选择器
    '[class*="download"]:has-text("下载")',
    'button[class*="ant-btn"]:has-text("下载")',
    # 可能的确认按钮
    'button:has-text("确认")',
    'button:has-text("确定")',
    'button:has-text("OK")',
    'button:has-text("Confirm")',
    # 跨地区差异选择器
    'button:has-text("下載")',  # 繁体中文
    'button:has-text("Descargar")',  # 西班牙语
    'button:has-text("Baixar")',  # 葡萄牙语
    'button:has-text("Télécharger")',  # 法语
    # "最新报告"面板相关选择器
    '[class*="report"] button:has-text("下载")',
    '[class*="latest"] button:has-text("下载")',
    '[class*="recent"] button:has-text("下载")',
    '.report-list button:has-text("下载")',
    '.download-list button:has-text("下载")',
    # iframe 内的选择器
    'iframe button:has-text("下载")',
    'iframe button:has-text("Download")',
    # 更宽泛的兜底选择器
    '[role="button"]:has-text("下载")',
    '[role="button"]:has-text("Download")',
]

# 表格或图表就绪的探针（用于在点击导出前确认页面加载完毕）
DATA_READY_PROBES: Final[List[str]] = [
    # 流量相关的数据元素
    "[data-testid*='traffic']",
    "[data-testid*='analytics']",
    "[data-testid*='overview']",
    # 图表组件
    ".analytics-chart",
    ".traffic-chart",
    ".overview-chart",
    ".chart-container",
    "[class*='chart']",
    # 表格组件
    ".ant-table",
    ".data-table",
    ".traffic-table",
    "[class*='table']",
    # 加载状态检测（反向探针 - 这些消失表示加载完成）
    # 注意：这些需要特殊处理，检测它们不可见
    # ".loading", ".spinner", "[class*='loading']",
    # 数据容器
    ".data-container",
    ".content-container",
    "[class*='content']",
    # 特定的流量表现页面元素
    "[class*='traffic-overview']",
    "[class*='analytics-overview']",
    # 图表库特定选择器
    ".echarts-container",
    ".highcharts-container",
    "canvas[data-zr-dom-id]",  # ECharts canvas
    # 更通用的数据就绪探针
    "[data-loaded='true']",
    "[data-ready='true']",
]

# 常见提示/升级通知弹窗的关闭按钮选择器（按优先级）
POPUP_CLOSE_SELECTORS: Final[List[str]] = [
    '.ant-modal-close',
    'button:has-text("我知道了")',
    'button:has-text("知道了")',
    'button:has-text("关闭")',
    'button:has-text("OK")',
    'button:has-text("Confirm")',
    '[aria-label="Close"]',
]

# "最新报告"面板相关选择器（流量表现特有的报告生成机制）
LATEST_REPORTS_PANEL_SELECTORS: Final[List[str]] = [
    # 最新报告面板
    '[class*="latest-report"]',
    '[class*="recent-report"]',
    '[class*="report-panel"]',
    '[class*="report-list"]',
    '.report-history',
    '.download-history',
    # 报告状态检测
    '[class*="report-ready"]',
    '[class*="report-completed"]',
    '[data-status="completed"]',
    '[data-status="ready"]',
    # 报告下载链接
    '[class*="report-download"]',
    '.report-item a',
    '.download-item a',
    # 右侧面板（常见的报告面板位置）
    '.sidebar [class*="report"]',
    '.right-panel [class*="report"]',
    '[class*="side-panel"] [class*="report"]',
]

# 导出完成状态检测选择器
EXPORT_STATUS_SELECTORS: Final[List[str]] = [
    # 成功状态
    '[class*="success"]',
    '[class*="completed"]',
    '[data-status="success"]',
    '[data-status="completed"]',
    # 进度指示器
    '[class*="progress"]',
    '.ant-progress',
    # 状态文本
    'text="导出完成"',
    'text="Export completed"',
    'text="下载就绪"',
    'text="Ready for download"',
    # 通知消息
    '.ant-notification',
    '.ant-message',
    '[class*="notification"]',
    '[class*="toast"]',
]

# 统一导出子目录名
DATA_TYPE_DIR: Final[str] = "traffic"


@dataclass(frozen=True)
class AnalyticsSelectors:
    """打包的选择器与常量（便于一次性传入组件）。"""

    base_url: str = BASE_URL
    overview_path: str = TRAFFIC_OVERVIEW_PATH
    order_path: str = ORDER_PERFORMANCE_PATH
    finance_path: str = FINANCE_PERFORMANCE_PATH

    # 日期相关
    date_openers: List[str] = tuple(DATE_OPENERS)  # type: ignore[assignment]
    preset_yesterday: List[str] = tuple(PRESET_YESTERDAY)  # type: ignore[assignment]
    preset_last7: List[str] = tuple(PRESET_LAST_7)  # type: ignore[assignment]
    preset_last30: List[str] = tuple(PRESET_LAST_30)  # type: ignore[assignment]
    date_apply_buttons: List[str] = tuple(DATE_APPLY_BUTTONS)  # type: ignore[assignment]

    # 导出相关
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]

    # 页面就绪探针
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]

    # 弹窗关闭
    popup_close_buttons: List[str] = tuple(POPUP_CLOSE_SELECTORS)  # type: ignore[assignment]

    # 流量表现特有：最新报告面板与状态检测
    latest_reports_panel: List[str] = tuple(LATEST_REPORTS_PANEL_SELECTORS)  # type: ignore[assignment]
    export_status_selectors: List[str] = tuple(EXPORT_STATUS_SELECTORS)  # type: ignore[assignment]

    # 输出目录名
    data_type_dir: str = DATA_TYPE_DIR

