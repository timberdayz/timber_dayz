"""
Miaoshou ERP inventory (仓库清单) component config

Centralizes base URL, deep-link paths and key selectors used by
navigation/export. Mirrors the orders_config / purchase_config convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List, Tuple

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
WAREHOUSE_CHECKLIST_PATH: Final[str] = "/warehouse/checklist"

OPEN_EXPORT_MENU_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("导入/导出商品")',
    '[role="button"]:has-text("导入/导出商品")',
    '.operate-side .jx-dropdown button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button:has-text("导入/导出商品")',
    '.pro-button:has-text("导入/导出商品")',
    '[aria-haspopup="menu"]:has-text("导入/导出商品")',
    'button:has-text("导出")',
)

MENU_EXPORT_SEARCHED_SELECTORS: Final[Tuple[str, ...]] = (
    ".J_warehouseChecklistExportSearch",
    '[role="menuitem"]:has-text("导出搜索的商品")',
    "text=导出搜索的商品",
)

GROUP_TITLES: Final[Tuple[str, ...]] = ("商品信息", "其他信息")
GROUP_CHECK_ALL_TEXT: Final[str] = "全选"

EXPORT_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
    ".jx-dialog__body .pro-button:has-text(导出)",
    "button.jx-button.jx-button--primary:has-text(导出)",
    "button.pro-button:has-text(导出)",
)

POPUP_CLOSE_SELECTORS: Final[Tuple[str, ...]] = (
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-notification .anticon-close",
    ".ant-message-notice-close",
    ".ant-popover .ant-popover-close",
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(取消)",
    "button:has-text(OK)",
)

CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

PROGRESS_TEXTS: Final[Tuple[str, ...]] = (
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "导出成功",
    "Generating",
    "Processing",
)

DATA_TYPE_DIR: Final[str] = "inventory"


@dataclass(frozen=True)
class InventorySelectors:
    base_url: str = BASE_URL
    checklist_path: str = WAREHOUSE_CHECKLIST_PATH
    open_export_menu: Tuple[str, ...] = OPEN_EXPORT_MENU_SELECTORS
    menu_export_searched: Tuple[str, ...] = MENU_EXPORT_SEARCHED_SELECTORS
    group_titles: Tuple[str, ...] = GROUP_TITLES
    group_check_all_text: str = GROUP_CHECK_ALL_TEXT
    export_buttons: Tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    popup_close_buttons: Tuple[str, ...] = POPUP_CLOSE_SELECTORS
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: Tuple[str, ...] = PROGRESS_TEXTS
    data_type_dir: str = DATA_TYPE_DIR
