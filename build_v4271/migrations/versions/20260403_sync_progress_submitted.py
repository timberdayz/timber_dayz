"""Allow legacy submitted status in sync_progress_tasks for backward compatibility.

Revision ID: 20260403_sync_progress_submitted
Revises: 20260403_sync_nulls
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_sync_progress_submitted"
down_revision = "20260403_sync_nulls"
branch_labels = None
depends_on = None


def _table_exists(schema_name: str, table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names(schema=schema_name)


def upgrade() -> None:
    if not _table_exists("core", "sync_progress_tasks"):
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE core.sync_progress_tasks
            DROP CONSTRAINT IF EXISTS chk_sync_progress_status
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE core.sync_progress_tasks
            ADD CONSTRAINT chk_sync_progress_status
            CHECK (status IN ('pending', 'submitted', 'processing', 'completed', 'failed'))
            """
        )
    )


def downgrade() -> None:
    if not _table_exists("core", "sync_progress_tasks"):
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE core.sync_progress_tasks
            DROP CONSTRAINT IF EXISTS chk_sync_progress_status
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE core.sync_progress_tasks
            ADD CONSTRAINT chk_sync_progress_status
            CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
            """
        )
    )
