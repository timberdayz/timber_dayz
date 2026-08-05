"""Add audit fields for next-month payroll supplements.

Revision ID: 20260805_payroll_backfill_audit
Revises: 20260804_employee_labor_cost_allocations
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_payroll_backfill_audit"
down_revision = "20260804_employee_labor_cost_allocations"
branch_labels = None
depends_on = None


def _column_names(connection) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(connection).get_columns(
            "payroll_records", schema="a_class"
        )
    }


def upgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if "backfill_source_month" not in columns:
        op.add_column(
            "payroll_records",
            sa.Column("backfill_source_month", sa.String(length=7), nullable=True),
            schema="a_class",
        )
    if "backfill_note" not in columns:
        op.add_column(
            "payroll_records",
            sa.Column("backfill_note", sa.Text(), nullable=True),
            schema="a_class",
        )


def downgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if "backfill_note" in columns:
        op.drop_column("payroll_records", "backfill_note", schema="a_class")
    if "backfill_source_month" in columns:
        op.drop_column("payroll_records", "backfill_source_month", schema="a_class")
