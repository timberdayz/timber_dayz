"""align dim_shops to core canonical table

Revision ID: 20260328_dim_shops_core
Revises: 20260328_schema_cleanup_wave1
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_dim_shops_core"
down_revision = "20260328_schema_cleanup_wave1"
branch_labels = None
depends_on = None


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
    connection = op.get_bind()

    connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS core"))

    public_exists = _table_exists(connection, "public", "dim_shops")
    core_exists = _table_exists(connection, "core", "dim_shops")

    if public_exists and not core_exists:
        connection.execute(
            sa.text(
                """
                CREATE TABLE core.dim_shops
                (LIKE public.dim_shops INCLUDING ALL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO core.dim_shops
                SELECT *
                FROM public.dim_shops
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()

    public_exists = _table_exists(connection, "public", "dim_shops")
    core_exists = _table_exists(connection, "core", "dim_shops")

    if core_exists and not public_exists:
        connection.execute(
            sa.text(
                """
                CREATE TABLE public.dim_shops
                (LIKE core.dim_shops INCLUDING ALL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO public.dim_shops
                SELECT *
                FROM core.dim_shops
                """
            )
        )
