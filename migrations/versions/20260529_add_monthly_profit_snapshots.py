"""add monthly profit snapshot tables

Revision ID: 20260529_add_monthly_profit_snapshots
Revises: 20260527_salary_structures_versioning
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260529_add_monthly_profit_snapshots"
down_revision = "20260527_salary_structures_versioning"
branch_labels = None
depends_on = None

FINANCE_SCHEMA = "finance"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {FINANCE_SCHEMA}"))
    table_names = _table_names(connection, FINANCE_SCHEMA)

    if "monthly_profit_shop_basis_snapshots" not in table_names:
        op.create_table(
            "monthly_profit_shop_basis_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("period_month", sa.String(length=16), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=256), nullable=False),
            sa.Column("shop_name", sa.String(length=256), nullable=True),
            sa.Column("basis_version", sa.String(length=64), nullable=True),
            sa.Column("orders_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("a_class_cost_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("profit_basis_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.UniqueConstraint(
                "settlement_id",
                "snapshot_version",
                "platform_code",
                "shop_id",
                name="uq_monthly_profit_shop_basis_snapshots",
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_shop_basis_snapshots_settlement",
            "monthly_profit_shop_basis_snapshots",
            ["settlement_id", "snapshot_status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_employee_commission_snapshots" not in table_names:
        op.create_table(
            "monthly_profit_employee_commission_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("period_month", sa.String(length=16), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("employee_code", sa.String(length=64), nullable=False),
            sa.Column("employee_name", sa.String(length=128), nullable=True),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=256), nullable=False),
            sa.Column("shop_name", sa.String(length=256), nullable=True),
            sa.Column("sales_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("commission_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("commission_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.UniqueConstraint(
                "settlement_id",
                "snapshot_version",
                "employee_code",
                "platform_code",
                "shop_id",
                name="uq_monthly_profit_employee_commission_snapshots",
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_employee_commission_snapshots_settlement",
            "monthly_profit_employee_commission_snapshots",
            ["settlement_id", "snapshot_status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_employee_performance_snapshots" not in table_names:
        op.create_table(
            "monthly_profit_employee_performance_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("period_month", sa.String(length=16), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("employee_code", sa.String(length=64), nullable=False),
            sa.Column("employee_name", sa.String(length=128), nullable=True),
            sa.Column("actual_sales", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("achievement_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("performance_score", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("attendance_adjustment_score", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("manual_adjustment_score", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.UniqueConstraint(
                "settlement_id",
                "snapshot_version",
                "employee_code",
                name="uq_monthly_profit_employee_performance_snapshots",
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_employee_performance_snapshots_settlement",
            "monthly_profit_employee_performance_snapshots",
            ["settlement_id", "snapshot_status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_payroll_snapshots" not in table_names:
        op.create_table(
            "monthly_profit_payroll_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("period_month", sa.String(length=16), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("payroll_record_id", sa.BigInteger(), nullable=True),
            sa.Column("employee_code", sa.String(length=64), nullable=False),
            sa.Column("employee_name", sa.String(length=128), nullable=True),
            sa.Column("base_salary", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("position_salary", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("performance_salary", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("overtime_pay", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("commission", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("allowances", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("bonus", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("gross_salary", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("social_insurance_personal", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("housing_fund_personal", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("income_tax", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("other_deductions", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("total_deductions", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("net_salary", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("social_insurance_company", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("housing_fund_company", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("total_cost", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")),
            sa.Column("payroll_status", sa.String(length=32), nullable=True),
            sa.Column("pay_date", sa.Date(), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.UniqueConstraint(
                "settlement_id",
                "snapshot_version",
                "employee_code",
                name="uq_monthly_profit_payroll_snapshots",
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_payroll_snapshots_settlement",
            "monthly_profit_payroll_snapshots",
            ["settlement_id", "snapshot_status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, FINANCE_SCHEMA)

    if "monthly_profit_payroll_snapshots" in table_names:
        op.drop_index(
            "ix_monthly_profit_payroll_snapshots_settlement",
            table_name="monthly_profit_payroll_snapshots",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_payroll_snapshots", schema=FINANCE_SCHEMA)

    if "monthly_profit_employee_performance_snapshots" in table_names:
        op.drop_index(
            "ix_monthly_profit_employee_performance_snapshots_settlement",
            table_name="monthly_profit_employee_performance_snapshots",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_employee_performance_snapshots", schema=FINANCE_SCHEMA)

    if "monthly_profit_employee_commission_snapshots" in table_names:
        op.drop_index(
            "ix_monthly_profit_employee_commission_snapshots_settlement",
            table_name="monthly_profit_employee_commission_snapshots",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_employee_commission_snapshots", schema=FINANCE_SCHEMA)

    if "monthly_profit_shop_basis_snapshots" in table_names:
        op.drop_index(
            "ix_monthly_profit_shop_basis_snapshots_settlement",
            table_name="monthly_profit_shop_basis_snapshots",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_shop_basis_snapshots", schema=FINANCE_SCHEMA)
