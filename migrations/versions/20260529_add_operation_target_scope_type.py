"""add operation target scope type

Revision ID: 20260529_add_operation_target_scope_type
Revises: 20260529_add_employee_performance_input_domain, 20260529_add_monthly_profit_snapshots
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_add_operation_target_scope_type"
down_revision = (
    "20260529_add_employee_performance_input_domain",
    "20260529_add_monthly_profit_snapshots",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_targets",
        sa.Column("scope_type", sa.String(length=32), nullable=True),
        schema="a_class",
    )
    op.execute(
        """
        UPDATE a_class.sales_targets
        SET scope_type = 'shop'
        WHERE target_type = 'operation'
          AND (scope_type IS NULL OR scope_type = '')
        """
    )


def downgrade() -> None:
    op.drop_column("sales_targets", "scope_type", schema="a_class")
