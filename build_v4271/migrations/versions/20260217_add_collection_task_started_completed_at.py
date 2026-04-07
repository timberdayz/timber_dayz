"""add collection_tasks started_at and completed_at

add-collection-step-observability: 任务开始/结束时间供任务详情展示

Revision ID: 20260217_ctsa
Revises: 20260202_sccym
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260217_ctsa"
down_revision = "20260202_sccym"
branch_labels = None
depends_on = None


def column_exists(conn, table_name: str, column_name: str, schema: str = "public") -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :t AND column_name = :col
        )
    """), {"schema": schema, "t": table_name, "col": column_name})
    return r.scalar() or False


def upgrade() -> None:
    conn = op.get_bind()
    if column_exists(conn, "collection_tasks", "started_at", "public"):
        return  # idempotent
    op.add_column(
        "collection_tasks",
        sa.Column("started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "collection_tasks",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collection_tasks", "completed_at")
    op.drop_column("collection_tasks", "started_at")
