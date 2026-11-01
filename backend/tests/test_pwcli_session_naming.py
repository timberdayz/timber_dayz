from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pwcli_account_inventory import slugify, work_tag  # noqa: E402


def test_slugify_keeps_non_ascii_distinct():
    """中文账号名不能塌成同一个 slug。"""
    assert slugify("虾皮巴西（东朗照明主体）") != slugify("验证码测试账号")


def test_slugify_is_stable_for_same_input():
    a = slugify("虾皮巴西（东朗照明主体）")
    b = slugify("虾皮巴西（东朗照明主体）")
    assert a == b


def test_slugify_output_is_filesystem_and_shell_safe():
    out = slugify("Leslieshop:main")
    assert ":" not in out
    assert "/" not in out
    assert " " not in out


def test_work_tag_differs_per_account():
    assert work_tag("shopee", "虾皮巴西（东朗照明主体）") != work_tag("shopee", "验证码测试账号")
    assert work_tag("shopee", "hongxikeji:main") != work_tag("tiktok", "hongxikeji:main")
