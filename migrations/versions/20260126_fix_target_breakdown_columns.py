"""fix target_breakdown missing columns to match schema.py

Revision ID: 20260126_tb_cols
Revises: 20260125_fix_st
Create Date: 2026-01-26

当库中 target_breakdown 表存在但缺少 breakdown_type、period_label 等列时，
本迁移会补齐缺失列，使与 modules/core/db/schema.py 中 TargetBreakdown 定义一致。
下次部署时执行 alembic upgrade head 即可生效。
"""

from alembic import op
from sqlalchemy import text


revision = "20260126_tb_cols"
down_revision = "20260125_fix_st"
branch_labels = None
depends_on = None


def _current_columns(conn, schema: str, table: str):
    result = conn.execute(
        text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :t
    """),
        {"schema": schema, "t": table},
    )
    return {row[0] for row in result}


def _schemas_with_table(conn, table: str):
    r = conn.execute(
        text("""
        SELECT table_schema FROM information_schema.tables
        WHERE table_name = :t
    """),
        {"t": table},
    )
    return [row[0] for row in r]


def upgrade():
    conn = op.get_bind()
    for schema in _schemas_with_table(conn, "target_breakdown"):
        cols = _current_columns(conn, schema, "target_breakdown")
        if not cols:
            continue
        qual = f'"{schema}".target_breakdown' if schema != "public" else "target_breakdown"
        add_sql = []
        if "target_id" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN target_id INTEGER NOT NULL DEFAULT 0")
        if "breakdown_type" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN breakdown_type VARCHAR(32) NOT NULL DEFAULT 'shop'"
            )
        if "platform_code" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN platform_code VARCHAR(32)")
        if "shop_id" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN shop_id VARCHAR(64)")
        if "period_start" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN period_start DATE")
        if "period_end" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN period_end DATE")
        if "period_label" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN period_label VARCHAR(64)")
        if "target_amount" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN target_amount NUMERIC NOT NULL DEFAULT 0"
            )
        if "target_quantity" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN target_quantity INTEGER NOT NULL DEFAULT 0"
            )
        if "achieved_amount" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN achieved_amount NUMERIC NOT NULL DEFAULT 0"
            )
        if "achieved_quantity" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN achieved_quantity INTEGER NOT NULL DEFAULT 0"
            )
        if "achievement_rate" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN achievement_rate NUMERIC NOT NULL DEFAULT 0"
            )
        if "created_at" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in cols:
            add_sql.append(
                f"ALTER TABLE {qual} ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        for stmt in add_sql:
            op.execute(text(stmt))


def downgrade():
    pass
