"""Add independent monthly payroll manual inputs."""

from alembic import op
import sqlalchemy as sa


revision = "20260909_payroll_manual_inputs"
down_revision = "20260826_unify_profit_basis_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_manual_inputs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("overtime_pay", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("bonus", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("social_insurance_personal", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("housing_fund_personal", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("income_tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("other_deductions", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("social_insurance_company", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("housing_fund_company", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("backfill_source_month", sa.String(length=7), nullable=True),
        sa.Column("backfill_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_code", "year_month", name="uq_payroll_manual_inputs_employee_month"),
        schema="a_class",
    )
    op.create_index(
        "ix_payroll_manual_inputs_employee",
        "payroll_manual_inputs",
        ["employee_code"],
        schema="a_class",
    )
    op.create_index(
        "ix_payroll_manual_inputs_month",
        "payroll_manual_inputs",
        ["year_month"],
        schema="a_class",
    )
    op.execute(
        sa.text(
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
    )


def downgrade() -> None:
    op.drop_index("ix_payroll_manual_inputs_month", table_name="payroll_manual_inputs", schema="a_class")
    op.drop_index("ix_payroll_manual_inputs_employee", table_name="payroll_manual_inputs", schema="a_class")
    op.drop_table("payroll_manual_inputs", schema="a_class")
