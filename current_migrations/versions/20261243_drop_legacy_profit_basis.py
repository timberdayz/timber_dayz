"""删除 legacy 口径的利润基数行（提成与绩效工资口径归一）。

背景
----
2026-11-21 业务确认「提成 = 可分配利润 × 归属提成比（零系数）」、
「绩效工资 = 绩效包 × 纯个人分数档位系数」，并授权**历史数据可删除或重算**
（本批最终选择**删除 legacy 行并接受历史空白**，见
``docs/superpowers/plans/2026-11-21-commission-and-performance-caliber-unification.md``）。

``finance.shop_profit_basis`` 里 2026-03 ~ 2026-09 共 58 行是旧口径版本：

* ``A_ONLY_V1``（仅 A 类成本口径，2026-03 ~ 2026-08）
* ``A_PRE_COMMISSION_LABOR_V2``（扣提成前人力成本口径，2026-09）

现行代码读它们时会被 :meth:`LaborCostPolicyService.is_legacy_basis_version`
跳过 ⇒ **这些月份今天算不出提成**，历史工资单也无法用今天的代码复现。
口径归一后它们不再有任何读者 ⇒ 删除。

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

⚠️ 删除后那些月份会变成**空白**，这是刻意的
--------------------------------------------
历史月份缺「人力成本分摊」数据（``finance.employee_labor_cost_allocations``
只有 2026-07 与 2026-10 有数据）⇒ 现行口径算不出那些月的利润基数，
重算这条路**实测不可行**。

取舍理由：**口径统一优先于历史可比** ——
留着两套口径的数字并存，看板上同一个月的数字会有两种解释，比空白更难解释。

连带的**已知后果**：2026-07 有旧口径利润基数，也有当前口径的人力成本分摊；
删掉利润基数后该月看板会整体留白（``data_status = no_profit_basis``），
工资单里的旧提成金额保留不动（历史事实不被改写）。
若日后补齐了这些月份的人力成本分摊，可用
``scripts/recalibrate_commission_history.py`` 回填。
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
    """删除 legacy 口径的利润基数行。

    ⚠️ 业务决策（2026-11-21，Walter）：**接受历史空白**。
    历史月份（2026-03 ~ 2026-09）缺「人力成本分摊」数据 ⇒ 现行口径算不出利润基数
    ⇒ 删掉 legacy 行后那些月份在看板与工资单上会变成空白。

    这是**刻意**的取舍：口径统一优先于历史可比 ——
    留着两套口径的数字并存，看板上同一个月的数字会有两种解释，比空白更难解释。
    """
    if not _has_table(FINANCE_SCHEMA, BASIS_TABLE):
        return
    bind = op.get_bind()
    versions = ", ".join(f"'{v}'" for v in LEGACY_BASIS_VERSIONS)

    # 先数一遍：生产核验要能对上「删了多少行、哪几个月」。
    rows = bind.execute(
        sa.text(
            f"SELECT period_month, basis_version, count(*) "
            f"FROM {FINANCE_SCHEMA}.{BASIS_TABLE} "
            f"WHERE basis_version IN ({versions}) "
            f"GROUP BY period_month, basis_version "
            f"ORDER BY period_month"
        )
    ).fetchall()
    for row in rows:
        print(f"[20261243] 删除 legacy 利润基数：{row[0]} {row[1]} x{row[2]}")
    total = sum(int(row[2]) for row in rows)
    print(f"[20261243] 共删除 {total} 行 legacy 口径利润基数")

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
