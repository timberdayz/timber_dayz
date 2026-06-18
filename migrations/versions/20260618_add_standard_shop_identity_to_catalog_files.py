"""Add standard shop identity fields to catalog_files.

Revision ID: 20260618_catalog_shop_identity
Revises: 20260618_semantic_field_contracts
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260618_catalog_shop_identity"
down_revision = "20260618_semantic_field_contracts"
branch_labels = None
depends_on = None


def _catalog_files_schema(connection) -> str | None:
    result = connection.execute(
        sa.text(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name = 'catalog_files'
              AND table_schema IN ('public', 'core')
            ORDER BY CASE table_schema WHEN 'public' THEN 0 ELSE 1 END
            LIMIT 1
            """
        )
    )
    return result.scalar()


def _column_exists(connection, schema: str, column_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = 'catalog_files'
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"schema": schema, "column_name": column_name},
    )
    return result.scalar() is not None


def _index_exists(connection, schema: str, index_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = :schema
              AND tablename = 'catalog_files'
              AND indexname = :index_name
            LIMIT 1
            """
        ),
        {"schema": schema, "index_name": index_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    schema = _catalog_files_schema(connection)
    if not schema:
        return

    columns = (
        sa.Column("main_account_id", sa.String(length=100), nullable=True),
        sa.Column("shop_account_id", sa.String(length=100), nullable=True),
        sa.Column("store_name", sa.String(length=200), nullable=True),
        sa.Column("platform_shop_id", sa.String(length=256), nullable=True),
    )
    for column in columns:
        if not _column_exists(connection, schema, column.name):
            op.add_column("catalog_files", column, schema=None if schema == "public" else schema)

    if not _index_exists(connection, schema, "ix_catalog_files_shop_account_id"):
        op.create_index(
            "ix_catalog_files_shop_account_id",
            "catalog_files",
            ["shop_account_id"],
            unique=False,
            schema=None if schema == "public" else schema,
        )


def downgrade() -> None:
    connection = op.get_bind()
    schema = _catalog_files_schema(connection)
    if not schema:
        return

    if _index_exists(connection, schema, "ix_catalog_files_shop_account_id"):
        op.drop_index(
            "ix_catalog_files_shop_account_id",
            table_name="catalog_files",
            schema=None if schema == "public" else schema,
        )

    for column_name in ("platform_shop_id", "store_name", "shop_account_id", "main_account_id"):
        if _column_exists(connection, schema, column_name):
            op.drop_column("catalog_files", column_name, schema=None if schema == "public" else schema)
