"""删除 legacy 口径的利润基数行（提成与绩效工资口径归一）。

背景
----
2026-11-21 业务确认「提成 = 可分配利润 × 归属提成比（零系数）」、
「绩效工资 = 绩效包 × 纯个人分数档位系数」，并授权**历史数据可删除或重算**
（本批选择**重算**，见 ``docs/superpowers/plans/2026-11-21-commission-and-performance-caliber-unification.md``）。

``finance.shop_profit_basis`` 里 2026-03 ~ 2026-09 共 58 行是旧口径版本：

* ``A_ONLY_V1``（仅 A 类成本口径，2026-03 ~ 2026-08）
* ``A_PRE_COMMISSION_LABOR_V2``（扣提成前人力成本口径，2026-09）

现行代码读它们时会被 :meth:`LaborCostPolicyService.is_legacy_a_only_basis_version`
跳过 ⇒ **这些月份今天算不出提成**，历史工资单也无法用今天的代码复现。
口径归一后它们不再有任何读者 ⇒ 删除，由重算脚本按现行口径重新生成。

本迁移做一件事
--------------
删掉 ``finance.shop_profit_basis`` 里 ``basis_version`` 属于
``A_ONLY_V1`` / ``A_PRE_COMMISSION_LABOR_V2`` 的行。

⚠️ 不可逆
--------
被删的行**无法**通过 downgrade 找回：downgrade 只保证 schema 与迁移链可回滚，
不重建历史快照（重建出来的数字是假的，比留着旧行更糟）。
数据可恢复性由**发版流程自带的迁移前备份**兜底
（``perform_pre_migration_backup``，``pg_restore --list`` 退出码 0 才放行迁移）。

⚠️ 删除后**必须**跑 ``scripts/recalibrate_commission_history.py`` 重算，
否则被删月份在看板与工资单上会变成空白。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261243_drop_legacy_profit_basis"
down_revision = "current_schema_20261242_drop_monthly_profit_snapshots"
branch_labels = None
depends_on = None


FINANCE_SCHEMA = "finance"
BASIS_TABLE = "shop_profit_basis"

#: 被删除的历史口径版本 —— 与
#: ``LaborCostPolicyService.LEGACY_BASIS_VERSIONS`` 一致。
LEGACY_BASIS_VERSIONS = ("A_ONLY_V1", "A_PRE_COMMISSION_LABOR_V2")


def _has_table(schema: str, table: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def upgrade() -> None:
    """删除 legacy 口径的利润基数行。"""
    if not _has_table(FINANCE_SCHEMA, BASIS_TABLE):
        return
    bind = op.get_bind()
    versions = ", ".join(f"'{v}'" for v in LEGACY_BASIS_VERSIONS)
    bind.execute(
        sa.text(
            f"DELETE FROM {FINANCE_SCHEMA}.{BASIS_TABLE} "
            f"WHERE basis_version IN ({versions})"
        )
    )


def downgrade() -> None:
    """不可逆：不恢复被删的历史快照行。

    原因（见文件头）：恢复出来的利润基数是**编造的数字** ——
    legacy 口径的成本构成已无法从当前数据精确重建，
    塞一行假数据进表比留着空白更危险。

    需要恢复历史数据时，从**发版前备份**还原：
    ``pg_restore`` 回灌 ``pre_deploy_*`` 目录里的 dump。
    """
    return None
