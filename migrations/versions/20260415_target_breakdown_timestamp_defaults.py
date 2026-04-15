"""Repair target_breakdown timestamp defaults in a_class.

Revision ID: 20260415_target_breakdown_ts
Revises: 20260413_refresh_queue
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_target_breakdown_ts"
down_revision = "20260413_refresh_queue"
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

    if not _table_exists(connection, "a_class", "target_breakdown"):
        return

    if _column_exists(connection, "a_class", "target_breakdown", "created_at"):
        op.execute(
            sa.text(
                """
                UPDATE a_class.target_breakdown
                SET created_at = now()
                WHERE created_at IS NULL
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE a_class.target_breakdown
                ALTER COLUMN created_at SET DEFAULT now()
                """
            )
        )

    if _column_exists(connection, "a_class", "target_breakdown", "updated_at"):
        op.execute(
            sa.text(
                """
                UPDATE a_class.target_breakdown
                SET updated_at = now()
                WHERE updated_at IS NULL
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE a_class.target_breakdown
                ALTER COLUMN updated_at SET DEFAULT now()
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()

    if not _table_exists(connection, "a_class", "target_breakdown"):
        return

    if _column_exists(connection, "a_class", "target_breakdown", "created_at"):
        op.execute(
            sa.text(
                """
                ALTER TABLE a_class.target_breakdown
                ALTER COLUMN created_at DROP DEFAULT
                """
            )
        )

    if _column_exists(connection, "a_class", "target_breakdown", "updated_at"):
        op.execute(
            sa.text(
                """
                ALTER TABLE a_class.target_breakdown
                ALTER COLUMN updated_at DROP DEFAULT
                """
            )
        )
