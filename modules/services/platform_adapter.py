from __future__ import annotations

"""Platform adapter service registry.

Apps should depend only on services/core. This module provides a factory
that returns the proper platform adapter given a platform id.

Import side-effects are minimal and localized.
"""
from typing import Dict, Type

from modules.platforms.adapter_base import PlatformAdapter
from modules.components.base import ExecutionContext

# Lazy imports inside factory to minimize import-time cost and avoid side effects.

_REGISTRY: Dict[str, str] = {
    "shopee": "modules.platforms.shopee.adapter.ShopeeAdapter",
    "miaoshou": "modules.platforms.miaoshou.adapter.MiaoshouAdapter",
    "tiktok": "modules.platforms.tiktok.adapter.TiktokAdapter",
    "amazon": "modules.platforms.amazon.adapter.AmazonAdapter",
}


def _import_string(path: str):
    module_path, _, class_name = path.rpartition(".")
    mod = __import__(module_path, fromlist=[class_name])
    return getattr(mod, class_name)


def get_adapter(platform: str, ctx: ExecutionContext) -> PlatformAdapter:
    """Return a platform adapter instance for the given platform id.

    Args:
        platform: platform id like 'shopee', 'miaoshou', 'tiktok'
        ctx: execution context
    """
    key = (platform or "").lower()
    if key not in _REGISTRY:
        raise ValueError(f"Unsupported platform: {platform}")
    cls = _import_string(_REGISTRY[key])
    return cls(ctx)  # type: ignore[return-value]

