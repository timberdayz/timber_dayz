"""Repair dim_shops timestamp defaults in core.

Revision ID: 20260415_dim_shops_ts
Revises: 20260415_target_breakdown_ts
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_dim_shops_ts"
down_revision = "20260415_target_breakdown_ts"
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

    if not _table_exists(connection, "core", "dim_shops"):
        return

    if _column_exists(connection, "core", "dim_shops", "created_at"):
        op.execute(
            sa.text(
                """
                UPDATE core.dim_shops
                SET created_at = now()
                WHERE created_at IS NULL
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE core.dim_shops
                ALTER COLUMN created_at SET DEFAULT now()
                """
            )
        )

    if _column_exists(connection, "core", "dim_shops", "updated_at"):
        op.execute(
            sa.text(
                """
                UPDATE core.dim_shops
                SET updated_at = now()
                WHERE updated_at IS NULL
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE core.dim_shops
                ALTER COLUMN updated_at SET DEFAULT now()
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()

    if not _table_exists(connection, "core", "dim_shops"):
        return

    if _column_exists(connection, "core", "dim_shops", "created_at"):
        op.execute(
            sa.text(
                """
                ALTER TABLE core.dim_shops
                ALTER COLUMN created_at DROP DEFAULT
                """
            )
        )

    if _column_exists(connection, "core", "dim_shops", "updated_at"):
        op.execute(
            sa.text(
                """
                ALTER TABLE core.dim_shops
                ALTER COLUMN updated_at DROP DEFAULT
                """
            )
        )
