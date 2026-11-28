"""费用占位行清理迁移的契约守护。

背景见迁移文件 docstring：2026-06-09 的一次批量操作预建了全年空费用行，
它们不是业务事实，导致已停用店铺在 11 月仍出现在费用管理页。

本守护把「只清纯占位行、只清 2026-06 及以后、可逆、迁移链单头」钉在 CI 里。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = "current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_migration_targets_only_placeholder_rows():
    source = _read(MIGRATION)
    for column in (
        "rent_amount",
        "marketing_amount",
        "utility_amount",
        "ai_token_amount",
        "other_amount",
    ):
        assert (
            f"COALESCE({column}, 0) = 0" in source
        ), f"占位行判定必须要求 {column} 为 0，否则会误删真实费用行"
    assert "COALESCE(total_amount, 0) = COALESCE(labor_amount, 0)" in source
    assert "COALESCE(remark, '') = ''" in source
    assert "attachments" in source
    assert "deleted_at IS NULL" in source


def test_migration_scope_starts_at_2026_06():
    source = _read(MIGRATION)
    assert 'CLEANUP_START = "2026-06"' in source
    assert 'CLEANUP_END = "2026-12"' in source
    assert "BETWEEN" in source


def test_migration_is_reversible_and_marked():
    source = _read(MIGRATION)
    assert "def downgrade()" in source
    assert "BATCH_MARK" in source
    assert "deleted_at = NULL" in source
    assert (
        "deleted_at IS NOT NULL" in source
    ), "downgrade 必须限定 deleted_at IS NOT NULL，否则会误清存活行的 remark"


NEW_REVISION = "current_schema_20261246_cleanup_expense_placeholder_rows"


def _scan_revision_chain() -> dict:
    chain = {}
    for path in (ROOT / "current_migrations/versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision = "([^"]+)"', text, re.M)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M)
        if rev:
            chain[rev.group(1)] = down.group(1) if down else None
    return chain


def test_migration_chain_has_no_fork_and_single_head():
    """有效链无分叉且唯一 head。

    「真双头」= 同一个父被两个迁移同时认领（分叉）。
    字符串断言抓不到它，必须真扫 revision/down_revision。

    本迁移的 down_revision 指向 current_schema_20261244_...（链上已存在），因此本分支
    自身自洽单头。main 上若另有在途迁移也认领 20261244，就会分叉 —— 本用例会红。
    """
    chain = _scan_revision_chain()

    assert NEW_REVISION in chain, "本迁移必须出现在 revision 链里"
    parent = chain[NEW_REVISION]
    assert parent, "本迁移必须有 down_revision"
    assert parent in chain, (
        f"down_revision 指向链上不存在的迁移: {parent} —— "
        "本迁移必须接在已落地的迁移之后"
    )

    parents = [down for down in chain.values() if down]
    forked = sorted({p for p in parents if parents.count(p) > 1})
    assert not forked, (
        f"revision 链分叉（多个迁移共用同一父 {forked}）—— "
        "alembic upgrade head 会失败；合并时需让其中一条改接在另一条之后"
    )

    heads = set(chain) - set(parents)
    assert len(heads) == 1, (
        f"有效链 head 不唯一: {sorted(heads)} —— "
        "本迁移必须接在当前 head 之后"
    )


def test_migration_declares_expected_revision_ids():
    source = _read(MIGRATION)
    assert (
        'revision = "current_schema_20261246_cleanup_expense_placeholder_rows"'
        in source
    )
    assert (
        'down_revision = "current_schema_20261244_drop_employee_shop_assignment_role"'
        in source
    )
