"""尾程配送费费率表（平台 × 仓 × 重量段）。

背景
----
尾程 = 仓 → 买家那段快递费，**每卖一件必付**（头程是已付库存成本，一次）。
没有费率表就等于默认「尾程不要钱」⇒ 利润虚高、最低售价底线偏低。

表结构要点
----------
- 当期唯一：``(platform_code, warehouse_code, min_weight_kg)``（active 且未闭区间）。
- **刻意不建外键**到 ``core.dim_platforms`` / ``core.dim_warehouses``：
  这两张表会被「采集机 → 云端」同步 ``TRUNCATE ... CASCADE``，建了外键会让
  **尾程费率规则被连带删掉**（静默失效：底线突然算不出来）。
- 重量段：``[min_weight_kg, max_weight_kg]``；``max_weight_kg IS NULL`` = 往上不封顶。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261233_delivery_rate_rules"
down_revision = "current_schema_20261232_inventory_contract_consumers"
branch_labels = None
depends_on = None


TABLE = "delivery_rate_rules"
SCHEMA = "finance"


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE, schema=SCHEMA)


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("rule_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=False),
        sa.Column("warehouse_code", sa.String(length=128), nullable=False),
        sa.Column("min_weight_kg", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("max_weight_kg", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "currency", sa.String(length=8), nullable=False, server_default="CNY"
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "min_weight_kg >= 0", name="ck_delivery_rate_rules_min_weight"
        ),
        sa.CheckConstraint(
            "max_weight_kg IS NULL OR max_weight_kg > min_weight_kg",
            name="ck_delivery_rate_rules_weight_window",
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_delivery_rate_rules_price"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_delivery_rate_rules_window",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_delivery_rate_rules_status"
        ),
        sa.PrimaryKeyConstraint("rule_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_delivery_rate_rules_current",
        TABLE,
        ["platform_code", "warehouse_code", "min_weight_kg"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_delivery_rate_rules_lookup",
        TABLE,
        ["platform_code", "warehouse_code", "effective_from"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    if not _has_table():
        return
    op.drop_index("ix_delivery_rate_rules_lookup", table_name=TABLE, schema=SCHEMA)
    op.drop_index("uq_delivery_rate_rules_current", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
