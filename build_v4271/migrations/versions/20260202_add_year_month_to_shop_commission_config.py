"""add_year_month_to_shop_commission_config

add-employee-shop-assignment-page 方案B: 店铺可分配利润率按月度存储

Revision ID: 20260202_sccym
Revises: 20260202_scc
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260202_sccym"
down_revision = "20260202_scc"
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


def column_exists(conn, table_name: str, column_name: str, schema: str = "a_class") -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :t AND column_name = :col
        )
    """), {"schema": schema, "t": table_name, "col": column_name})
    return r.scalar() or False


def upgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "shop_commission_config", "a_class"):
        return
    if column_exists(conn, "shop_commission_config", "year_month", "a_class"):
        return  # 幂等：已添加则跳过

    # 1. 添加 year_month 列（先可空）
    op.add_column(
        "shop_commission_config",
        sa.Column("year_month", sa.String(7), nullable=True),
        schema="a_class",
    )

    # 2. 回填现有数据：使用 created_at 的年月，无则用 2026-02
    conn.execute(text("""
        UPDATE a_class.shop_commission_config
        SET year_month = COALESCE(
            TO_CHAR(created_at, 'YYYY-MM'),
            '2026-02'
        )
        WHERE year_month IS NULL
    """))

    # 3. 设为 NOT NULL
    op.alter_column(
        "shop_commission_config",
        "year_month",
        existing_type=sa.String(7),
        nullable=False,
        schema="a_class",
    )

    # 4. 删除旧唯一约束和索引
    op.drop_constraint(
        "uq_shop_commission_config_a",
        "shop_commission_config",
        schema="a_class",
        type_="unique",
    )
    op.drop_index(
        "ix_shop_commission_config_a_shop",
        table_name="shop_commission_config",
        schema="a_class",
    )

    # 5. 添加新唯一约束和索引
    op.create_unique_constraint(
        "uq_shop_commission_config_a",
        "shop_commission_config",
        ["year_month", "platform_code", "shop_id"],
        schema="a_class",
    )
    op.create_index(
        "ix_shop_commission_config_a_shop_month",
        "shop_commission_config",
        ["year_month", "platform_code", "shop_id"],
        schema="a_class",
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "shop_commission_config", "a_class"):
        return
    if not column_exists(conn, "shop_commission_config", "year_month", "a_class"):
        return

    # 若有同店铺多月份数据，downgrade 会丢失；仅保留每个店铺一条（取最新月份）
    op.drop_constraint(
        "uq_shop_commission_config_a",
        "shop_commission_config",
        schema="a_class",
        type_="unique",
    )
    op.drop_index(
        "ix_shop_commission_config_a_shop_month",
        table_name="shop_commission_config",
        schema="a_class",
    )

    # 删除重复：每个 (platform_code, shop_id) 只保留 id 最大的一条
    conn.execute(text("""
        DELETE FROM a_class.shop_commission_config c1
        WHERE EXISTS (
            SELECT 1 FROM a_class.shop_commission_config c2
            WHERE c1.platform_code = c2.platform_code AND c1.shop_id = c2.shop_id AND c1.id < c2.id
        )
    """))

    op.drop_column("shop_commission_config", "year_month", schema="a_class")

    op.create_unique_constraint(
        "uq_shop_commission_config_a",
        "shop_commission_config",
        ["platform_code", "shop_id"],
        schema="a_class",
    )
    op.create_index(
        "ix_shop_commission_config_a_shop",
        "shop_commission_config",
        ["platform_code", "shop_id"],
        schema="a_class",
    )
