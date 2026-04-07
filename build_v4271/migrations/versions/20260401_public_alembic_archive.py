"""archive public.alembic_version after core version table cutover

Revision ID: 20260401_public_alembic_archive
Revises: 20260401_collection_exec_mode
Create Date: 2026-04-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_public_alembic_archive"
down_revision = "20260401_collection_exec_mode"
branch_labels = None
depends_on = None


SOURCE_SCHEMA = "public"
SOURCE_TABLE = "alembic_version"
ARCHIVE_TABLE = "alembic_version__archive_retired"
CANONICAL_SCHEMA = "core"
CANONICAL_TABLE = "alembic_version"


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
    """Archive rename public.alembic_version -> public.alembic_version__archive_retired."""
    connection = op.get_bind()

    public_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)
    core_exists = _table_exists(connection, CANONICAL_SCHEMA, CANONICAL_TABLE)

    if public_exists and core_exists and not archive_exists:
        op.rename_table(SOURCE_TABLE, ARCHIVE_TABLE, schema=SOURCE_SCHEMA)


def downgrade() -> None:
    """Restore public.alembic_version from public.alembic_version__archive_retired."""
    connection = op.get_bind()

    public_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)

    if archive_exists and not public_exists:
        op.rename_table(ARCHIVE_TABLE, SOURCE_TABLE, schema=SOURCE_SCHEMA)
