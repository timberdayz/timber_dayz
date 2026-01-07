"""
Miaoshou ERP Warehouse (仓库清单) component config

Centralizes base URL, deep-link paths and key selectors used by navigation/export.
This mirrors the Shopee/TikTok *_config.py convention.

Keep import-time side-effects at zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List

# Base URL for Miaoshou ERP
BASE_URL: Final[str] = "https://erp.91miaoshou.com"

# Deep-link path for warehouse checklist
WAREHOUSE_CHECKLIST_PATH: Final[str] = "/warehouse/checklist"

# Buttons on the warehouse page (best-effort, resilient to wording variants)
OPEN_EXPORT_MENU_SELECTORS: Final[List[str]] = [
    # Primary exact text on Miaoshou toolbar
    "button:has-text(导入/导出商品)",
    "[role='button']:has-text(导入/导出商品)",
    # Miaoshou jx-button variants (plain style within operate-side dropdown)
    ".operate-side .jx-dropdown button.jx-button.is-plain:has-text(导入/导出商品)",
    "button.jx-button.is-plain:has-text(导入/导出商品)",
    "button.jx-button:has-text(导入/导出商品)",
    ".pro-button:has-text(导入/导出商品)",
    "[aria-haspopup='menu']:has-text(导入/导出商品)",
    # Fallbacks
    "button:has-text(导出)",
]
MENU_EXPORT_SEARCHED_SELECTORS: Final[List[str]] = [
    "[role='menuitem']:has-text(导出搜索的商品)",
    "text=导出搜索的商品",
]

# iFrame modal where export options are presented
IFRAME_LOCATORS: Final[List[str]] = [
    "iframe[title*='选择导出字段']",
    "iframe",
]

# Inside iFrame: two group headers contain 全选 toggles
GROUP_TITLES: Final[List[str]] = ["商品信息", "其他信息"]
GROUP_CHECK_ALL_TEXT: Final[str] = "全选"

# Confirm/Export buttons inside the modal
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    # Primary
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
    # Dialog-scoped variants
    ".jx-dialog__body .pro-button:has-text(导出)",
    "button.jx-button.jx-button--primary:has-text(导出)",
    "button.pro-button:has-text(导出)",
]

# Optional pop-up close buttons (used by navigation to clear announcements)
POPUP_CLOSE_SELECTORS: Final[List[str]] = [
    # Ant Design family
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-notification .anticon-close",
    ".ant-message-notice-close",
    ".ant-popover .ant-popover-close",
    # Miaoshou jx-dialog family
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    # Text fallbacks
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(取消)",
    "button:has-text(OK)",
]
# Poll strategy for closing popups
CLOSE_POLL_MAX_ROUNDS: Final[int] = 20  # ~6s
CLOSE_POLL_INTERVAL_MS: Final[int] = 300
# Progress texts observed during export
PROGRESS_TEXTS: Final[List[str]] = [
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "Generating",
    "Processing",
]

# Data directory name used by Exporter for output layout
DATA_TYPE_DIR: Final[str] = "warehouse"


@dataclass(frozen=True)
class WarehouseSelectors:
    base_url: str = BASE_URL
    checklist_path: str = WAREHOUSE_CHECKLIST_PATH
    open_export_menu: List[str] = tuple(OPEN_EXPORT_MENU_SELECTORS)  # type: ignore[assignment]
    menu_export_searched: List[str] = tuple(MENU_EXPORT_SEARCHED_SELECTORS)  # type: ignore[assignment]
    iframe_locators: List[str] = tuple(IFRAME_LOCATORS)  # type: ignore[assignment]
    group_titles: List[str] = tuple(GROUP_TITLES)  # type: ignore[assignment]
    group_check_all_text: str = GROUP_CHECK_ALL_TEXT
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    popup_close_buttons: List[str] = tuple(POPUP_CLOSE_SELECTORS)  # type: ignore[assignment]
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: List[str] = tuple(PROGRESS_TEXTS)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR

