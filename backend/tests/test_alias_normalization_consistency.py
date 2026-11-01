from __future__ import annotations

import re
from pathlib import Path

from backend.utils.text_normalization import normalize_alias_key

REPO_ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("TK-新加坡-1店", "新加坡1店"),
    ("TK新加坡1店", "新加坡1店"),
    ("Malaysia(Flora Mall)", "malaysiafloramall"),
    ("Shopee3C店", "3c店"),
    ("3C店", "3c店"),
    # 注意：分隔符集是 [\s_()/-]，**不含点号** —— 与 spec §2.4 的 SQL 口径
    # `[[:space:]_()/-]+` 保持一致。xhkj1.my 的规范化值就是 xhkj1.my。
    ("xhkj1.my", "xhkj1.my"),
]


def test_normalize_alias_key_matches_sql_semantics():
    """Python 侧规范化必须与 SQL 侧（剥前缀 + 删分隔符）完全一致。"""
    for raw, expected in CASES:
        assert normalize_alias_key(raw) == expected, f"{raw!r} -> {normalize_alias_key(raw)!r} != {expected!r}"


def test_normalize_alias_key_is_idempotent():
    """规范化必须幂等：normalize(normalize(x)) == normalize(x)。"""
    for raw, _ in CASES:
        once = normalize_alias_key(raw)
        assert normalize_alias_key(once) == once


def test_sql_assets_use_stored_alias_normalized():
    """直接引用别名表的 SQL 必须用存储的 alias_normalized。

    注：``analytics_atomic.sql`` 与 ``orders_monthly_atomic_mv.sql`` 走的是候选视图
    ``semantic.shop_identity_resolution_candidates``，不直接 JOIN 别名表，
    所以对这两个文件断言的是「引用了候选视图」。
    """
    for rel in (
        "sql/semantic/shop_identity_resolution_candidates.sql",
        "sql/semantic/orders_atomic.sql",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "saa.alias_normalized" in text, f"{rel} 未使用存储的 alias_normalized"

    for rel in (
        "sql/semantic/analytics_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "shop_identity_resolution_candidates" in text, f"{rel} 未引用候选视图"
