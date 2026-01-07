"""
Miaoshou ERP Orders Performance config (数据域：订单表现)
- 维护“订单表现”页面的深链接与常用选择器
- 本数据域包含两个子类型：
  1) shopee 销售订单信息
  2) tiktok 销售订单信息
- 两者的页面路径仅在 Query 中 platform 不同：
  /stat/profit_statistics/detail?platform=shopee|tiktok

导入阶段零副作用：仅定义常量与数据类。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List

# 站点域
BASE_URL: Final[str] = "https://erp.91miaoshou.com"

# 子类型枚举（保持小写）
ORDER_SUBTYPES: Final[List[str]] = ["shopee", "tiktok"]

# 深链接模板（仅替换 platform）
DEEP_LINK_TEMPLATE: Final[str] = "/stat/profit_statistics/detail?platform={platform}"

# 常见导出/下载/进度相关选择器（与 products/warehouse 体例一致）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
]

# 公告/通知等弹窗关闭（尽量与其他 Miaoshou 配置保持一致，便于统一关闭）
POPUP_CLOSE_SELECTORS: Final[List[str]] = [
    # Ant Design 常见关闭按钮
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-notification .anticon-close",
    ".ant-message-notice-close",
    ".ant-popover .ant-popover-close",
    # Miaoshou 自研 jx-dialog 系列
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    # 文案点击兜底
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(OK)",
    "button:has-text(取消)",
]
CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

PROGRESS_TEXTS: Final[List[str]] = [
    "导出成功，正在下载",
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
    """打包订单表现所需的选择器与常量。

    备注：navigation 组件会根据 ctx.config["orders_subtype"] 选择具体深链接；
    未提供时按顺序尝试 ORDER_SUBTYPES。
    """

    base_url: str = BASE_URL
    # 使用模板 + 子类型列表，便于 navigation 选择
    deep_link_template: str = DEEP_LINK_TEMPLATE
    subtypes: List[str] = tuple(ORDER_SUBTYPES)  # type: ignore[assignment]

    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    popup_close_buttons: List[str] = tuple(POPUP_CLOSE_SELECTORS)  # type: ignore[assignment]
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: List[str] = tuple(PROGRESS_TEXTS)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR

