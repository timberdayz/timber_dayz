"""Move the pricing floor down to SKU × platform (Stage 2.1).

Two DDL changes:

1. **New table ``finance.sku_platform_pricing``** — the home of the per-platform
   manual minimum-selling-price override plus a derivation snapshot.
   The floor itself is still derived at query time (a stored copy would drift
   away from the live rates and end up blocking the wrong SKUs).

2. **``ops.price_adjust_baselines`` primary key becomes ``(sku_id, platform_code)``** —
   the baseline answers "did *this SKU on *this platform* get more expensive?",
   so one row per SKU is no longer enough.  A floor that moves on Shopee must
   not be reported as a change on TikTok.

The migration is idempotent: every object is guarded by an existence check.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "current_schema_20261115_add_sku_platform_pricing"
down_revision = "current_schema_20261114_add_sku_roi_columns"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def _has_index(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        index["name"] == name
        for index in _inspector().get_indexes(table, schema=schema)
    )


def _has_unique_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        constraint.get("name") == name
        for constraint in _inspector().get_unique_constraints(table, schema=schema)
    )


def _primary_key_columns(table: str, schema: str) -> list[str]:
    return list(
        _inspector().get_pk_constraint(table, schema=schema)["constrained_columns"]
    )


def _primary_key_name(table: str, schema: str) -> str | None:
    return _inspector().get_pk_constraint(table, schema=schema).get("name")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) finance.sku_platform_pricing
    # ------------------------------------------------------------------
    if not _has_table("sku_platform_pricing", "finance"):
        op.create_table(
            "sku_platform_pricing",
            sa.Column("pricing_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sku_id", sa.Integer(), nullable=False),
            sa.Column("platform_code", sa.String(32), nullable=False),
            sa.Column("min_selling_price_override", sa.Numeric(18, 2), nullable=True),
            sa.Column("min_selling_price_source", sa.String(32), nullable=True),
            sa.Column("pricing_tier_label", sa.String(32), nullable=True),
            sa.Column("pricing_days_since_restock", sa.Integer(), nullable=True),
            sa.Column("pricing_tier_source", sa.String(32), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
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
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["sku_id"], ["core.dim_erp_sku.sku_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["platform_code"],
                ["core.dim_platforms.platform_code"],
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "sku_id", "platform_code", name="uq_sku_platform_pricing_sku_platform"
            ),
            schema="finance",
        )
    if _has_table("sku_platform_pricing", "finance") and not _has_index(
        "sku_platform_pricing", "finance", "ix_sku_platform_pricing_platform"
    ):
        op.create_index(
            "ix_sku_platform_pricing_platform",
            "sku_platform_pricing",
            ["platform_code"],
            schema="finance",
        )
    # 表已存在但缺唯一约束（老版本建过表）时补上——
    # 没有这个约束，同一个 SKU × 平台可以插出多行人工覆盖，
    # 读路径 ``load_platform_pricing_overrides`` 用 dict 归位就会**静默丢一行**。
    if _has_table("sku_platform_pricing", "finance") and not _has_unique_constraint(
        "sku_platform_pricing", "finance", "uq_sku_platform_pricing_sku_platform"
    ):
        op.create_unique_constraint(
            "uq_sku_platform_pricing_sku_platform",
            "sku_platform_pricing",
            ["sku_id", "platform_code"],
            schema="finance",
        )

    # ------------------------------------------------------------------
    # 2) ops.price_adjust_baselines -> 复合主键 (sku_id, platform_code)
    # ------------------------------------------------------------------
    if not _has_table("price_adjust_baselines", "ops"):
        return

    if not _has_column("price_adjust_baselines", "ops", "platform_code"):
        op.add_column(
            "price_adjust_baselines",
            sa.Column("platform_code", sa.String(32), nullable=True),
            schema="ops",
        )
        # 回填：老行按该 SKU 的经营档案平台回填；没有经营档案的 SKU 落规则表 basis 平台。
        # ⚠️ 回填必须**先于**加 NOT NULL 与复合主键。
        op.execute(
            sa.text(
                "UPDATE ops.price_adjust_baselines b SET platform_code = COALESCE("
                "  (SELECT p.platform_code FROM finance.sku_operating_profiles p "
                "   WHERE p.sku_id = b.sku_id AND p.status = 'active' AND p.effective_to IS NULL "
                "   ORDER BY p.profile_id LIMIT 1),"
                "  (SELECT pol.platform_basis FROM finance.sku_pricing_policies pol "
                "   WHERE pol.status = 'active' AND pol.effective_to IS NULL "
                "   ORDER BY pol.min_restock_days LIMIT 1),"
                "  'tiktok'"
                ") WHERE b.platform_code IS NULL"
            )
        )
        # 兜底：连 basis 平台都取不到的（规则表空库）落 tiktok
        op.execute(
            sa.text(
                "UPDATE ops.price_adjust_baselines SET platform_code = 'tiktok' "
                "WHERE platform_code IS NULL"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE ops.price_adjust_baselines "
                "ALTER COLUMN platform_code SET NOT NULL"
            )
        )

    pk_columns = _primary_key_columns("price_adjust_baselines", "ops")
    if pk_columns == ["sku_id"]:
        op.drop_constraint(
            _primary_key_name("price_adjust_baselines", "ops")
            or "price_adjust_baselines_pkey",
            "price_adjust_baselines",
            schema="ops",
            type_="primary",
        )
        op.create_primary_key(
            "price_adjust_baselines_pkey",
            "price_adjust_baselines",
            ["sku_id", "platform_code"],
            schema="ops",
        )


def downgrade() -> None:
    if _has_table("price_adjust_baselines", "ops"):
        pk_columns = _primary_key_columns("price_adjust_baselines", "ops")
        if pk_columns == ["sku_id", "platform_code"]:
            # 复合主键 → 单列主键：同一个 SKU 的多个平台行只保留**平台字典序最小**的那条，
            # 否则建主键会撞重复行。
            op.execute(
                sa.text(
                    "DELETE FROM ops.price_adjust_baselines a USING ops.price_adjust_baselines b "
                    "WHERE a.sku_id = b.sku_id AND a.platform_code > b.platform_code"
                )
            )
            op.drop_constraint(
                _primary_key_name("price_adjust_baselines", "ops")
                or "price_adjust_baselines_pkey",
                "price_adjust_baselines",
                schema="ops",
                type_="primary",
            )
            op.create_primary_key(
                "price_adjust_baselines_pkey",
                "price_adjust_baselines",
                ["sku_id"],
                schema="ops",
            )
        if _has_column("price_adjust_baselines", "ops", "platform_code"):
            op.drop_column("price_adjust_baselines", "platform_code", schema="ops")

    if _has_table("sku_platform_pricing", "finance"):
        op.drop_table("sku_platform_pricing", schema="finance")
