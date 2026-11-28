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


def test_migration_revision_chain_is_single_head():
    """真扫全仓 revision/down_revision 判单头。

    字符串断言抓不到「双头」：若有人在途迁移与本迁移同父，合回 main 后就会出现两个
    head，``alembic upgrade head`` 直接失败。
    """
    versions_dir = ROOT / "current_migrations/versions"
    revisions = set()
    down_revisions = set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision = "([^"]+)"', text, re.M)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            down_revisions.add(down.group(1))

    heads = revisions - down_revisions
    assert len(heads) <= 1, (
        f"迁移链出现多个 head: {sorted(heads)} —— "
        "本迁移的 down_revision 必须接在当前 head 之后"
    )


def test_migration_declares_expected_revision_ids():
    source = _read(MIGRATION)
    assert (
        'revision = "current_schema_20261246_cleanup_expense_placeholder_rows"'
        in source
    )
    assert "down_revision = " in source
