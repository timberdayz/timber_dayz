"""
Miaoshou ERP popup configuration.

This module keeps generic popup cleanup empty and only defines the first
evidence-backed safe notice rules used for post-login / post-navigation
stabilization.
"""

from typing import Any, Dict, List


def get_close_selectors() -> List[str]:
    return []


def get_overlay_selectors() -> List[str]:
    return []


def get_poll_strategy() -> Dict[str, Any]:
    return {"max_rounds": 4, "interval_ms": 250, "watch_ms": 3000}


def get_safe_notice_close_selectors() -> List[str]:
    return [
        ".notice-message-box-dialog .jx-dialog__headerbtn",
        ".notice-message-box-dialog .jx-dialog__close",
        ".notice-message-box-dialog footer .pro-button",
        ".notice-message-box-dialog button[aria-label='关闭此对话框']",
    ]


def get_safe_notice_overlay_selectors() -> List[str]:
    return [
        ".jx-overlay:has(.notice-message-box-dialog)",
        ".notice-message-box-dialog",
    ]


def get_safe_notice_exclusion_selectors() -> List[str]:
    return [
        ".captcha",
        ".aliyun-captcha",
        "[data-nc-idx]",
        "input[autocomplete='one-time-code']",
        "input[name*='otp' i]",
    ]
