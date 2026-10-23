"""把最低售价变更通知的基线从 ``core.dim_erp_sku`` 搬到 ``ops.price_adjust_baselines``。

为什么必须搬（这是本次改动的**唯一**目的）：

商品中心的 SKU 主数据有一条「采集机 → 云端」的同步链路，
它对 ``core.dim_erp_sku`` 做的是 **TRUNCATE + 全量重灌**（保证两边完全一致）。
基线若住在那张表里，每次同步都会被抹成"从未处理过"：

- 系统重新建基线（不发通知）
- **同步窗口内真实发生的底线变化会被静默吞掉** —— 与"一个都不能漏"直接冲突

所以基线搬到 ``ops`` 域的独立表：它与 ``feishu_projection_tasks``（通知 outbox）同域，
语义一致（都是"通知进度状态"，不是"商品主数据"），且**不参与商品中心同步**。

顺带把 ``core.dim_erp_sku`` 上那两列删掉——留着空列是隐患：
以后有人看到"这里有基线字段"会以为它是生效的。

迁移是幂等的：建表、搬数据、删列都带存在性检查。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "current_schema_20261024_price_adjust_baseline_table"
down_revision = "current_schema_20261023_price_adjust_notification"
branch_labels = None
depends_on = None


JSON_COMPAT = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

BASELINE_TABLE = "price_adjust_baselines"
LEGACY_SKU_COLUMNS = ("last_notified_context", "last_notified_min_price")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def upgrade() -> None:
    # ---------- 1. 建基线表 ----------
    if not _has_table(BASELINE_TABLE, "ops"):
        op.create_table(
            BASELINE_TABLE,
            sa.Column("sku_id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("last_notified_min_price", sa.Numeric(18, 2), nullable=True),
            sa.Column("last_notified_context", JSON_COMPAT, nullable=True),
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
            sa.PrimaryKeyConstraint("sku_id", name="pk_price_adjust_baselines"),
            sa.Index(
                "ix_price_adjust_baselines_updated",
                "updated_at",
            ),
            schema="ops",
        )

    # ---------- 2. 搬迁旧基线数据（若存在） ----------
    if _has_table("dim_erp_sku", "core") and all(
        _has_column("dim_erp_sku", "core", name) for name in LEGACY_SKU_COLUMNS
    ):
        op.execute(
            sa.text(
                "INSERT INTO ops.price_adjust_baselines "
                "(sku_id, last_notified_min_price, last_notified_context, "
                " created_at, updated_at) "
                "SELECT sku_id, last_notified_min_price, last_notified_context, "
                "       now(), now() "
                "FROM core.dim_erp_sku "
                "WHERE last_notified_context IS NOT NULL "
                "ON CONFLICT (sku_id) DO UPDATE SET "
                "  last_notified_min_price = EXCLUDED.last_notified_min_price, "
                "  last_notified_context = EXCLUDED.last_notified_context, "
                "  updated_at = now()"
            )
        )

        # ---------- 3. 删掉 SKU 表上的旧列 ----------
        for name in LEGACY_SKU_COLUMNS:
            if _has_column("dim_erp_sku", "core", name):
                op.drop_column("dim_erp_sku", name, schema="core")


def downgrade() -> None:
    if _has_table("dim_erp_sku", "core"):
        for name in LEGACY_SKU_COLUMNS:
            if not _has_column("dim_erp_sku", "core", name):
                op.add_column(
                    "dim_erp_sku",
                    sa.Column(
                        name,
                        JSON_COMPAT if name.endswith("context") else sa.Numeric(18, 2),
                        nullable=True,
                    ),
                    schema="core",
                )
        if _has_table(BASELINE_TABLE, "ops"):
            op.execute(
                sa.text(
                    "UPDATE core.dim_erp_sku AS s "
                    "SET last_notified_min_price = b.last_notified_min_price, "
                    "    last_notified_context = b.last_notified_context "
                    "FROM ops.price_adjust_baselines AS b "
                    "WHERE s.sku_id = b.sku_id"
                )
            )

    if _has_table(BASELINE_TABLE, "ops"):
        op.drop_index("ix_price_adjust_baselines_updated", table_name=BASELINE_TABLE, schema="ops")
        op.drop_table(BASELINE_TABLE, schema="ops")
