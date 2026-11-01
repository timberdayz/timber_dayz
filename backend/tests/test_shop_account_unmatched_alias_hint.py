from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_unmatched_alias_item_exposes_claim_hint():
    """未匹配别名项必须给出认领提示。

    业务决定：TK新加坡3C店 暂不认领，必须说清「现有 TikTok 店已被其它标签 1:1 占满，
    需新建店账号才能认领」—— 否则运营看到 unknown 不知道下一步该做什么。
    """
    from backend.schemas.account import UnmatchedShopAliasItem

    assert "claim_hint" in UnmatchedShopAliasItem.model_fields, "未匹配别名项缺少 claim_hint"


def test_account_management_shows_unmatched_alias_row_count():
    """前端必须展示未匹配别名的出现次数 row_count。

    注：``order_count`` 已经在展示了，缺的是 ``row_count``（数据行数）。
    """
    vue = REPO_ROOT / "frontend" / "src" / "domains" / "platform" / "views" / "AccountManagement.vue"
    text = vue.read_text(encoding="utf-8")
    assert "row_count" in text, "前端未展示未匹配别名的 row_count"
