"""Add header bindings to field mapping templates.

Revision ID: 20260525_header_bindings
Revises: 20260521_operating_costs_add_cost_total_note_lock
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_header_bindings"
down_revision = "20260521_operating_costs_add_cost_total_note_lock"
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
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "core", "field_mapping_templates"):
        return

    if not _column_exists(connection, "core", "field_mapping_templates", "header_bindings"):
        op.add_column(
            "field_mapping_templates",
            sa.Column(
                "header_bindings",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment="模板列语义绑定(JSONB数组)",
            ),
            schema="core",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "core", "field_mapping_templates"):
        return

    if _column_exists(connection, "core", "field_mapping_templates", "header_bindings"):
        op.drop_column("field_mapping_templates", "header_bindings", schema="core")
