"""Add English columns to c_class employee metric tables.

Revision ID: 20260415_c_class_employee_metrics_en
Revises: 20260415_employee_identity, 20260415_finance_ts
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_c_class_employee_metrics_en"
down_revision = ("20260415_employee_identity", "20260415_finance_ts")
branch_labels = None
depends_on = None


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


def _constraint_exists(connection, schema_name: str, table_name: str, constraint_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND constraint_name = :constraint_name
            LIMIT 1
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "constraint_name": constraint_name,
        },
    )
    return result.scalar() is not None


def _index_exists(connection, schema_name: str, table_name: str, index_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = :schema_name
              AND tablename = :table_name
              AND indexname = :index_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name, "index_name": index_name},
    )
    return result.scalar() is not None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    connection = op.get_bind()
    if not _column_exists(connection, "c_class", table_name, column.name):
        op.add_column(table_name, column, schema="c_class")


def _has_all_columns(connection, table_name: str, columns: list[str]) -> bool:
    return all(
        _column_exists(connection, "c_class", table_name, column_name)
        for column_name in columns
    )


def upgrade() -> None:
    connection = op.get_bind()

    if _table_exists(connection, "c_class", "employee_performance"):
        legacy_employee_performance_columns = [
            "员工编号",
            "年月",
            "实际销售额",
            "达成率",
            "绩效得分",
            "计算时间",
        ]
        _add_column_if_missing(
            "employee_performance",
            sa.Column("employee_code", sa.String(length=64), nullable=True),
        )
        _add_column_if_missing(
            "employee_performance",
            sa.Column("year_month", sa.String(length=7), nullable=True),
        )
        _add_column_if_missing(
            "employee_performance",
            sa.Column("actual_sales", sa.Numeric(15, 2), nullable=True),
        )
        _add_column_if_missing(
            "employee_performance",
            sa.Column("achievement_rate", sa.Float(), nullable=True),
        )
        _add_column_if_missing(
            "employee_performance",
            sa.Column("performance_score", sa.Float(), nullable=True),
        )
        _add_column_if_missing(
            "employee_performance",
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        )

        if _has_all_columns(connection, "employee_performance", legacy_employee_performance_columns):
            op.execute(
                sa.text(
                    """
                    UPDATE c_class.employee_performance
                    SET employee_code = "员工编号",
                        year_month = "年月",
                        actual_sales = "实际销售额",
                        achievement_rate = "达成率",
                        performance_score = "绩效得分",
                        calculated_at = "计算时间"
                    WHERE employee_code IS NULL
                       OR year_month IS NULL
                       OR actual_sales IS NULL
                       OR achievement_rate IS NULL
                       OR performance_score IS NULL
                       OR calculated_at IS NULL
                    """
                )
            )

        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN employee_code SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN year_month SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN actual_sales SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN achievement_rate SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN performance_score SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_performance ALTER COLUMN calculated_at SET NOT NULL"""))

        if not _constraint_exists(connection, "c_class", "employee_performance", "uq_employee_performance_c"):
            op.create_unique_constraint(
                "uq_employee_performance_c",
                "employee_performance",
                ["employee_code", "year_month"],
                schema="c_class",
            )
        if not _index_exists(connection, "c_class", "employee_performance", "ix_employee_performance_c_employee"):
            op.create_index(
                "ix_employee_performance_c_employee",
                "employee_performance",
                ["employee_code"],
                unique=False,
                schema="c_class",
            )
        if not _index_exists(connection, "c_class", "employee_performance", "ix_employee_performance_c_month"):
            op.create_index(
                "ix_employee_performance_c_month",
                "employee_performance",
                ["year_month"],
                unique=False,
                schema="c_class",
            )

    if _table_exists(connection, "c_class", "employee_commissions"):
        legacy_employee_commission_columns = [
            "员工编号",
            "年月",
            "销售额",
            "提成金额",
            "提成比例",
            "计算时间",
        ]
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("employee_code", sa.String(length=64), nullable=True),
        )
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("year_month", sa.String(length=7), nullable=True),
        )
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("sales_amount", sa.Numeric(15, 2), nullable=True),
        )
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("commission_amount", sa.Numeric(15, 2), nullable=True),
        )
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("commission_rate", sa.Float(), nullable=True),
        )
        _add_column_if_missing(
            "employee_commissions",
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        )

        if _has_all_columns(connection, "employee_commissions", legacy_employee_commission_columns):
            op.execute(
                sa.text(
                    """
                    UPDATE c_class.employee_commissions
                    SET employee_code = "员工编号",
                        year_month = "年月",
                        sales_amount = "销售额",
                        commission_amount = "提成金额",
                        commission_rate = "提成比例",
                        calculated_at = "计算时间"
                    WHERE employee_code IS NULL
                       OR year_month IS NULL
                       OR sales_amount IS NULL
                       OR commission_amount IS NULL
                       OR commission_rate IS NULL
                       OR calculated_at IS NULL
                    """
                )
            )

        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN employee_code SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN year_month SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN sales_amount SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN commission_amount SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN commission_rate SET NOT NULL"""))
        op.execute(sa.text("""ALTER TABLE c_class.employee_commissions ALTER COLUMN calculated_at SET NOT NULL"""))

        if not _constraint_exists(connection, "c_class", "employee_commissions", "uq_employee_commissions_c"):
            op.create_unique_constraint(
                "uq_employee_commissions_c",
                "employee_commissions",
                ["employee_code", "year_month"],
                schema="c_class",
            )
        if not _index_exists(connection, "c_class", "employee_commissions", "ix_employee_commissions_c_employee"):
            op.create_index(
                "ix_employee_commissions_c_employee",
                "employee_commissions",
                ["employee_code"],
                unique=False,
                schema="c_class",
            )
        if not _index_exists(connection, "c_class", "employee_commissions", "ix_employee_commissions_c_month"):
            op.create_index(
                "ix_employee_commissions_c_month",
                "employee_commissions",
                ["year_month"],
                unique=False,
                schema="c_class",
            )


def downgrade() -> None:
    connection = op.get_bind()

    if _table_exists(connection, "c_class", "employee_commissions"):
        if _index_exists(connection, "c_class", "employee_commissions", "ix_employee_commissions_c_month"):
            op.drop_index("ix_employee_commissions_c_month", table_name="employee_commissions", schema="c_class")
        if _index_exists(connection, "c_class", "employee_commissions", "ix_employee_commissions_c_employee"):
            op.drop_index("ix_employee_commissions_c_employee", table_name="employee_commissions", schema="c_class")
        if _constraint_exists(connection, "c_class", "employee_commissions", "uq_employee_commissions_c"):
            op.drop_constraint("uq_employee_commissions_c", "employee_commissions", schema="c_class", type_="unique")
        for column_name in ("calculated_at", "commission_rate", "commission_amount", "sales_amount", "year_month", "employee_code"):
            if _column_exists(connection, "c_class", "employee_commissions", column_name):
                op.drop_column("employee_commissions", column_name, schema="c_class")

    if _table_exists(connection, "c_class", "employee_performance"):
        if _index_exists(connection, "c_class", "employee_performance", "ix_employee_performance_c_month"):
            op.drop_index("ix_employee_performance_c_month", table_name="employee_performance", schema="c_class")
        if _index_exists(connection, "c_class", "employee_performance", "ix_employee_performance_c_employee"):
            op.drop_index("ix_employee_performance_c_employee", table_name="employee_performance", schema="c_class")
        if _constraint_exists(connection, "c_class", "employee_performance", "uq_employee_performance_c"):
            op.drop_constraint("uq_employee_performance_c", "employee_performance", schema="c_class", type_="unique")
        for column_name in ("calculated_at", "performance_score", "achievement_rate", "actual_sales", "year_month", "employee_code"):
            if _column_exists(connection, "c_class", "employee_performance", column_name):
                op.drop_column("employee_performance", column_name, schema="c_class")
