"""add_shop_commission_config

add-employee-shop-assignment-page Phase 2: 店铺可分配利润率配置表

Revision ID: 20260202_scc
Revises: 20260201_max_score
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260202_scc"
down_revision = "20260201_max_score"
branch_labels = None
depends_on = None


def table_exists(conn, table_name: str, schema: str = "public") -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :t
        )
    """), {"schema": schema, "t": table_name})
    return r.scalar() or False


def upgrade() -> None:
    conn = op.get_bind()
    if table_exists(conn, "shop_commission_config", "a_class"):
        return  # 幂等：表已存在则跳过

    op.create_table(
        "shop_commission_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=256), nullable=False),
        sa.Column("allocatable_profit_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_code", "shop_id", name="uq_shop_commission_config_a"),
        sa.ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_shop_commission_config_shop_a",
            ondelete="RESTRICT",
        ),
        schema="a_class",
    )
    op.create_index(
        "ix_shop_commission_config_a_shop",
        "shop_commission_config",
        ["platform_code", "shop_id"],
        schema="a_class",
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "shop_commission_config", "a_class"):
        return  # 幂等：表不存在则跳过
    op.drop_index(
        "ix_shop_commission_config_a_shop",
        table_name="shop_commission_config",
        schema="a_class",
    )
    op.drop_table("shop_commission_config", schema="a_class")
