"""Add platform identity to sales_targets_a.

Revision ID: 20260610_sales_targets_a_platform
Revises: 20260609_operating_costs_labor_cost
Create Date: 2026-06-10

Changes:
- Add platform_code to a_class.sales_targets_a.
- Move target identity from shop + month to platform + shop + month.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260610_sales_targets_a_platform"
down_revision = "20260609_operating_costs_labor_cost"
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
    if not _table_exists(connection, "a_class", "sales_targets_a"):
        return

    if not _column_exists(connection, "a_class", "sales_targets_a", "platform_code"):
        op.add_column(
            "sales_targets_a",
            sa.Column("platform_code", sa.String(length=32), nullable=False, server_default="unknown"),
            schema="a_class",
        )

    op.execute(
        sa.text(
            """
            UPDATE a_class.sales_targets_a
            SET platform_code = 'unknown'
            WHERE platform_code IS NULL OR TRIM(platform_code) = ''
            """
        )
    )

    op.execute(
        sa.text(
            """
            WITH resolved AS (
                SELECT
                    sta.ctid AS row_id,
                    MIN(LOWER(TRIM(tb.platform_code))) AS platform_code
                FROM a_class.sales_targets_a sta
                JOIN a_class.sales_targets st
                  ON DATE_TRUNC('month', st.period_start)::date = to_date(sta."年月" || '-01', 'YYYY-MM-DD')
                JOIN a_class.target_breakdown tb
                  ON tb.target_id = st.id
                 AND tb.breakdown_type = 'shop'
                 AND COALESCE(tb.shop_id, '') = COALESCE(sta."店铺ID", '')
                WHERE LOWER(TRIM(COALESCE(sta.platform_code, 'unknown'))) = 'unknown'
                  AND NULLIF(TRIM(tb.platform_code), '') IS NOT NULL
                  AND LOWER(TRIM(tb.platform_code)) NOT IN ('unknown', 'none')
                GROUP BY sta.ctid
                HAVING COUNT(DISTINCT LOWER(TRIM(tb.platform_code))) = 1
            )
            UPDATE a_class.sales_targets_a sta
            SET platform_code = resolved.platform_code
            FROM resolved
            WHERE sta.ctid = resolved.row_id
            """
        )
    )

    if _constraint_exists(connection, "a_class", "sales_targets_a", "uq_sales_targets_a_shop_month"):
        op.drop_constraint(
            "uq_sales_targets_a_shop_month",
            "sales_targets_a",
            schema="a_class",
            type_="unique",
        )

    if not _constraint_exists(connection, "a_class", "sales_targets_a", "uq_sales_targets_a_platform_shop_month"):
        op.create_unique_constraint(
            "uq_sales_targets_a_platform_shop_month",
            "sales_targets_a",
            ["platform_code", "店铺ID", "年月"],
            schema="a_class",
        )

    if not _index_exists(connection, "a_class", "ix_sales_targets_a_platform_shop"):
        op.create_index(
            "ix_sales_targets_a_platform_shop",
            "sales_targets_a",
            ["platform_code", "店铺ID"],
            unique=False,
            schema="a_class",
        )

    if not _index_exists(connection, "a_class", "ix_sales_targets_a_platform_month"):
        op.create_index(
            "ix_sales_targets_a_platform_month",
            "sales_targets_a",
            ["platform_code", "年月"],
            unique=False,
            schema="a_class",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "sales_targets_a"):
        return

    if _index_exists(connection, "a_class", "ix_sales_targets_a_platform_month"):
        op.drop_index("ix_sales_targets_a_platform_month", table_name="sales_targets_a", schema="a_class")

    if _index_exists(connection, "a_class", "ix_sales_targets_a_platform_shop"):
        op.drop_index("ix_sales_targets_a_platform_shop", table_name="sales_targets_a", schema="a_class")

    if _constraint_exists(connection, "a_class", "sales_targets_a", "uq_sales_targets_a_platform_shop_month"):
        op.drop_constraint(
            "uq_sales_targets_a_platform_shop_month",
            "sales_targets_a",
            schema="a_class",
            type_="unique",
        )

    if not _constraint_exists(connection, "a_class", "sales_targets_a", "uq_sales_targets_a_shop_month"):
        op.create_unique_constraint(
            "uq_sales_targets_a_shop_month",
            "sales_targets_a",
            ["店铺ID", "年月"],
            schema="a_class",
        )

    if _column_exists(connection, "a_class", "sales_targets_a", "platform_code"):
        op.drop_column("sales_targets_a", "platform_code", schema="a_class")
