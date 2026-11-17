"""重量段化（批次 6，2026-11-17）：SKU 改报重量段，尾程费率表改按段定价。

背景
----
承运商按**重量段**定价（Shopee SG / TikTok SG 价目表都是「≤1kg / ≤5kg / … 一档价」），
所以业务上 SKU **不用称重**，只报「落在哪一段」；承运商调价时只改费率表的那一行，
不用回改每一个 SKU。

本迁移做四件事：

1. 建 ``core.dim_weight_tiers`` —— **全局一套**重量段定义（所有平台共用同一把尺子），
   并种下标准档位。
2. ``core.dim_erp_sku``：加 ``weight_tier_code``，按老 ``weight_kg`` 回填，
   然后**删掉** ``weight_kg``（批次 6 决定：老的精确重量口径直接退役）。
3. ``finance.delivery_rate_rules``：加 ``weight_tier_code``，按老的
   ``min_weight_kg`` 回填，删掉 ``min_weight_kg`` / ``max_weight_kg``。
4. 当期唯一索引从 ``(平台, 仓, 重量下限)`` 换成 ``(平台, 仓, 重量段)``。

⚠️ **回填的取舍**
----------------
- SKU：老重量落进哪个区间就归哪个段；**没有区间的**（重量为 0 或超出最高段）
  归**最轻段** —— 与「未选段按最轻段」同一口径（用户 2026-11-17 拍板）。
- 费率行：老的重量下限落进哪个段就归哪个段。段是全局唯一的，所以同一段在不同仓
  天然对齐 ⇒ 不会出现「同一个区间两个段编码」。

⚠️ **同名段重复怎么办**
----------------------
老数据理论上不会有重叠段（写入端一直拦着重叠），但万一有，映射后同一
``(平台, 仓, 段)`` 可能出现两行当期 ⇒ 新唯一索引会建不出来。
所以建索引**之前**先把重复行停用（保留 ``effective_from`` 最新的一行当期，
其余闭区间退出当期）—— **宁可少算一档，也不能让迁移挂掉**。

⚠️ **不建外键**
--------------
``core.dim_weight_tiers`` 会被「采集机 → 云端」同步 ``TRUNCATE ... CASCADE``
（``scripts/sync_product_center_to_cloud.py``）。建外键 ⇒ 段表被清空时，
引用它的 SKU 与费率规则一起没了（**静默失效**：底线突然算不出来）。
所以 ``weight_tier_code`` 一律是普通字符串，由服务层校验存在性。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261236_weight_tiers"
down_revision = "current_schema_20261235_price_adjust_baseline_warehouse"
branch_labels = None
depends_on = None


TIER_TABLE = "dim_weight_tiers"
TIER_SCHEMA = "core"

SKU_TABLE = "dim_erp_sku"
SKU_SCHEMA = "core"

RATE_TABLE = "delivery_rate_rules"
RATE_SCHEMA = "finance"

#: 全局标准档位（轻 → 重）。区间是**左闭右开** ``[min_kg, max_kg)``。
#: ⚠️ 这是**全局一套** —— 所有平台共用同一把尺子（同一个段在哪个平台都是同一段）。
SEED_TIERS = (
    ("T01", "0-1 kg", 0, 1, 1),
    ("T02", "1-5 kg", 1, 5, 2),
    ("T03", "5-10 kg", 5, 10, 3),
    ("T04", "10-20 kg", 10, 20, 4),
    ("T05", "20-30 kg", 20, 30, 5),
    ("T06", "30 kg 以上", 30, None, 6),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _columns(table: str, schema: str) -> set[str]:
    if not _has_table(table, schema):
        return set()
    return {column["name"] for column in _inspector().get_columns(table, schema=schema)}


def _has_column(table: str, schema: str, column: str) -> bool:
    return column in _columns(table, schema)


def _has_index(table: str, schema: str, index: str) -> bool:
    if not _has_table(table, schema):
        return False
    return any(
        item["name"] == index for item in _inspector().get_indexes(table, schema=schema)
    )


def _has_constraint(table: str, schema: str, name: str) -> bool:
    if not _has_table(table, schema):
        return False
    return any(
        constraint.get("name") == name
        for constraint in _inspector().get_check_constraints(table, schema=schema)
    )


def upgrade() -> None:
    # --- 1 · 全局重量段表 -------------------------------------------------
    if not _has_table(TIER_TABLE, TIER_SCHEMA):
        op.create_table(
            TIER_TABLE,
            sa.Column("tier_code", sa.String(length=32), nullable=False),
            sa.Column("label", sa.String(length=64), nullable=False),
            sa.Column("min_kg", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("max_kg", sa.Numeric(precision=12, scale=3), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("tier_code"),
            sa.CheckConstraint("min_kg >= 0", name="ck_dim_weight_tiers_min_kg"),
            sa.CheckConstraint(
                "max_kg IS NULL OR max_kg > min_kg", name="ck_dim_weight_tiers_window"
            ),
            sa.CheckConstraint(
                "status IN ('active', 'inactive')", name="ck_dim_weight_tiers_status"
            ),
            schema=TIER_SCHEMA,
        )
        op.create_index(
            "ix_dim_weight_tiers_sort_order",
            TIER_TABLE,
            ["sort_order"],
            schema=TIER_SCHEMA,
        )

    for tier_code, label, min_kg, max_kg, sort_order in SEED_TIERS:
        op.execute(
            sa.text(
                """
                INSERT INTO core.dim_weight_tiers
                    (tier_code, label, min_kg, max_kg, sort_order, status)
                VALUES (:tier_code, :label, :min_kg, :max_kg, :sort_order, 'active')
                ON CONFLICT (tier_code) DO NOTHING
                """
            ).bindparams(
                tier_code=tier_code,
                label=label,
                min_kg=min_kg,
                max_kg=max_kg,
                sort_order=sort_order,
            )
        )

    # --- 2 · SKU：加段 → 回填 → 删精确重量 -------------------------------
    if _has_table(SKU_TABLE, SKU_SCHEMA) and not _has_column(
        SKU_TABLE, SKU_SCHEMA, "weight_tier_code"
    ):
        op.add_column(
            SKU_TABLE,
            sa.Column("weight_tier_code", sa.String(length=32), nullable=True),
            schema=SKU_SCHEMA,
        )

    if _has_column(SKU_TABLE, SKU_SCHEMA, "weight_kg"):
        # 老重量落进哪个段就归哪个段（区间左闭右开）。
        op.execute(
            sa.text(
                """
                UPDATE core.dim_erp_sku AS s
                   SET weight_tier_code = t.tier_code
                  FROM core.dim_weight_tiers AS t
                 WHERE s.weight_tier_code IS NULL
                   AND s.weight_kg IS NOT NULL
                   AND s.weight_kg >= t.min_kg
                   AND (t.max_kg IS NULL OR s.weight_kg < t.max_kg)
                """
            )
        )
        # 没落进任何段（重量为 0 / 超出最高段）⇒ 归最轻段（与「未选段」同口径）。
        op.execute(
            sa.text(
                """
                UPDATE core.dim_erp_sku AS s
                   SET weight_tier_code = (
                       SELECT t.tier_code FROM core.dim_weight_tiers AS t
                        WHERE t.status = 'active'
                        ORDER BY t.sort_order, t.min_kg
                        LIMIT 1
                   )
                 WHERE s.weight_tier_code IS NULL
                   AND s.weight_kg IS NOT NULL
                """
            )
        )
        op.drop_column(SKU_TABLE, "weight_kg", schema=SKU_SCHEMA)

    # --- 3 · 尾程费率表：加段 → 回填 → 删重量上下限 -----------------------
    if _has_table(RATE_TABLE, RATE_SCHEMA) and not _has_column(
        RATE_TABLE, RATE_SCHEMA, "weight_tier_code"
    ):
        op.add_column(
            RATE_TABLE,
            sa.Column("weight_tier_code", sa.String(length=32), nullable=True),
            schema=RATE_SCHEMA,
        )

    if _has_column(RATE_TABLE, RATE_SCHEMA, "min_weight_kg"):
        op.execute(
            sa.text(
                """
                UPDATE finance.delivery_rate_rules AS r
                   SET weight_tier_code = t.tier_code
                  FROM core.dim_weight_tiers AS t
                 WHERE r.weight_tier_code IS NULL
                   AND r.min_weight_kg >= t.min_kg
                   AND (t.max_kg IS NULL OR r.min_weight_kg < t.max_kg)
                """
            )
        )
        # 落不进任何段的行 ⇒ 归最轻段（宁可算便宜，也不能让迁移挂掉）。
        op.execute(
            sa.text(
                """
                UPDATE finance.delivery_rate_rules AS r
                   SET weight_tier_code = (
                       SELECT t.tier_code FROM core.dim_weight_tiers AS t
                        WHERE t.status = 'active'
                        ORDER BY t.sort_order, t.min_kg
                        LIMIT 1
                   ),
                       notes = COALESCE(r.notes, '')
                               || ' [20261236] 重量段回填：老重量下限无法落段，已归最轻段'
                 WHERE r.weight_tier_code IS NULL
                """
            )
        )
        op.drop_column(RATE_TABLE, "min_weight_kg", schema=RATE_SCHEMA)

    if _has_column(RATE_TABLE, RATE_SCHEMA, "max_weight_kg"):
        op.drop_column(RATE_TABLE, "max_weight_kg", schema=RATE_SCHEMA)

    for constraint in (
        "ck_delivery_rate_rules_min_weight",
        "ck_delivery_rate_rules_weight_window",
    ):
        if _has_constraint(RATE_TABLE, RATE_SCHEMA, constraint):
            op.drop_constraint(
                constraint, RATE_TABLE, schema=RATE_SCHEMA, type_="check"
            )

    if _has_column(RATE_TABLE, RATE_SCHEMA, "weight_tier_code"):
        # 同一段重复的当期行 ⇒ 先停用多余的（保留最新的一行当期）。
        op.execute(
            sa.text(
                """
                UPDATE finance.delivery_rate_rules AS r
                   SET status = 'inactive',
                       effective_to = COALESCE(r.effective_to, r.effective_from - 1)
                 WHERE r.status = 'active'
                   AND r.effective_to IS NULL
                   AND r.rule_id NOT IN (
                       SELECT DISTINCT ON (platform_code, warehouse_code, weight_tier_code)
                              rule_id
                         FROM finance.delivery_rate_rules
                        WHERE status = 'active' AND effective_to IS NULL
                        ORDER BY platform_code, warehouse_code, weight_tier_code,
                                 effective_from DESC, rule_id DESC
                   )
                """
            )
        )
        op.alter_column(
            RATE_TABLE,
            "weight_tier_code",
            nullable=False,
            schema=RATE_SCHEMA,
        )

    # --- 4 · 当期唯一索引换成按段 ----------------------------------------
    if _has_index(RATE_TABLE, RATE_SCHEMA, "uq_delivery_rate_rules_current"):
        op.drop_index(
            "uq_delivery_rate_rules_current",
            table_name=RATE_TABLE,
            schema=RATE_SCHEMA,
            postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
        )
    op.create_index(
        "uq_delivery_rate_rules_current",
        RATE_TABLE,
        ["platform_code", "warehouse_code", "weight_tier_code"],
        unique=True,
        schema=RATE_SCHEMA,
        postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
    )


def downgrade() -> None:
    # ⚠️ 回滚是**尽力还原**：老的精确重量已经随迁移丢掉了，只能用段的代表重量
    #    （段上限）回填 —— 数值不保证与迁移前逐字相同。
    if _has_table(RATE_TABLE, RATE_SCHEMA) and not _has_column(
        RATE_TABLE, RATE_SCHEMA, "min_weight_kg"
    ):
        op.add_column(
            RATE_TABLE,
            sa.Column(
                "min_weight_kg", sa.Numeric(precision=12, scale=3), nullable=True
            ),
            schema=RATE_SCHEMA,
        )
    if _has_table(RATE_TABLE, RATE_SCHEMA) and not _has_column(
        RATE_TABLE, RATE_SCHEMA, "max_weight_kg"
    ):
        op.add_column(
            RATE_TABLE,
            sa.Column(
                "max_weight_kg", sa.Numeric(precision=12, scale=3), nullable=True
            ),
            schema=RATE_SCHEMA,
        )
    if _has_column(RATE_TABLE, RATE_SCHEMA, "weight_tier_code"):
        op.execute(
            sa.text(
                """
                UPDATE finance.delivery_rate_rules AS r
                   SET min_weight_kg = t.min_kg,
                       max_weight_kg = t.max_kg
                  FROM core.dim_weight_tiers AS t
                 WHERE t.tier_code = r.weight_tier_code
                """
            )
        )
        op.drop_column(RATE_TABLE, "weight_tier_code", schema=RATE_SCHEMA)

    if _has_table(SKU_TABLE, SKU_SCHEMA) and not _has_column(
        SKU_TABLE, SKU_SCHEMA, "weight_kg"
    ):
        op.add_column(
            SKU_TABLE,
            sa.Column("weight_kg", sa.Float(), nullable=True),
            schema=SKU_SCHEMA,
        )
    if _has_column(SKU_TABLE, SKU_SCHEMA, "weight_tier_code"):
        op.execute(
            sa.text(
                """
                UPDATE core.dim_erp_sku AS s
                   SET weight_kg = COALESCE(t.max_kg, t.min_kg)
                  FROM core.dim_weight_tiers AS t
                 WHERE t.tier_code = s.weight_tier_code
                """
            )
        )
        op.drop_column(SKU_TABLE, "weight_tier_code", schema=SKU_SCHEMA)

    if _has_index(RATE_TABLE, RATE_SCHEMA, "uq_delivery_rate_rules_current"):
        op.drop_index(
            "uq_delivery_rate_rules_current",
            table_name=RATE_TABLE,
            schema=RATE_SCHEMA,
            postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
        )
    op.create_index(
        "uq_delivery_rate_rules_current",
        RATE_TABLE,
        ["platform_code", "warehouse_code", "min_weight_kg"],
        unique=True,
        schema=RATE_SCHEMA,
        postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
    )

    if _has_table(TIER_TABLE, TIER_SCHEMA):
        op.drop_table(TIER_TABLE, schema=TIER_SCHEMA)
