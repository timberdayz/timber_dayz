"""repair field mapping template timestamp defaults

Revision ID: 20260409_field_mapping_template_timestamp_defaults
Revises: 20260407_follow_investment_profit_basis
Create Date: 2026-04-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_field_mapping_template_timestamp_defaults"
down_revision = "20260407_follow_investment_profit_basis"
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"
TABLE_NAME = "field_mapping_templates"


def _table_exists(connection: sa.Connection, schema_name: str, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    try:
        return table_name in set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return False


def _column_exists(connection: sa.Connection, schema_name: str, table_name: str, column_name: str) -> bool:
    rows = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    ).fetchall()
    return bool(rows)


def _set_default_now_if_present(connection: sa.Connection, column_name: str) -> None:
    if not _column_exists(connection, CORE_SCHEMA, TABLE_NAME, column_name):
        return
    op.execute(
        sa.text(
            f"ALTER TABLE {CORE_SCHEMA}.{TABLE_NAME} "
            f"ALTER COLUMN {column_name} SET DEFAULT now()"
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, CORE_SCHEMA, TABLE_NAME):
        return

    _set_default_now_if_present(connection, "created_at")
    _set_default_now_if_present(connection, "updated_at")


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, CORE_SCHEMA, TABLE_NAME):
        return

    if _column_exists(connection, CORE_SCHEMA, TABLE_NAME, "updated_at"):
        op.execute(
            sa.text(
                f"ALTER TABLE {CORE_SCHEMA}.{TABLE_NAME} "
                "ALTER COLUMN updated_at DROP DEFAULT"
            )
        )

    if _column_exists(connection, CORE_SCHEMA, TABLE_NAME, "created_at"):
        op.execute(
            sa.text(
                f"ALTER TABLE {CORE_SCHEMA}.{TABLE_NAME} "
                "ALTER COLUMN created_at DROP DEFAULT"
            )
        )
