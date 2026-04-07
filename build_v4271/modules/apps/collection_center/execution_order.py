"""
采集组件执行顺序配置 - 仅使用 Python 模块，不再读取 YAML。

迁离 execution_order.yaml / default_execution_order.yaml 后，
由本模块统一导出默认与按平台可选的执行顺序。
"""

from typing import Dict, List, Any, Optional

from modules.core.logger import get_logger

logger = get_logger(__name__)


def get_default_execution_order() -> List[Dict[str, Any]]:
    """
    返回默认组件执行顺序（与 executor_v2._get_default_execution_order 一致）。

    Returns:
        执行顺序列表，每项含 component, required, index 等。
    """
    return [
        {"component": "login", "required": True, "index": 0},
        {"component": "shop_switch", "required": False, "index": 1},
        {"component": "navigation", "required": False, "index": 2},
        {"component": "export", "required": True, "index": 3},
    ]


# 平台覆盖：若某平台需要不同顺序，在此注册；否则使用默认顺序。
_PLATFORM_ORDER: Dict[str, List[Dict[str, Any]]] = {}


def get_execution_order(platform: str) -> Optional[List[Dict[str, Any]]]:
    """
    按平台返回执行顺序；无平台配置时返回默认顺序。

    Args:
        platform: 平台代码，如 shopee / tiktok / miaoshou。

    Returns:
        execution_sequence 结构的列表；无定制时返回默认顺序。
    """
    if platform in _PLATFORM_ORDER:
        order = _PLATFORM_ORDER[platform]
        logger.debug(f"Loaded execution order for {platform}: {len(order)} components")
        return order
    default = get_default_execution_order()
    logger.debug(f"Using default execution order for {platform}: {len(default)} components")
    return default
