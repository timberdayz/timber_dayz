"""archive public.dim_shops after core canonical cutover

Revision ID: 20260328_dim_shops_archive
Revises: 20260328_dim_shops_core
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_dim_shops_archive"
down_revision = "20260328_dim_shops_core"
branch_labels = None
depends_on = None


SOURCE_SCHEMA = "public"
SOURCE_TABLE = "dim_shops"
ARCHIVE_TABLE = "dim_shops__archive_retired"
CANONICAL_SCHEMA = "core"
CANONICAL_TABLE = "dim_shops"


def _table_exists(connection, schema: str, table_name: str) -> bool:
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
        {"schema_name": schema, "table_name": table_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    """Archive rename public.dim_shops -> public.dim_shops__archive_retired."""
    connection = op.get_bind()

    public_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)
    core_exists = _table_exists(connection, CANONICAL_SCHEMA, CANONICAL_TABLE)

    if public_exists and core_exists and not archive_exists:
        op.rename_table(SOURCE_TABLE, ARCHIVE_TABLE, schema=SOURCE_SCHEMA)


def downgrade() -> None:
    """Restore public.dim_shops from public.dim_shops__archive_retired."""
    connection = op.get_bind()

    public_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)

    if archive_exists and not public_exists:
        op.rename_table(ARCHIVE_TABLE, SOURCE_TABLE, schema=SOURCE_SCHEMA)
