"""
Miaoshou ERP Products Performance config (数据域：商品表现)
- 提供深链接候选路径与常用按钮选择器
- 体例对齐 *_config.py 规范，导入时零副作用
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List

BASE_URL: Final[str] = "https://erp.91miaoshou.com"

# 深链接候选（按顺序尝试，均失败则回退到侧边栏导航）
# 注：若你确认了更精确路径，请把其放在列表第一位
DEEP_LINK_PATHS: Final[List[str]] = [
    "/warehouse/checklist",
]

# 导出按钮（通用导出组件已支持，无需特别处理）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
]

# 公告/通知等弹窗的关闭按钮
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
# 弹窗关闭轮询策略（ms）
CLOSE_POLL_MAX_ROUNDS: Final[int] = 20  # ~6s
CLOSE_POLL_INTERVAL_MS: Final[int] = 300
# 导出进度提示文案
PROGRESS_TEXTS: Final[List[str]] = [
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "Generating",
    "Processing",
]


@dataclass(frozen=True)
class ProductsSelectors:
    base_url: str = BASE_URL
    deep_link_paths: List[str] = tuple(DEEP_LINK_PATHS)  # type: ignore[assignment]
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    popup_close_buttons: List[str] = tuple(POPUP_CLOSE_SELECTORS)  # type: ignore[assignment]
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: List[str] = tuple(PROGRESS_TEXTS)  # type: ignore[assignment]

