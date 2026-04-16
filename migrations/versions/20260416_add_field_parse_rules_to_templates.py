"""Add field parse rules to field mapping templates.

Revision ID: 20260416_field_parse_rules
Revises: 20260415_c_class_employee_metrics_cleanup
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260416_field_parse_rules"
down_revision = "20260415_c_class_employee_metrics_cleanup"
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

    if not _column_exists(connection, "core", "field_mapping_templates", "field_parse_rules"):
        op.add_column(
            "field_mapping_templates",
            sa.Column(
                "field_parse_rules",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment="字段解析规则(JSONB数组)",
            ),
            schema="core",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "core", "field_mapping_templates"):
        return

    if _column_exists(connection, "core", "field_mapping_templates", "field_parse_rules"):
        op.drop_column("field_mapping_templates", "field_parse_rules", schema="core")
