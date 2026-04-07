"""fix sales_targets missing columns (target_name does not exist)

Revision ID: 20260125_fix_st
Revises: v5_0_0_schema_snapshot
Create Date: 2026-01-25

当库中 sales_targets 表存在但缺少 target_name 等列时（例如由旧迁移或其它库导入），
本迁移会补齐缺失列，使与 modules/core/db/schema.py 中 SalesTarget 定义一致。
"""

from alembic import op
from sqlalchemy import text


revision = '20260125_fix_st'
down_revision = 'v5_0_0_schema_snapshot'
branch_labels = None
depends_on = None


def _current_columns(conn, schema: str, table: str):
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :t
    """), {"schema": schema, "t": table})
    return {row[0] for row in result}


def _schemas_with_table(conn, table: str):
    """返回包含该表的 schema 列表"""
    r = conn.execute(text("""
        SELECT table_schema FROM information_schema.tables
        WHERE table_name = :t
    """), {"t": table})
    return [row[0] for row in r]


def upgrade():
    conn = op.get_bind()
    schemas = _schemas_with_table(conn, "sales_targets")
    if not schemas:
        return
    for schema in schemas:
        cols = _current_columns(conn, schema, "sales_targets")
        if not cols:
            continue
        if "target_name" in cols:
            return
        # 缺少 target_name：表结构不符合当前 schema，补齐缺失列
        qual = f'"{schema}".sales_targets' if schema != "public" else "sales_targets"
        add_sql = []
        if "target_name" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN target_name VARCHAR(200) NOT NULL DEFAULT ''")
        if "target_type" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN target_type VARCHAR(32) NOT NULL DEFAULT 'shop'")
        if "period_start" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN period_start DATE NOT NULL DEFAULT '1970-01-01'")
        if "period_end" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN period_end DATE NOT NULL DEFAULT '1970-01-01'")
        if "target_amount" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN target_amount NUMERIC NOT NULL DEFAULT 0")
        if "target_quantity" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN target_quantity INTEGER NOT NULL DEFAULT 0")
        if "achieved_amount" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN achieved_amount NUMERIC NOT NULL DEFAULT 0")
        if "achieved_quantity" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN achieved_quantity INTEGER NOT NULL DEFAULT 0")
        if "achievement_rate" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN achievement_rate NUMERIC NOT NULL DEFAULT 0")
        if "status" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'")
        if "description" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN description TEXT")
        if "created_by" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN created_by VARCHAR(64)")
        if "created_at" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
        if "updated_at" not in cols:
            add_sql.append(f"ALTER TABLE {qual} ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
        for stmt in add_sql:
            op.execute(text(stmt))
        return
    # 若在 public 未找到表，尝试 a_class；若 a_class 也没有 target_name，上面会执行 add
    pass


def downgrade():
    pass
