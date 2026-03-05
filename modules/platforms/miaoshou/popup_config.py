"""
妙手 ERP 平台弹窗配置 - 仅使用 Python 模块，不再读取 popup_config.yaml。
"""

from typing import List, Dict, Any


def get_close_selectors() -> List[str]:
    """平台特定关闭按钮选择器。"""
    return []


def get_overlay_selectors() -> List[str]:
    """平台特定遮罩层选择器。"""
    return []


def get_poll_strategy() -> Dict[str, Any]:
    """轮询策略覆盖（可选）。"""
    return {}
