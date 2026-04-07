"""Align catalog_files.source default with canonical data/raw storage.

Revision ID: 20260327_catalog_source
Revises: 20260326_target_ext
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_catalog_source"
down_revision = "20260326_target_ext"
branch_labels = None
depends_on = None


def _table_exists(table_name: str, schema: str | None = None) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names(schema=schema)


def _column_exists(table_name: str, column_name: str, schema: str | None = None) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {col["name"] for col in inspector.get_columns(table_name, schema=schema)}


def upgrade() -> None:
    if not _table_exists("catalog_files"):
        return

    if _column_exists("catalog_files", "source"):
        op.alter_column(
            "catalog_files",
            "source",
            existing_type=sa.String(length=64),
            server_default=sa.text("'data/raw'"),
            existing_nullable=False,
        )

        op.execute(
            sa.text(
                """
                UPDATE catalog_files
                SET source = 'data/raw'
                WHERE source = 'temp/outputs'
                  AND file_path LIKE 'data/raw/%'
                """
            )
        )


def downgrade() -> None:
    if not _table_exists("catalog_files"):
        return

    if _column_exists("catalog_files", "source"):
        op.alter_column(
            "catalog_files",
            "source",
            existing_type=sa.String(length=64),
            server_default=sa.text("'temp/outputs'"),
            existing_nullable=False,
        )
