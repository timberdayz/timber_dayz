from __future__ import annotations

"""TikTok 订单数据（Orders）组件配置

- 深链接路径与关键选择器集中维护；禁止业务层硬编码 URL
- 仅定义常量与数据类；导入零副作用
- 路径为占位默认值，录制完成后根据真实入口更新
"""
from dataclasses import dataclass
from typing import Final, List

# 统一深链接域名（登录域是 seller.tiktokglobalshop.com）
BASE_URL: Final[str] = "https://seller.tiktokshopglobalselling.com"

# 订单中心页面（仅路径部分；待录制确认后更新更精确路径）
ORDERS_PATH: Final[str] = "/order/list"

# 页面就绪探针（最低可用集，后续按录制完善）
DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='order']",
    "table",
    "[role='grid']",
]

# 导出/下载按钮候选（按优先级）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"导出\")",
    "button:has-text(\"Export\")",
    "[data-testid*='export']",
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"下载\")",
    "a:has-text(\"下载\")",
    "button:has-text(\"Download\")",
    "[data-testid*='download']",
]

# 统一导出子目录名（与 Shopee 对齐）
DATA_TYPE_DIR: Final[str] = "orders"


@dataclass(frozen=True)
class OrdersSelectors:
    """订单数据页面的路径与选择器打包"""

    base_url: str = BASE_URL
    orders_path: str = ORDERS_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR

