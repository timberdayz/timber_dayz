"""Add SKU pricing guardrails: age-tier policy table, platform cost rates, SKU overrides.

Adds the company-level library-age pricing policy table, the platform cost-rate
columns used to derive a cost floor, and the two SKU-level writable columns
(creator commission rate and a manual minimum-selling-price override).

The migration is idempotent: every object is guarded by an existence check, and
the policy seed is keyed on the tier's *current* row rather than on today's date,
so re-running it on a later day does not attempt a duplicate insert.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "current_schema_20261020_sku_pricing_guardrails"
down_revision = "current_schema_20260921_warehouse_storage_label_fee"
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


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        constraint.get("name") == name
        for constraint in _inspector().get_check_constraints(table, schema=schema)
    )


def _has_index(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        index["name"] == name for index in _inspector().get_indexes(table, schema=schema)
    )


POLICY_ROWS = [
    # min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis
    (0, "日常", 0.10, 0.25, "tiktok"),
    (60, "滞销30天", 0.15, 0.22, "tiktok"),
    (90, "滞销60天", 0.20, 0.18, "tiktok"),
    (120, "滞销60天以上", 0.30, 0.10, "tiktok"),
]

PLATFORM_COST_RATES = {
    "tiktok": {
        "default_fee_rate": 0.0737,
        "default_creator_commission_rate": 0.0606,
        "other_cost_rate": 0.2727,
    },
    "shopee": {
        "default_fee_rate": 0.1487,
        "default_creator_commission_rate": 0.0111,
        "other_cost_rate": 0.4165,
    },
}

PLATFORM_FEE_RATE_SOURCE = "b_class_measured_2026_01_07"
PLATFORM_FEE_RATE_VERSION = "v2"
POLICY_SOURCE = "industry_benchmark_2026"
POLICY_VERSION = "v1"


def upgrade() -> None:
    if not _has_table("sku_pricing_policies", "finance"):
        op.create_table(
            "sku_pricing_policies",
            sa.Column("policy_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("min_age_days", sa.Integer(), nullable=False),
            sa.Column("tier_label", sa.String(32), nullable=False),
            sa.Column("discount_rate", sa.Numeric(12, 8), nullable=False),
            sa.Column("target_margin_rate", sa.Numeric(12, 8), nullable=False),
            sa.Column("platform_basis", sa.String(32), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("source", sa.String(128), nullable=True),
            sa.Column("version", sa.String(64), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("min_age_days", "effective_from", name="uq_sku_pricing_policy_tier_start"),
            sa.CheckConstraint("min_age_days >= 0", name="ck_sku_pricing_policy_age_start"),
            sa.CheckConstraint("discount_rate >= 0 AND discount_rate <= 1", name="ck_sku_pricing_policy_discount_rate"),
            sa.CheckConstraint("target_margin_rate >= 0 AND target_margin_rate < 1", name="ck_sku_pricing_policy_target_margin"),
            sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_sku_pricing_policy_window"),
            sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_sku_pricing_policy_status"),
            schema="finance",
        )
    if not _has_index("sku_pricing_policies", "finance", "uq_sku_pricing_policies_current"):
        op.create_index(
            "uq_sku_pricing_policies_current",
            "sku_pricing_policies",
            ["min_age_days"],
            unique=True,
            postgresql_where=text("status = 'active' AND effective_to IS NULL"),
            schema="finance",
        )
    if not _has_index("sku_pricing_policies", "finance", "ix_sku_pricing_policy_scope"):
        op.create_index(
            "ix_sku_pricing_policy_scope",
            "sku_pricing_policies",
            ["min_age_days", "effective_from"],
            schema="finance",
        )

    if _has_table("dim_platforms", "core") and not _has_column("dim_platforms", "core", "default_creator_commission_rate"):
        op.add_column("dim_platforms", sa.Column("default_creator_commission_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    if _has_table("dim_platforms", "core") and not _has_column("dim_platforms", "core", "other_cost_rate"):
        op.add_column("dim_platforms", sa.Column("other_cost_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    for name, expr in (
        ("ck_dim_platforms_fee_rate_range", "default_fee_rate IS NULL OR (default_fee_rate >= 0 AND default_fee_rate <= 1)"),
        ("ck_dim_platforms_creator_commission_rate_range", "default_creator_commission_rate IS NULL OR (default_creator_commission_rate >= 0 AND default_creator_commission_rate <= 1)"),
        ("ck_dim_platforms_other_cost_rate_range", "other_cost_rate IS NULL OR (other_cost_rate >= 0 AND other_cost_rate < 1)"),
    ):
        if _has_table("dim_platforms", "core") and not _has_constraint("dim_platforms", "core", name):
            op.create_check_constraint(name, "dim_platforms", expr, schema="core")

    if _has_table("dim_erp_sku", "core") and not _has_column("dim_erp_sku", "core", "creator_commission_rate"):
        op.add_column("dim_erp_sku", sa.Column("creator_commission_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    if _has_table("dim_erp_sku", "core") and not _has_column("dim_erp_sku", "core", "min_selling_price_override"):
        op.add_column("dim_erp_sku", sa.Column("min_selling_price_override", sa.Numeric(18, 2), nullable=True), schema="core")
    for name, expr in (
        ("ck_dim_erp_sku_creator_commission_rate", "creator_commission_rate IS NULL OR (creator_commission_rate >= 0 AND creator_commission_rate <= 1)"),
        ("ck_dim_erp_sku_min_selling_price_override", "min_selling_price_override IS NULL OR min_selling_price_override > 0"),
    ):
        if _has_table("dim_erp_sku", "core") and not _has_constraint("dim_erp_sku", "core", name):
            op.create_check_constraint(name, "dim_erp_sku", expr, schema="core")

    bind = op.get_bind()
    for min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis in POLICY_ROWS:
        # 幂等守卫必须按「该档位是否已有当前生效行」判断，
        # **不能**按「effective_from = CURRENT_DATE」判断——
        # 后者在「昨天跑过 upgrade、今天再跑一次」时会判定为不存在，
        # 于是插入一行 effective_from=今天 的重复档位，
        # 直接撞 uq_sku_pricing_policies_current 部分唯一索引。
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM finance.sku_pricing_policies "
                "WHERE min_age_days = :m AND status = 'active' AND effective_to IS NULL LIMIT 1"
            ),
            {"m": min_age_days},
        ).scalar()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO finance.sku_pricing_policies "
                    "(min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis, "
                    " effective_from, status, source, version) "
                    "VALUES (:m, :l, :d, :t, :b, CURRENT_DATE, 'active', :s, :v)"
                ),
                {
                    "m": min_age_days,
                    "l": tier_label,
                    "d": discount_rate,
                    "t": target_margin_rate,
                    "b": platform_basis,
                    "s": POLICY_SOURCE,
                    "v": POLICY_VERSION,
                },
            )

    for platform_code, values in PLATFORM_COST_RATES.items():
        bind.execute(
            sa.text(
                "UPDATE core.dim_platforms SET default_fee_rate = :fee, "
                "default_creator_commission_rate = :crea, other_cost_rate = :other, "
                "fee_rate_source = :src, fee_rate_version = :ver "
                "WHERE platform_code = :code AND platform_role = 'sales'"
            ),
            {
                "code": platform_code,
                "fee": values["default_fee_rate"],
                "crea": values["default_creator_commission_rate"],
                "other": values["other_cost_rate"],
                "src": PLATFORM_FEE_RATE_SOURCE,
                "ver": PLATFORM_FEE_RATE_VERSION,
            },
        )


def downgrade() -> None:
    # 平台费率是**数据**校准（不是 schema 变更），必须一并还原，
    # 否则 downgrade 之后平台佣金率还停在 7.37%/14.87%，与列被删掉的现实脱节。
    # 只还原**仍带本次迁移标记**的行，避免覆盖掉后来的人工调整。
    op.execute(sa.text(
        "UPDATE core.dim_platforms SET default_fee_rate = 0.02, "
        "fee_rate_source = 'manual', fee_rate_version = 'v1' "
        "WHERE platform_code IN ('tiktok', 'shopee') "
        "AND fee_rate_source = 'b_class_measured_2026_01_07' AND fee_rate_version = 'v2'"
    ))
    op.execute(sa.text("DELETE FROM finance.sku_pricing_policies WHERE source = 'industry_benchmark_2026'"))
    if _has_table("sku_pricing_policies", "finance"):
        op.drop_table("sku_pricing_policies", schema="finance")
    for name in ("ck_dim_erp_sku_min_selling_price_override", "ck_dim_erp_sku_creator_commission_rate"):
        if _has_constraint("dim_erp_sku", "core", name):
            op.drop_constraint(name, "dim_erp_sku", schema="core", type_="check")
    for name in ("ck_dim_platforms_other_cost_rate_range", "ck_dim_platforms_creator_commission_rate_range", "ck_dim_platforms_fee_rate_range"):
        if _has_constraint("dim_platforms", "core", name):
            op.drop_constraint(name, "dim_platforms", schema="core", type_="check")
    for column in ("min_selling_price_override", "creator_commission_rate"):
        if _has_column("dim_erp_sku", "core", column):
            op.drop_column("dim_erp_sku", column, schema="core")
    for column in ("other_cost_rate", "default_creator_commission_rate"):
        if _has_column("dim_platforms", "core", column):
            op.drop_column("dim_platforms", column, schema="core")
