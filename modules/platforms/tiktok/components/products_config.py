from __future__ import annotations

"""TikTok 商品表现（Products）组件配置

遵循新架构“深链接集中维护”规范：
- 仅在本文件维护深链接路径（不含域名）与页面关键选择器；业务层禁止硬编码 URL
- 页面语言可能变化，选择器提供中英双语兜底
- 模块导入零副作用
"""
from dataclasses import dataclass
from typing import Final, List
from enum import Enum


class TargetPage(Enum):
    """导航目标页面枚举"""
    PRODUCTS_PERFORMANCE = "products_performance"
    TRAFFIC_OVERVIEW = "traffic_overview"


# 注意：登录入口为 seller.tiktokglobalshop.com；
# 深链接域名为 seller.tiktokshopglobalselling.com
BASE_URL: Final[str] = "https://seller.tiktokshopglobalselling.com"

# 目标页面（商品表现）深链接路径（仅路径部分）
PRODUCTS_PERFORMANCE_PATH: Final[str] = "/compass/product-analysis"

# 导出与下载按钮（按优先级）
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"导出数据\")",
    "button:has-text(\"导出\")",
    "text=导出数据",
    "text=导出",
    "button:has-text(\"Export\")",
    "button:has-text(\"Export Data\")",
    "[data-testid*='export']",
]

DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    "button:has-text(\"下载\")",
    "a:has-text(\"下载\")",
    "button:has-text(\"Download\")",
    "[data-testid*='download']",
    "button:has-text(\"确认\")",
    "button:has-text(\"确定\")",
]

# 页面就绪探针（点击导出前确认页面稳定）
DATA_READY_PROBES: Final[List[str]] = [
    "[data-testid*='product']",
    "table",
    "[role='grid']",
]

# 统一导出子目录名（与 Shopee 对齐）
DATA_TYPE_DIR: Final[str] = "products"


@dataclass(frozen=True)
class ProductsSelectors:
    """打包的选择器与常量（便于一次性传入组件）。"""

    base_url: str = BASE_URL
    performance_path: str = PRODUCTS_PERFORMANCE_PATH
    export_buttons: List[str] = tuple(EXPORT_BUTTON_SELECTORS)  # type: ignore[assignment]
    download_buttons: List[str] = tuple(DOWNLOAD_BUTTON_SELECTORS)  # type: ignore[assignment]
    data_ready_probes: List[str] = tuple(DATA_READY_PROBES)  # type: ignore[assignment]
    data_type_dir: str = DATA_TYPE_DIR
