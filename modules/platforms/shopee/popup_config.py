"""
Shopee popup configuration.

The cross-platform safe-notice contract is defined here even before
Shopee-specific evidence-backed selectors are added.
"""

from typing import Any, Dict, List


def get_close_selectors() -> List[str]:
    return []


def get_overlay_selectors() -> List[str]:
    return []


def get_poll_strategy() -> Dict[str, Any]:
    return {}


def get_safe_notice_close_selectors() -> List[str]:
    return []


def get_safe_notice_overlay_selectors() -> List[str]:
    return []


def get_safe_notice_exclusion_selectors() -> List[str]:
    return []
