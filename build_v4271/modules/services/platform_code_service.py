#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Platform code canonicalization service.

- Maps various aliases (including Chinese names) to canonical platform_code
  e.g., '虾皮', 'Shopee', 'shopee' -> 'shopee'
- Enforces lowercase snake-case codes
- Provides validation and simple registry helpers

This module has no side effects at import time.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

# Canonical codes we recognize
CANONICAL_PLATFORM_CODES = {
    "shopee",
    "miaoshou",
    "tiktok",
    "amazon",
}

# Alias map (case-insensitive); keep keys lowercased for matching
_ALIAS_TO_CODE: Dict[str, str] = {
    # Shopee
    "shopee": "shopee",
    "虾皮": "shopee",
    "shopee巴西": "shopee",
    "shopee brasil": "shopee",
    "shopee br": "shopee",
    # Miaoshou ERP / 妙手
    "miaoshou": "miaoshou",
    "妙手": "miaoshou",
    # TikTok Shop
    "tiktok": "tiktok",
    "tiktok shop": "tiktok",
    "tiktok_2店": "tiktok",  # 添加tiktok_2店别名
    "抖音": "tiktok",
    # Amazon
    "amazon": "amazon",
    "亚马逊": "amazon",
}


def canonicalize_platform(name: str) -> Optional[str]:
    """Return canonical platform_code for an input name/alias.

    Args:
        name: Free-form name or alias (Chinese/English)
    Returns:
        canonical code (e.g., 'shopee'), or None if unknown.
    """
    if not name:
        return None
    key = str(name).strip().lower()
    return _ALIAS_TO_CODE.get(key)


def is_supported(code: str) -> bool:
    """Check if a canonical platform code is recognized."""
    if not code:
        return False
    return code.strip().lower() in CANONICAL_PLATFORM_CODES


def register_alias(alias: str, code: str) -> None:
    """Register a runtime alias -> code mapping (in-memory).

    Useful for hotfixing new aliases without redeploy. Not persisted.
    """
    if not alias or not code:
        return
    alias_key = alias.strip().lower()
    code_key = code.strip().lower()
    if code_key in CANONICAL_PLATFORM_CODES:
        _ALIAS_TO_CODE[alias_key] = code_key


def bulk_canonicalize(names: Iterable[str]) -> Dict[str, Optional[str]]:
    """Canonicalize an iterable of names to codes, returned as a dict."""
    return {name: canonicalize_platform(name) for name in names}

