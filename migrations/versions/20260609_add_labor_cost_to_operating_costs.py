"""Add labor cost to operating_costs.

Revision ID: 20260609_operating_costs_labor_cost
Revises: 20260608_cloud_sync_run_metadata
Create Date: 2026-06-09

Changes:
- Add "人力费用" as a manual store-level operating cost column.
- Backfill "成本合计" from the six operating-cost columns.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_operating_costs_labor_cost"
down_revision = "20260608_cloud_sync_run_metadata"
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


def _backfill_total_cost(include_labor_cost: bool) -> None:
    labor_cost_expr = '+ COALESCE("人力费用", 0)' if include_labor_cost else ""
    op.execute(
        sa.text(
            f"""
            UPDATE a_class.operating_costs
            SET "成本合计" =
                COALESCE("租金", 0)
              + COALESCE("营销费用", 0)
              + COALESCE("水电费", 0)
              + COALESCE("AI Token费用", 0)
              {labor_cost_expr}
              + COALESCE("其他成本", 0)
            """
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    if not _column_exists(connection, "a_class", "operating_costs", "人力费用"):
        op.add_column(
            "operating_costs",
            sa.Column("人力费用", sa.Numeric(15, 2), nullable=False, server_default="0"),
            schema="a_class",
        )

    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN a_class.operating_costs."人力费用"
            IS '人力费用（CNY），店铺经营成本手工分摊，不作为HR工资单入口'
            """
        )
    )

    if _column_exists(connection, "a_class", "operating_costs", "成本合计"):
        _backfill_total_cost(include_labor_cost=True)


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    if _column_exists(connection, "a_class", "operating_costs", "成本合计"):
        _backfill_total_cost(include_labor_cost=False)

    if _column_exists(connection, "a_class", "operating_costs", "人力费用"):
        op.drop_column("operating_costs", "人力费用", schema="a_class")
