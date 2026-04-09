"""add execution_mode to collection_configs

Revision ID: 20260401_collection_exec_mode
Revises: 20260328_dim_shops_archive
Create Date: 2026-04-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_collection_exec_mode"
down_revision = "20260328_dim_shops_archive"
branch_labels = None
depends_on = None


TABLE_NAME = "collection_configs"
COLUMN_NAME = "execution_mode"
SCHEMA_NAME = "core"


def _column_names(connection, table_name: str, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return {
            column["name"] for column in inspector.get_columns(table_name, schema=schema_name)
        }
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection, TABLE_NAME, SCHEMA_NAME)

    if COLUMN_NAME not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(length=20), nullable=True, server_default="headless"),
            schema=SCHEMA_NAME,
        )

    connection.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA_NAME}.{TABLE_NAME}
            SET {COLUMN_NAME} = 'headless'
            WHERE {COLUMN_NAME} IS NULL
            """
        )
    )

    op.alter_column(
        TABLE_NAME,
        COLUMN_NAME,
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="headless",
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection, TABLE_NAME, SCHEMA_NAME)
    if COLUMN_NAME in columns:
        op.drop_column(TABLE_NAME, COLUMN_NAME, schema=SCHEMA_NAME)
