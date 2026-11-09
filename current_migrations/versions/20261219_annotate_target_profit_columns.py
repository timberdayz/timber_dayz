"""给两列「目标利润」补上明确的语义注释（**保留两列，不合并**）。

背景
----
``a_class.target_breakdown``（以及它的父表 ``a_class.sales_targets``）上有两列
名字极其接近的「目标利润」：

    target_profit_amount         目标毛利
    target_profit_basis_amount   目标结算利润基数

业务含义**不同**，不能合并成一列：

* ``target_profit_amount``（目标毛利）
  管理员直接配置的目标毛利，**不扣**其他经营成本、**不扣**提成前人力成本。
  它是「业务上想要赚多少毛利」的目标值，只作参考展示。

* ``target_profit_basis_amount``（目标结算利润基数）
  与实际结算口径**对齐**的目标值，绩效「利润维度」就是拿它跟实际利润基数
  ``finance.shop_profit_basis.profit_basis_amount`` 比达成率
  （见 ``backend/domains/business/routers/performance_management.py``）。
  它由「店铺目标工作台」录入公司级目标后，按店铺比例与时间权重拆到各店
  （``backend/services/shop_target_workbench_service.py``）。

两列的差额来源是成本与人力：毛利目标没有扣成本，结算利润基数目标扣了。
如果谁把它们当成同一列，绩效得分会直接算错。

处理方式
--------
只加 ``COMMENT ON COLUMN``，**不改列、不合列、不动数据** ——
合并需要一次数据迁移，而且会丢掉「毛利目标」这个业务概念。

ORM 侧同步改了 ``modules/core/db/schema_parts/business.py`` 里的注释，
两边描述一致。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261219_annotate_target_profit_columns"
down_revision = "current_schema_20261218_cleanup_chinese_constraint_names"
branch_labels = None
depends_on = None


#: 目标毛利 —— 管理员直接配置，未扣成本
TARGET_PROFIT_AMOUNT_COMMENT = (
    "目标毛利(CNY)：管理员直接配置的目标毛利，不扣其他经营成本、不扣提成前人力成本；"
    "只作业务参考，不参与绩效利润维度计算"
)

#: 目标结算利润基数 —— 与结算口径对齐，绩效利润维度用它算达成率
TARGET_PROFIT_BASIS_AMOUNT_COMMENT = (
    "目标结算利润基数(CNY)：与结算口径对齐的目标值（已扣其他经营成本与提成前人力成本），"
    "绩效利润维度用它与实际利润基数 finance.shop_profit_basis.profit_basis_amount "
    "对比算达成率；由店铺目标工作台按公司目标按店铺比例与时间权重拆分而来"
)

#: 实际毛利 —— 达成值口径
ACHIEVED_PROFIT_AMOUNT_COMMENT = (
    "实际毛利(CNY)：达成值口径的实际毛利，由系统按当期数据回算"
)

#: 需要补注释的表
TABLES = ("a_class.target_breakdown", "a_class.sales_targets")

#: 列 → 注释
COLUMN_COMMENTS = {
    "target_profit_amount": TARGET_PROFIT_AMOUNT_COMMENT,
    "target_profit_basis_amount": TARGET_PROFIT_BASIS_AMOUNT_COMMENT,
    "achieved_profit_amount": ACHIEVED_PROFIT_AMOUNT_COMMENT,
}


def _table_exists(table: str) -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text("SELECT to_regclass(:name)"),
            {"name": table},
        )
        .scalar_one_or_none()
    )
    return row is not None


def _column_exists(table: str, column: str) -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = :schema
                   AND table_name = :table
                   AND column_name = :column
                """
            ),
            {
                "schema": table.split(".", 1)[0],
                "table": table.split(".", 1)[1],
                "column": column,
            },
        )
        .fetchone()
    )
    return row is not None


def _apply_comments() -> None:
    for table in TABLES:
        if not _table_exists(table):
            print(f"[WARN] 表不存在，跳过注释：{table}")
            continue
        schema, name = table.split(".", 1)
        for column, comment in COLUMN_COMMENTS.items():
            if not _column_exists(table, column):
                continue
            # schema 与表名要**分开**加引号：写成 "a_class.target_breakdown"
            # 会被 PostgreSQL 当成「一个带点的标识符」，直接报「表不存在」。
            op.execute(
                f'COMMENT ON COLUMN "{schema}"."{name}"."{column}" IS {_literal(comment)}'
            )


def _literal(value: str) -> str:
    """把注释拼成 SQL 字符串字面量（单引号转义）。"""
    return "'" + str(value).replace("'", "''") + "'"


def upgrade() -> None:
    _apply_comments()


def downgrade() -> None:
    """回滚：清空这三列的注释（回到「没有说明」的状态）。"""
    for table in TABLES:
        if not _table_exists(table):
            continue
        schema, name = table.split(".", 1)
        for column in COLUMN_COMMENTS:
            if not _column_exists(table, column):
                continue
            op.execute(
                f'COMMENT ON COLUMN "{schema}"."{name}"."{column}" IS NULL'
            )
