"""SSOT 收敛（第二阶段）：为员工绩效补上「统一结算系数」列。

背景
----
本轮把「绩效工资」和「提成」两个口子上的系数统一成同一个口径：

    结算系数 = min(排名系数, 分数系数)

排名系数来自店铺绩效排名档位（TOP20%/50%/80% → 1.2/1.0/0.9/0.8），
分数系数来自个人绩效分数档位（≥90/80/70/60 → 1.2/1.0/0.9/0.8，其余 0.5）。

统一之后，这个系数必须**能被工资单读到**，否则绩效工资会退回到
「分数 ÷ 100」的旧算法，和页面上显示的系数对不上。

改造前 ``c_class.employee_performance`` 只有 ``performance_score``，
``PayrollGenerationService._normalize_performance_coefficient`` 拿不到系数时
会退化成 ``score / 100``；改造后必须有一列专门存结算系数。

安全性
------
- 新列可空，不改写任何历史行；历史行的 ``performance_coefficient`` 保持 NULL，
  由结算流程在重算时回填，保证历史快照可追溯。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261213_employee_performance_coefficient"
down_revision = "current_schema_20261212_cleanup_shadow_tables_and_legacy_columns"
branch_labels = None
depends_on = None


TABLE = "c_class.employee_performance"
COLUMN = "performance_coefficient"


def _column_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("employee_performance", schema="c_class"):
        return False
    return any(
        col["name"] == COLUMN
        for col in inspector.get_columns("employee_performance", schema="c_class")
    )


def upgrade() -> None:
    if _column_exists():
        return
    op.execute(
        "ALTER TABLE c_class.employee_performance "
        "ADD COLUMN IF NOT EXISTS performance_coefficient double precision"
    )


def downgrade() -> None:
    if not _column_exists():
        return
    op.execute(
        "ALTER TABLE c_class.employee_performance "
        "DROP COLUMN IF EXISTS performance_coefficient"
    )
