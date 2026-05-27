"""Add platform_code to operating_costs and backfill existing rows.

Revision ID: 20260526_add_platform_code_to_operating_costs
Revises: 20260525_add_header_bindings_to_templates
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_add_platform_code_to_operating_costs"
down_revision = "20260525_header_bindings"
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
        {"schema_name": schema_name, "table_name": table_name, "column_name": column_name},
    )
    return result.scalar() is not None


def _constraint_exists(connection, schema_name: str, table_name: str, constraint_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND constraint_name = :constraint_name
            LIMIT 1
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "constraint_name": constraint_name,
        },
    )
    return result.scalar() is not None


def _index_exists(connection, schema_name: str, index_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = :schema_name
              AND indexname = :index_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "index_name": index_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    if not _column_exists(connection, "a_class", "operating_costs", "platform_code"):
        op.add_column(
            "operating_costs",
            sa.Column("platform_code", sa.String(length=32), nullable=True),
            schema="a_class",
        )

    # Backfill with the best available shop account match.
    op.execute(
        sa.text(
            """
            WITH resolved AS (
                SELECT
                    oc.ctid AS row_id,
                    LOWER(TRIM(sa.platform)) AS platform_code
                FROM a_class.operating_costs oc
                JOIN core.shop_accounts sa
                  ON sa.enabled = true
                 AND (
                      COALESCE(sa.platform_shop_id, '') = COALESCE(oc."店铺ID", '')
                   OR COALESCE(sa.shop_account_id, '') = COALESCE(oc."店铺ID", '')
                 )
                WHERE oc.platform_code IS NULL
            )
            UPDATE a_class.operating_costs oc
            SET platform_code = resolved.platform_code
            FROM resolved
            WHERE oc.ctid = resolved.row_id
            """
        )
    )

    if _constraint_exists(connection, "a_class", "operating_costs", "uq_operating_costs_a_shop_month"):
        op.drop_constraint(
            "uq_operating_costs_a_shop_month",
            "operating_costs",
            schema="a_class",
            type_="unique",
        )

    if not _constraint_exists(connection, "a_class", "operating_costs", "uq_operating_costs_a_platform_shop_month"):
        op.create_unique_constraint(
            "uq_operating_costs_a_platform_shop_month",
            "operating_costs",
            ["platform_code", "店铺ID", "年月"],
            schema="a_class",
        )

    if not _index_exists(connection, "a_class", "ix_operating_costs_a_platform_shop"):
        op.create_index(
            "ix_operating_costs_a_platform_shop",
            "operating_costs",
            ["platform_code", "店铺ID"],
            unique=False,
            schema="a_class",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    if _index_exists(connection, "a_class", "ix_operating_costs_a_platform_shop"):
        op.drop_index("ix_operating_costs_a_platform_shop", table_name="operating_costs", schema="a_class")

    if _constraint_exists(connection, "a_class", "operating_costs", "uq_operating_costs_a_platform_shop_month"):
        op.drop_constraint(
            "uq_operating_costs_a_platform_shop_month",
            "operating_costs",
            schema="a_class",
            type_="unique",
        )

    if not _constraint_exists(connection, "a_class", "operating_costs", "uq_operating_costs_a_shop_month"):
        op.create_unique_constraint(
            "uq_operating_costs_a_shop_month",
            "operating_costs",
            ["店铺ID", "年月"],
            schema="a_class",
        )

    if _column_exists(connection, "a_class", "operating_costs", "platform_code"):
        op.drop_column("operating_costs", "platform_code", schema="a_class")
