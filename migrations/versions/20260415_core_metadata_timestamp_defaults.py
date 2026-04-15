"""Repair core metadata table timestamp defaults.

Revision ID: 20260415_core_metadata_ts
Revises: 20260415_core_runtime_ts
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_core_metadata_ts"
down_revision = "20260415_core_runtime_ts"
branch_labels = None
depends_on = None


TARGET_COLUMNS = {
    "field_mappings": ("created_at",),
    "field_mapping_template_items": ("created_at",),
    "dim_currencies": ("created_at",),
    "dim_fiscal_calendar": ("created_at",),
    "dim_vendors": ("created_at", "updated_at"),
}


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


def _repair_column(schema_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {schema_name}.{table_name}
            SET {column_name} = now()
            WHERE {column_name} IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {schema_name}.{table_name}
            ALTER COLUMN {column_name} SET DEFAULT now()
            """
        )
    )


def _drop_default(schema_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {schema_name}.{table_name}
            ALTER COLUMN {column_name} DROP DEFAULT
            """
        )
    )


def upgrade() -> None:
    connection = op.get_bind()

    for table_name, columns in TARGET_COLUMNS.items():
        if not _table_exists(connection, "core", table_name):
            continue
        for column_name in columns:
            if _column_exists(connection, "core", table_name, column_name):
                _repair_column("core", table_name, column_name)


def downgrade() -> None:
    connection = op.get_bind()

    for table_name, columns in TARGET_COLUMNS.items():
        if not _table_exists(connection, "core", table_name):
            continue
        for column_name in columns:
            if _column_exists(connection, "core", table_name, column_name):
                _drop_default("core", table_name, column_name)
