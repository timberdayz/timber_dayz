"""
Shopee 平台弹窗配置 - 仅使用 Python 模块，不再读取 popup_config.yaml。

由 UniversalPopupHandler 通过本模块获取平台特定关闭/遮罩选择器。
"""

from typing import List, Dict, Any


def get_close_selectors() -> List[str]:
    """平台特定关闭按钮选择器（插入到通用选择器前，优先匹配）。"""
    return []


def get_overlay_selectors() -> List[str]:
    """平台特定遮罩层选择器。"""
    return []


def get_poll_strategy() -> Dict[str, Any]:
    """轮询策略覆盖（可选）。"""
    return {}
