"""Extend operating_costs for expense management.

Revision ID: 20260521_operating_costs_cost_fields
Revises: 20260416_field_parse_rules
Create Date: 2026-05-21

Changes (a_class.operating_costs):
- Rename legacy "工资" -> "营销费用" when needed
- Add "AI Token费用", "成本合计", "备注", "附件", "是否锁定"
- Backfill "成本合计" from component columns
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260521_operating_costs_cost_fields"
down_revision = "20260416_field_parse_rules"
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


def _rename_column_if_needed(connection, old_name: str, new_name: str) -> None:
    if _column_exists(connection, "a_class", "operating_costs", old_name) and not _column_exists(
        connection, "a_class", "operating_costs", new_name
    ):
        op.execute(sa.text(f'ALTER TABLE a_class.operating_costs RENAME COLUMN "{old_name}" TO "{new_name}"'))


def _add_numeric_column_if_missing(connection, column_name: str) -> None:
    if not _column_exists(connection, "a_class", "operating_costs", column_name):
        op.add_column(
            "operating_costs",
            sa.Column(column_name, sa.Numeric(15, 2), nullable=False, server_default="0"),
            schema="a_class",
        )


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    # 1) Normalize the v5 snapshot English columns to the current Chinese-column contract.
    _rename_column_if_needed(connection, "shop_id", "店铺ID")
    _rename_column_if_needed(connection, "year_month", "年月")
    _rename_column_if_needed(connection, "rent", "租金")
    _rename_column_if_needed(connection, "salary", "工资")
    _rename_column_if_needed(connection, "utilities", "水电费")
    _rename_column_if_needed(connection, "other_costs", "其他成本")
    _rename_column_if_needed(connection, "created_at", "创建时间")
    _rename_column_if_needed(connection, "updated_at", "更新时间")
    _rename_column_if_needed(connection, "工资", "营销费用")

    _add_numeric_column_if_missing(connection, "租金")
    _add_numeric_column_if_missing(connection, "营销费用")
    _add_numeric_column_if_missing(connection, "水电费")
    _add_numeric_column_if_missing(connection, "其他成本")

    # 2) Add new columns (idempotent).
    _add_numeric_column_if_missing(connection, "AI Token费用")
    _add_numeric_column_if_missing(connection, "成本合计")

    if not _column_exists(connection, "a_class", "operating_costs", "备注"):
        op.add_column(
            "operating_costs",
            sa.Column("备注", sa.Text(), nullable=True),
            schema="a_class",
        )

    if not _column_exists(connection, "a_class", "operating_costs", "附件"):
        op.add_column(
            "operating_costs",
            sa.Column("附件", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            schema="a_class",
        )

    if not _column_exists(connection, "a_class", "operating_costs", "是否锁定"):
        op.add_column(
            "operating_costs",
            sa.Column("是否锁定", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            schema="a_class",
        )
        op.create_index(
            "ix_operating_costs_locked",
            "operating_costs",
            ["是否锁定"],
            unique=False,
            schema="a_class",
        )

    # 3) Backfill total cost.
    # Use COALESCE to be resilient to older rows / nullable columns.
    # Prefer "营销费用"; after rename it should exist.
    op.execute(
        sa.text(
            """
            UPDATE a_class.operating_costs
            SET "成本合计" =
                COALESCE("租金", 0)
              + COALESCE("营销费用", 0)
              + COALESCE("水电费", 0)
              + COALESCE("其他成本", 0)
              + COALESCE("AI Token费用", 0)
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection, "a_class", "operating_costs"):
        return

    if _column_exists(connection, "a_class", "operating_costs", "是否锁定"):
        try:
            op.drop_index("ix_operating_costs_locked", table_name="operating_costs", schema="a_class")
        except Exception:
            pass
        op.drop_column("operating_costs", "是否锁定", schema="a_class")

    if _column_exists(connection, "a_class", "operating_costs", "附件"):
        op.drop_column("operating_costs", "附件", schema="a_class")

    if _column_exists(connection, "a_class", "operating_costs", "备注"):
        op.drop_column("operating_costs", "备注", schema="a_class")

    if _column_exists(connection, "a_class", "operating_costs", "成本合计"):
        op.drop_column("operating_costs", "成本合计", schema="a_class")

    if _column_exists(connection, "a_class", "operating_costs", "AI Token费用"):
        op.drop_column("operating_costs", "AI Token费用", schema="a_class")

    # Rename back only if needed.
    has_salary = _column_exists(connection, "a_class", "operating_costs", "工资")
    has_marketing = _column_exists(connection, "a_class", "operating_costs", "营销费用")
    if (not has_salary) and has_marketing:
        op.execute(sa.text('ALTER TABLE a_class.operating_costs RENAME COLUMN "营销费用" TO "工资"'))
