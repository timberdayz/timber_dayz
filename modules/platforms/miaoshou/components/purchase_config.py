"""
Miaoshou ERP purchase (采购单) component config

Centralizes selectors used by the async-export purchase flow.
Mirrors the orders_config / inventory_config convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Tuple

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
PURCHASE_GOODS_PATH: Final[str] = "/purchase/goods"
PURCHASE_EXPORT_RECORD_PATH: Final[str] = "/purchase/export_record"

STATUS_TABS: Final[Tuple[str, ...]] = (
    "全部",
    "草稿箱",
    "待审核",
    "待收货",
    "已完成",
    "已取消/退货",
)

FILTER_FIELD_NAMES: Final[Tuple[str, ...]] = (
    "采购单号",
    "货源单号",
    "商品SKU",
    "中文名称",
    "收货仓库",
    "供货商",
    "有无物流单号",
    "备注",
    "采购员",
    "创建日期",
    "采购单类型",
    "关联包裹号",
)

DATE_SHORTCUTS: Final[Tuple[str, ...]] = (
    "今天",
    "昨天",
    "近7天",
    "近30天",
    "近90天",
)

CUSTOM_DATE_INPUT_NAMES: Final[Tuple[str, ...]] = (
    "开始日期",
    "结束日期",
)

CUSTOM_TIME_INPUT_NAMES: Final[Tuple[str, ...]] = (
    "开始时间",
    "结束时间",
)

IMPORT_EXPORT_BUTTON_TEXT: Final[str] = "导入/导出"

EXPORT_MENU_ITEMS: Final[Tuple[str, ...]] = (
    "导入采购单",
    "导出选中",
    "导出全部搜索结果",
    "导出记录",
)

EXPORT_FIELD_GROUPS: Final[Tuple[str, ...]] = (
    "采购单信息",
    "商品信息",
    "关联运单信息",
)

EXPORT_FIELD_GROUPS_FULL_SELECT_TEXT: Final[str] = "全选"

PROGRESS_DIALOG_TITLE: Final[str] = "正在导出"

PROGRESS_TEXT_VARIANTS: Final[Tuple[str, ...]] = (
    "正在导出包裹",
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
)

EXPORT_RECORD_ROW_READY_TEXTS: Final[Tuple[str, ...]] = (
    "导出成功",
    "可下载",
    "下载",
)

EXPORT_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "导出",
    "确定导出",
)

CANCEL_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "取消",
)

CLOSE_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "关闭",
    "我知道了",
)

EXPORT_RECORD_POLL_INTERVAL_S: Final[int] = 5
EXPORT_RECORD_POLL_TIMEOUT_S: Final[int] = 300

POPUP_CLOSE_SELECTORS: Final[Tuple[str, ...]] = (
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

DATA_TYPE_DIR: Final[str] = "purchase"


@dataclass(frozen=True)
class PurchaseSelectors:
    base_url: str = BASE_URL
    purchase_path: str = PURCHASE_GOODS_PATH
    export_record_path: str = PURCHASE_EXPORT_RECORD_PATH
    status_tabs: Tuple[str, ...] = STATUS_TABS
    filter_field_names: Tuple[str, ...] = FILTER_FIELD_NAMES
    date_shortcuts: Tuple[str, ...] = DATE_SHORTCUTS
    custom_date_input_names: Tuple[str, ...] = CUSTOM_DATE_INPUT_NAMES
    custom_time_input_names: Tuple[str, ...] = CUSTOM_TIME_INPUT_NAMES
    import_export_button_text: str = IMPORT_EXPORT_BUTTON_TEXT
    export_menu_items: Tuple[str, ...] = EXPORT_MENU_ITEMS
    export_field_groups: Tuple[str, ...] = EXPORT_FIELD_GROUPS
    export_field_groups_full_select_text: str = EXPORT_FIELD_GROUPS_FULL_SELECT_TEXT
    progress_dialog_title: str = PROGRESS_DIALOG_TITLE
    progress_text_variants: Tuple[str, ...] = PROGRESS_TEXT_VARIANTS
    export_record_row_ready_texts: Tuple[str, ...] = EXPORT_RECORD_ROW_READY_TEXTS
    export_btn_texts: Tuple[str, ...] = EXPORT_BTN_TEXTS
    cancel_btn_texts: Tuple[str, ...] = CANCEL_BTN_TEXTS
    close_btn_texts: Tuple[str, ...] = CLOSE_BTN_TEXTS
    export_record_poll_interval_s: int = EXPORT_RECORD_POLL_INTERVAL_S
    export_record_poll_timeout_s: int = EXPORT_RECORD_POLL_TIMEOUT_S
    popup_close_buttons: Tuple[str, ...] = POPUP_CLOSE_SELECTORS
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    data_type_dir: str = DATA_TYPE_DIR
