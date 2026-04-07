"""
Miaoshou ERP orders performance config for the Shopee/TikTok profit-detail page.

This module is import-side-effect free and only defines selectors/constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
ORDER_SUBTYPES: Final[list[str]] = ["shopee", "tiktok"]
DEEP_LINK_TEMPLATE: Final[str] = "/stat/profit_statistics/detail?platform={platform}"

EXPORT_BUTTON_TEXTS: Final[list[str]] = [
    "导出数据",
]

EXPORT_MENU_ITEMS: Final[list[str]] = [
    "导出全部订单",
    "导出所选订单",
    "导出任务记录",
]

EXPORT_PROGRESS_TITLES: Final[list[str]] = [
    "正在导出",
]

EXPORT_PROGRESS_TEXTS: Final[list[str]] = [
    "正在导出订单",
    "正在导出",
    "导出成功,正在下载",
    "导出成功",
    "正在下载",
]

DATE_SHORTCUTS: Final[list[str]] = [
    "今天",
    "昨天",
    "近7天",
    "近30天",
    "近60天",
]

CUSTOM_DATE_INPUT_NAMES: Final[list[str]] = [
    "开始日期",
    "结束日期",
]

CUSTOM_TIME_INPUT_NAMES: Final[list[str]] = [
    "开始时间",
    "结束时间",
]

SEARCH_BUTTON_TEXTS: Final[list[str]] = [
    "搜索",
]

POPUP_CLOSE_SELECTORS: Final[list[str]] = [
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-popover .ant-popover-close",
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    "button:has-text('我知道了')",
    "button:has-text('知道了')",
    "button:has-text('关闭')",
    "button:has-text('确认')",
    "button:has-text('确定')",
    "button:has-text('OK')",
    "button:has-text('取消')",
]

CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

PROGRESS_TEXTS: Final[list[str]] = [
    "导出成功,正在下载",
    "导出成功",
    "正在下载",
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "Generating",
    "Processing",
]

DATA_TYPE_DIR: Final[str] = "orders"


@dataclass(frozen=True)
class OrdersSelectors:
    base_url: str = BASE_URL
    deep_link_template: str = DEEP_LINK_TEMPLATE
    subtypes: tuple[str, ...] = tuple(ORDER_SUBTYPES)

    export_button_texts: tuple[str, ...] = tuple(EXPORT_BUTTON_TEXTS)
    export_menu_items: tuple[str, ...] = tuple(EXPORT_MENU_ITEMS)
    export_progress_titles: tuple[str, ...] = tuple(EXPORT_PROGRESS_TITLES)
    export_progress_texts: tuple[str, ...] = tuple(EXPORT_PROGRESS_TEXTS)
    date_shortcuts: tuple[str, ...] = tuple(DATE_SHORTCUTS)
    custom_date_input_names: tuple[str, ...] = tuple(CUSTOM_DATE_INPUT_NAMES)
    custom_time_input_names: tuple[str, ...] = tuple(CUSTOM_TIME_INPUT_NAMES)
    search_button_texts: tuple[str, ...] = tuple(SEARCH_BUTTON_TEXTS)
    popup_close_buttons: tuple[str, ...] = tuple(POPUP_CLOSE_SELECTORS)
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: tuple[str, ...] = tuple(PROGRESS_TEXTS)
    data_type_dir: str = DATA_TYPE_DIR
