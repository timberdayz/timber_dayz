"""SSOT 收敛（第三阶段）：利润基数快照「一月一店一行」。

背景
----
``finance.shop_profit_basis`` 的唯一键原来是
``(period_month, platform_code, shop_id, basis_version)`` ——
也就是说**同一家店、同一个月，口径一变就会多出一行**。

口径从 ``A_PRE_COMMISSION_LABOR_V2`` 收敛到 ``SETTLEMENT_BASIS_V1`` 之后，
本地库立刻出现了同一个事实的两份快照：

    shopee | 1308200830 | A_PRE_COMMISSION_LABOR_V2 | 7739.52
    shopee | 1308200830 | SETTLEMENT_BASIS_V1        | 6454.60

读的时候只能靠「挑一条」来糊弄 —— 这正是 SSOT 要消灭的情况：
同一份事实存两份，取决于读代码时先写了哪句。

处理方式
--------
* 一个「月份 + 店铺」只保留**一条**快照；
  ``basis_version`` 变成这条快照的**属性**（重算时更新），
  不再用来区分行。
* 保留哪一条：优先当前口径；没有当前口径就保留已锁定的那条（已锁定的不能悄悄删）；
  都没有就保留最近更新的那条。
* **要删的行如果是已锁定状态，直接中止迁移** ——
  已锁定的快照被月结引用过，删掉等于偷偷改已结账的钱，必须人工退回再重算。

安全性
------
fail-closed：遇到已锁定的重复行就抛错，不擅自决定留哪条。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261216_unify_profit_basis_snapshot_rows"
down_revision = "current_schema_20261215_migrate_sales_targets_a"
branch_labels = None
depends_on = None


CURRENT_BASIS_VERSION = "SETTLEMENT_BASIS_V1"
TABLE = "finance.shop_profit_basis"
CONSTRAINT = "uq_shop_profit_basis"


def _bind():
    return op.get_bind()


def _scalar(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar_one()


def _duplicate_groups() -> list[tuple[str, str, str]]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT period_month, platform_code, shop_id
                  FROM finance.shop_profit_basis
                 GROUP BY period_month, platform_code, shop_id
                HAVING COUNT(*) > 1
                 ORDER BY period_month, platform_code, shop_id
                """
            )
        )
        .fetchall()
    )
    return [(row[0], row[1], row[2]) for row in rows]


def _rows_of(period_month: str, platform_code: str, shop_id: str) -> list[dict]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT id, basis_version, is_locked, updated_at
                  FROM finance.shop_profit_basis
                 WHERE period_month = :period_month
                   AND platform_code = :platform_code
                   AND shop_id = :shop_id
                 ORDER BY updated_at DESC, id DESC
                """
            ),
            {
                "period_month": period_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
            },
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _pick_keeper(rows: list[dict]) -> dict:
    for row in rows:
        if str(row.get("basis_version") or "") == CURRENT_BASIS_VERSION:
            return row
    for row in rows:
        if bool(row.get("is_locked")):
            return row
    return rows[0]


def upgrade() -> None:
    for period_month, platform_code, shop_id in _duplicate_groups():
        rows = _rows_of(period_month, platform_code, shop_id)
        if len(rows) <= 1:
            continue
        keeper = _pick_keeper(rows)
        for row in rows:
            if row["id"] == keeper["id"]:
                continue
            if bool(row.get("is_locked")):
                raise RuntimeError(
                    "finance.shop_profit_basis 存在已锁定的重复快照 "
                    f"({period_month}, {platform_code}, {shop_id}, id={row['id']}); "
                    "请先退回月结再重跑迁移。"
                )
            op.get_bind().execute(
                sa.text("DELETE FROM finance.shop_profit_basis WHERE id = :id"),
                {"id": row["id"]},
            )

    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} "
        "UNIQUE (period_month, platform_code, shop_id)"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} "
        "UNIQUE (period_month, platform_code, shop_id, basis_version)"
    )
