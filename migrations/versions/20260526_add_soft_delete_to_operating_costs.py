"""Add soft delete columns to operating_costs.

Revision ID: 20260526_add_soft_delete_to_operating_costs
Revises: 20260526_add_platform_code_to_operating_costs
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_add_soft_delete_to_operating_costs"
down_revision = "20260526_add_platform_code_to_operating_costs"
branch_labels = None
depends_on = None


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
    if not _column_exists(connection, "a_class", "operating_costs", "删除时间"):
        op.add_column(
            "operating_costs",
            sa.Column("删除时间", sa.DateTime(timezone=True), nullable=True),
            schema="a_class",
        )
    if not _column_exists(connection, "a_class", "operating_costs", "删除人"):
        op.add_column(
            "operating_costs",
            sa.Column("删除人", sa.BigInteger(), nullable=True),
            schema="a_class",
        )
    op.create_index(
        "ix_operating_costs_deleted_at",
        "operating_costs",
        ["删除时间"],
        unique=False,
        schema="a_class",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_operating_costs_deleted_at", table_name="operating_costs", schema="a_class")
    op.drop_column("operating_costs", "删除人", schema="a_class")
    op.drop_column("operating_costs", "删除时间", schema="a_class")
