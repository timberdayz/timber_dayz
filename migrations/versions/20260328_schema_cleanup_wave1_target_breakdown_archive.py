"""schema cleanup wave 1 target_breakdown archive rename

Revision ID: 20260328_schema_cleanup_wave1
Revises: 20260328_task_center_merge
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_schema_cleanup_wave1"
down_revision = "20260328_task_center_merge"
branch_labels = None
depends_on = None


SOURCE_SCHEMA = "public"
SOURCE_TABLE = "target_breakdown"
ARCHIVE_TABLE = "target_breakdown__archive_wave1"


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
    """Archive rename for the duplicate public target_breakdown table."""
    connection = op.get_bind()

    source_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)

    if source_exists and not archive_exists:
        op.rename_table(SOURCE_TABLE, ARCHIVE_TABLE, schema=SOURCE_SCHEMA)


def downgrade() -> None:
    """Restore the archived public target_breakdown table name."""
    connection = op.get_bind()

    source_exists = _table_exists(connection, SOURCE_SCHEMA, SOURCE_TABLE)
    archive_exists = _table_exists(connection, SOURCE_SCHEMA, ARCHIVE_TABLE)

    if archive_exists and not source_exists:
        op.rename_table(ARCHIVE_TABLE, SOURCE_TABLE, schema=SOURCE_SCHEMA)
