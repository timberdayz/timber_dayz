"""Add payroll manual inputs to the isolated current-schema chain."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260910_payroll_manual_inputs"
down_revision = "current_schema_20260910_product_profit_finalization"
branch_labels = None
depends_on = None


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("payroll_manual_inputs", schema="a_class")


def upgrade() -> None:
    if not _table_exists():
        op.create_table(
            "payroll_manual_inputs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("employee_code", sa.String(64), nullable=False),
            sa.Column("year_month", sa.String(7), nullable=False),
            sa.Column("overtime_pay", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("bonus", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("social_insurance_personal", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("housing_fund_personal", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("income_tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("other_deductions", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("social_insurance_company", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("housing_fund_company", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("pay_date", sa.Date()),
            sa.Column("remark", sa.Text()),
            sa.Column("backfill_source_month", sa.String(7)),
            sa.Column("backfill_note", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("employee_code", "year_month", name="uq_payroll_manual_inputs_employee_month"),
            schema="a_class",
        )
    op.create_index("ix_payroll_manual_inputs_employee", "payroll_manual_inputs", ["employee_code"], schema="a_class", if_not_exists=True)
    op.create_index("ix_payroll_manual_inputs_month", "payroll_manual_inputs", ["year_month"], schema="a_class", if_not_exists=True)
    op.execute(
        """
        INSERT INTO a_class.payroll_manual_inputs (
            employee_code, year_month, overtime_pay, bonus,
            social_insurance_personal, housing_fund_personal, income_tax,
            other_deductions, social_insurance_company, housing_fund_company,
            pay_date, remark, backfill_source_month, backfill_note
        )
        SELECT employee_code, year_month, overtime_pay, bonus,
               social_insurance_personal, housing_fund_personal, income_tax,
               other_deductions, social_insurance_company, housing_fund_company,
               pay_date, remark, backfill_source_month, backfill_note
        FROM a_class.payroll_records
        WHERE status = 'draft'
        ON CONFLICT (employee_code, year_month) DO NOTHING
        """
    )


def downgrade() -> None:
    # The table may predate this current-schema increment through the legacy chain.
    # Never remove a compatible existing table during a current-chain downgrade.
    pass
