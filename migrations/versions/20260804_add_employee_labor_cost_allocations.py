"""Create employee labor-cost allocation records used by profit-basis V2.

Revision ID: 20260804_employee_labor_cost_allocations
Revises: 20260803_settlement_profit_target
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_employee_labor_cost_allocations"
down_revision = "20260803_settlement_profit_target"
branch_labels = None
depends_on = None


def _table_exists(connection) -> bool:
    return sa.inspect(connection).has_table(
        "employee_labor_cost_allocations", schema="finance"
    )


def upgrade() -> None:
    connection = op.get_bind()
    if _table_exists(connection):
        return

    op.create_table(
        "employee_labor_cost_allocations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period_month", sa.String(length=16), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=True),
        sa.Column("shop_id", sa.String(length=256), nullable=True),
        sa.Column("allocation_scope", sa.String(length=16), nullable=False),
        sa.Column("allocation_ratio", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("pre_commission_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("performance_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("source_payroll_record_id", sa.BigInteger(), nullable=True),
        sa.Column("source_payroll_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("calculation_status", sa.String(length=32), nullable=False, server_default="projected"),
        sa.Column("calculation_version", sa.String(length=64), nullable=False, server_default="LABOR_COST_V1"),
        sa.Column("pre_commission_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("allocation_scope IN ('shop', 'company')", name="ck_employee_labor_cost_scope"),
        sa.ForeignKeyConstraint(["period_month"], ["core.dim_fiscal_calendar.period_code"]),
        schema="finance",
    )
    op.create_index(
        "ix_employee_labor_cost_period",
        "employee_labor_cost_allocations",
        ["period_month"],
        schema="finance",
    )
    op.create_index(
        "ix_employee_labor_cost_employee",
        "employee_labor_cost_allocations",
        ["employee_code", "period_month"],
        schema="finance",
    )
    op.create_index(
        "ix_employee_labor_cost_shop",
        "employee_labor_cost_allocations",
        ["platform_code", "shop_id", "period_month"],
        schema="finance",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_employee_labor_cost_shop_scope
        ON finance.employee_labor_cost_allocations
        (period_month, employee_code, platform_code, shop_id, calculation_version)
        WHERE allocation_scope = 'shop'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_employee_labor_cost_company_scope
        ON finance.employee_labor_cost_allocations
        (period_month, employee_code, calculation_version)
        WHERE allocation_scope = 'company'
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    if _table_exists(connection):
        op.drop_table("employee_labor_cost_allocations", schema="finance")
