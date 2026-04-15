"""Drop legacy Chinese columns from c_class employee metric tables.

Revision ID: 20260415_c_class_employee_metrics_cleanup
Revises: 20260415_c_class_employee_metrics_en
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_c_class_employee_metrics_cleanup"
down_revision = "20260415_c_class_employee_metrics_en"
branch_labels = None
depends_on = None


LEGACY_COLUMNS = {
    "employee_performance": [
        "员工编号",
        "年月",
        "实际销售额",
        "达成率",
        "绩效得分",
        "计算时间",
    ],
    "employee_commissions": [
        "员工编号",
        "年月",
        "销售额",
        "提成金额",
        "提成比例",
        "计算时间",
    ],
}


def _table_exists(connection, schema_name: str, table_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return result.scalar() is not None


def _column_exists(connection, schema_name: str, table_name: str, column_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name, "column_name": column_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    for table_name, columns in LEGACY_COLUMNS.items():
        if not _table_exists(connection, "c_class", table_name):
            continue
        for column_name in columns:
            if _column_exists(connection, "c_class", table_name, column_name):
                op.drop_column(table_name, column_name, schema="c_class")


def downgrade() -> None:
    connection = op.get_bind()

    if _table_exists(connection, "c_class", "employee_performance"):
        if not _column_exists(connection, "c_class", "employee_performance", "员工编号"):
            op.add_column("employee_performance", sa.Column("员工编号", sa.String(length=64), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_performance", "年月"):
            op.add_column("employee_performance", sa.Column("年月", sa.String(length=7), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_performance", "实际销售额"):
            op.add_column("employee_performance", sa.Column("实际销售额", sa.Numeric(15, 2), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_performance", "达成率"):
            op.add_column("employee_performance", sa.Column("达成率", sa.Float(), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_performance", "绩效得分"):
            op.add_column("employee_performance", sa.Column("绩效得分", sa.Float(), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_performance", "计算时间"):
            op.add_column("employee_performance", sa.Column("计算时间", sa.DateTime(timezone=True), nullable=True), schema="c_class")
        op.execute(
            sa.text(
                """
                UPDATE c_class.employee_performance
                SET "员工编号" = employee_code,
                    "年月" = year_month,
                    "实际销售额" = actual_sales,
                    "达成率" = achievement_rate,
                    "绩效得分" = performance_score,
                    "计算时间" = calculated_at
                """
            )
        )

    if _table_exists(connection, "c_class", "employee_commissions"):
        if not _column_exists(connection, "c_class", "employee_commissions", "员工编号"):
            op.add_column("employee_commissions", sa.Column("员工编号", sa.String(length=64), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_commissions", "年月"):
            op.add_column("employee_commissions", sa.Column("年月", sa.String(length=7), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_commissions", "销售额"):
            op.add_column("employee_commissions", sa.Column("销售额", sa.Numeric(15, 2), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_commissions", "提成金额"):
            op.add_column("employee_commissions", sa.Column("提成金额", sa.Numeric(15, 2), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_commissions", "提成比例"):
            op.add_column("employee_commissions", sa.Column("提成比例", sa.Float(), nullable=True), schema="c_class")
        if not _column_exists(connection, "c_class", "employee_commissions", "计算时间"):
            op.add_column("employee_commissions", sa.Column("计算时间", sa.DateTime(timezone=True), nullable=True), schema="c_class")
        op.execute(
            sa.text(
                """
                UPDATE c_class.employee_commissions
                SET "员工编号" = employee_code,
                    "年月" = year_month,
                    "销售额" = sales_amount,
                    "提成金额" = commission_amount,
                    "提成比例" = commission_rate,
                    "计算时间" = calculated_at
                """
            )
        )
