"""给员工提成加「计算审计」两列，让「没提成」不再是无声的。

背景
----
``c_class.employee_commissions`` 只有金额、比例和时间三个业务字段。
以前一个员工如果**没配提成比例**，计算链路会直接 ``continue`` 跳过他
⇒ 根本不产生这一行 ⇒ 工资单提成恒 0，而界面上看不出任何异常。

本迁移加两列（与 ``c_class.employee_performance`` 同一套模式）：

- ``calculation_status``
  - ``calculated``  正常算出来了
  - ``no_ratio``    没配任何提成比例（金额 0，但**有记录**）
  - ``blocked``     被业务规则挡住（如受控月未确认口径）
- ``calculation_details``（JSON）
  记录比例来源、比例值、用了哪些店铺 —— 让「这个人的提成到底怎么来的」可审计。

兼容性
------
新增列**都有默认值**，既有行不受影响；``calculation_details`` 可空。

顺带修一处「注释与实现矛盾」
--------------------------
``c_class.performance_scores`` 的四个得分列注释写死了百分比
（30%/25%/25%/20%），而实际默认权重是 **40/40/0/20**，而且权重是**可配置的**
（``a_class.performance_config``）⇒ 看注释的人会以为配置没生效。
这里把注释改成「权重由绩效配置决定」，不再写死数字。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261109_add_commission_calculation_audit"
down_revision = "current_schema_20261108_align_labor_cost_allocation_version"
branch_labels = None
depends_on = None


TABLE = "employee_commissions"
SCHEMA = "c_class"


def _columns(connection, table_name: str, schema_name: str) -> set[str]:
    return set(
        connection.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema_name AND table_name = :table_name"
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        .scalars()
        .all()
    )


def upgrade() -> None:
    connection = op.get_bind()
    existing = _columns(connection, TABLE, SCHEMA)
    if "calculation_status" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "calculation_status",
                sa.String(length=32),
                nullable=False,
                server_default="calculated",
            ),
            schema=SCHEMA,
        )
    if "calculation_details" not in existing:
        op.add_column(
            TABLE,
            sa.Column("calculation_details", sa.JSON(), nullable=True),
            schema=SCHEMA,
        )
    _fix_performance_score_comments(connection)


def _fix_performance_score_comments(connection) -> None:
    """把「写死百分比」的得分列注释改成「权重由绩效配置决定」。"""
    comments = (
        ("sales_score", "销售额得分（权重由绩效配置决定）"),
        ("profit_score", "毛利得分（权重由绩效配置决定）"),
        ("key_product_score", "重点产品得分（该维度尚未启用，恒为0）"),
        ("operation_score", "运营得分（权重由绩效配置决定）"),
    )
    existing = _columns(connection, "performance_scores", SCHEMA)
    for column, comment in comments:
        if column not in existing:
            continue
        connection.execute(
            sa.text(
                "COMMENT ON COLUMN c_class.performance_scores.{column} IS :comment".format(
                    column=column
                )
            ),
            {"comment": comment},
        )


def downgrade() -> None:
    connection = op.get_bind()
    existing = _columns(connection, TABLE, SCHEMA)
    for column in ("calculation_details", "calculation_status"):
        if column in existing:
            op.drop_column(TABLE, column, schema=SCHEMA)
