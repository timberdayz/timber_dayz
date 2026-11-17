"""平台费率按官方牌价校准（Shopee 三方仓 16% / TikTok 非 BXP 8.175%）+ Shopee SG 尾程改官方 3PF 标准。

背景
----
``core.dim_platforms`` 的费率是 **2026-01-07 的实测残差**（来源 ``b_class_measured_2026_01_07``），
而官方在这之后两次调价：

- **Shopee SG**：自 2026-01-01 起，跨境直邮(SLS) 与三方仓(3PF) 佣金统一 **16%（含税）**，
  官方海外仓(FBS) 11%。我们的履约模式是「头程 → 当地本地仓 → 消费者」，本地仓是
  自有/三方仓 ⇒ 落在 **三方仓(3PF)** 口径 ⇒ 佣金 16%。
- **TikTok Shop SG**：自 2026-04-01 起，一般类目非 BXP **8.175%（含 GST）**，
  BXP 7.085%，电子产品 6.54%/5.45%；另收交易手续费 3.27%。

⇒ 旧的 14.87% / 7.37% 偏低 ⇒ **底线偏低 ⇒ 定价偏低 ⇒ 亏本**。

尾程
----
Shopee SG 尾程从「三方合非 SPA」价目表切到**官方 3PF 尾程费用标准**
（自 2025-03-18 起，买家承担 1.99 + 卖家承担 X / 每个包裹）。

⚠️ **口径：商家包邮时承担的是「买家那份 + 卖家那份」的总额**。
    买家付 1.99 的时候，那 1.99 不是卖家的成本；一旦包邮（买家付 0），
    卖家要一个人把两份都扛下来 ⇒ 费率表记的是**总额**。
    旧行记的就是总额（4.29 = 1.99 + 2.30），本迁移保持同一口径。

⚠️ 本迁移**不动** ``other_cost_rate``（残差桶）与 ``delivery_cost_rate``（尾程占收入比）：
    - 残差桶是实测反推值，要用新实测数据重算，本轮没有 ⇒ 保持原值。
    - 尾程占收入比必须与费率表**同源**，但它的重算前置条件（SKU 段归类、
      订单级 vs 单件摊的口径）现在都不具备 ⇒ 保持原值，缺口记在台账里。
    - 两者当前都不影响底线：``free_shipping`` 默认关闭 ⇒ 尾程不进底线。

汇率沿用 **5.2077**（SGD→CNY，``manual_market_mid_2026-11``）：本轮不引入新汇率变量。
"""

from alembic import op
import sqlalchemy as sa

revision = "current_schema_20261238_official_platform_fee_rates"
down_revision = "current_schema_20261237_free_shipping_flag"
branch_labels = None
depends_on = None

SCHEMA = "core"
PLATFORM_TABLE = "dim_platforms"
RULE_SCHEMA = "finance"
RULE_TABLE = "delivery_rate_rules"

#: SGD → CNY 汇率（与既有尾程费率行同一个口径，见 notes 里的来源标记）。
SGD_TO_CNY = 5.2077

#: 平台佣金按官方牌价校准（只改**平台佣金率**，残差桶与达人佣金率不动）。
#:
#: ``source`` 把两件事分开写清楚：佣金是官方牌价，残差桶还是 1 月实测 ——
#: 混成一个来源会让人以为整行都是官方值。
PLATFORM_FEE_UPDATES = {
    "shopee": {
        "default_fee_rate": 0.16,
        "fee_rate_effective_from": "2026-01-01",
        "fee_rate_source": "official_3pf_commission_2026_01_01 + b_class_measured_2026_01_07_residual",
        "fee_rate_version": "v3",
    },
    "tiktok": {
        "default_fee_rate": 0.08175,
        "fee_rate_effective_from": "2026-04-01",
        "fee_rate_source": "official_sg_2026_04_01 + b_class_measured_2026_01_07_residual",
        "fee_rate_version": "v3",
    },
}

PLATFORM_FEE_ROLLBACK = {
    # 旧口径是 2026-01-07 的实测残差 ⇒ 生效日期也要回到那一天，
    # 否则降级后会留下"费率是 1 月实测、日期却是官方调价日"的自相矛盾行。
    "shopee": {"default_fee_rate": 0.1487, "fee_rate_effective_from": "2026-01-07"},
    "tiktok": {"default_fee_rate": 0.0737, "fee_rate_effective_from": "2026-01-07"},
}

#: Shopee SG 尾程：官方 3PF 尾程费用标准（2025-03-18 起）。
#:
#: ``buyer`` = 买家承担（包邮时由商家扛下来），``seller`` = 卖家承担，
#: ``total_sgd`` = 商家包邮时的**总额**（= 费率表里记的金额）。
SHOPEE_SG_3PF_TIERS = [
    ("T01", 1.99, 2.03, 4.02),
    ("T02", 1.99, 2.87, 4.86),
    ("T03", 1.99, 3.38, 5.37),
    ("T04", 1.99, 5.42, 7.41),
    ("T05", 1.99, 10.00, 11.99),
]

SHOPEE_SG_WAREHOUSE = "SG-01"
TAIL_SOURCE = "shopee_sg_3pf_standard_2025_03_18"
TAIL_VERSION = "v2"

#: 旧行（"三方合非 SPA" 价目表）里记的总额，改回去用于 downgrade。
LEGACY_SHOPEE_SG_TOTALS = {
    "T01": 4.29,
    "T02": 5.20,
    "T03": 5.78,
    "T04": 8.06,
    "T05": 13.19,
}


def _round_cny(sgd: float) -> float:
    """按汇率折算成人民币等值，保留两位（表里是 Numeric(18,2)）。"""
    return round(sgd * SGD_TO_CNY, 2)


def _has_table(schema: str, table: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def _has_column(schema: str, table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return column in {
        item["name"] for item in inspector.get_columns(table, schema=schema)
    }


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1) 平台佣金按官方牌价校准 -------------------------------------------
    for platform_code, values in PLATFORM_FEE_UPDATES.items():
        bind.execute(
            sa.text(
                f"UPDATE {SCHEMA}.{PLATFORM_TABLE} SET "
                "default_fee_rate = :fee, "
                "fee_rate_effective_from = :eff, "
                "fee_rate_source = :src, "
                "fee_rate_version = :ver "
                "WHERE platform_code = :code"
            ),
            {
                "fee": values["default_fee_rate"],
                "eff": values["fee_rate_effective_from"],
                "src": values["fee_rate_source"],
                "ver": values["fee_rate_version"],
                "code": platform_code,
            },
        )

    # --- 2) Shopee SG 尾程改官方 3PF 标准 ------------------------------------
    if not _has_table(RULE_SCHEMA, RULE_TABLE):
        return
    has_notes = _has_column(RULE_SCHEMA, RULE_TABLE, "notes")
    for tier_code, buyer_sgd, seller_sgd, total_sgd in SHOPEE_SG_3PF_TIERS:
        unit_price = _round_cny(total_sgd)
        notes = (
            f"Shopee 官方《3PF 收费标准》新加坡站点 3PF 尾程费用标准（2025-03-18 起）："
            f"买家承担 SGD {buyer_sgd:.2f} + 卖家承担 SGD {seller_sgd:.2f} = "
            f"SGD {total_sgd:.2f}（商家包邮时承担总额）；"
            f"按 SGD→CNY {SGD_TO_CNY}（manual_market_mid_2026-11）折算"
        )
        existing = bind.execute(
            sa.text(
                f"SELECT rule_id FROM {RULE_SCHEMA}.{RULE_TABLE} "
                "WHERE platform_code = :platform AND warehouse_code = :warehouse "
                "AND weight_tier_code = :tier AND status = 'active'"
            ),
            {
                "platform": "shopee",
                "warehouse": SHOPEE_SG_WAREHOUSE,
                "tier": tier_code,
            },
        ).fetchone()
        if existing:
            bind.execute(
                sa.text(
                    f"UPDATE {RULE_SCHEMA}.{RULE_TABLE} SET "
                    "unit_price = :price, currency = 'CNY', source = :src, "
                    "version = :ver, notes = :notes "
                    "WHERE rule_id = :rid"
                ),
                {
                    "price": unit_price,
                    "src": TAIL_SOURCE,
                    "ver": TAIL_VERSION,
                    "notes": notes,
                    "rid": existing[0],
                },
            )
            continue
        columns = [
            "platform_code",
            "warehouse_code",
            "weight_tier_code",
            "unit_price",
            "currency",
            "effective_from",
            "status",
            "source",
            "version",
        ]
        values = {
            "platform_code": "shopee",
            "warehouse_code": SHOPEE_SG_WAREHOUSE,
            "weight_tier_code": tier_code,
            "unit_price": unit_price,
            "currency": "CNY",
            "effective_from": "2026-11-17",
            "status": "active",
            "source": TAIL_SOURCE,
            "version": TAIL_VERSION,
        }
        if has_notes:
            columns.append("notes")
            values["notes"] = notes
        bind.execute(
            sa.text(
                f"INSERT INTO {RULE_SCHEMA}.{RULE_TABLE} "
                f"({', '.join(columns)}) VALUES "
                f"({', '.join(':' + name for name in columns)})"
            ),
            values,
        )


def downgrade() -> None:
    bind = op.get_bind()

    for platform_code, values in PLATFORM_FEE_ROLLBACK.items():
        bind.execute(
            sa.text(
                f"UPDATE {SCHEMA}.{PLATFORM_TABLE} SET "
                "default_fee_rate = :fee, "
                "fee_rate_effective_from = :eff, "
                "fee_rate_source = 'b_class_measured_2026_01_07', "
                "fee_rate_version = 'v2' "
                "WHERE platform_code = :code"
            ),
            {
                "fee": values["default_fee_rate"],
                "eff": values["fee_rate_effective_from"],
                "code": platform_code,
            },
        )

    if not _has_table(RULE_SCHEMA, RULE_TABLE):
        return
    has_notes = _has_column(RULE_SCHEMA, RULE_TABLE, "notes")
    for tier_code, _buyer, _seller, _total in SHOPEE_SG_3PF_TIERS:
        legacy_total = LEGACY_SHOPEE_SG_TOTALS[tier_code]
        notes = (
            f"Shopee SG 价目表(2026-01-01起)：买家承担 SGD 1.99 + 卖家承担三方合 SGD "
            f"{legacy_total - 1.99:.2f} = SGD {legacy_total:.2f}；"
            f"按 SGD→CNY {SGD_TO_CNY}（2026-11-17 manual_market_mid_2026-11）折算"
        )
        params = {
            "price": _round_cny(legacy_total),
            "src": "shopee_sg_ratecard_2026",
            "ver": "v1",
            "notes": notes,
            "platform": "shopee",
            "warehouse": SHOPEE_SG_WAREHOUSE,
            "tier": tier_code,
        }
        if has_notes:
            bind.execute(
                sa.text(
                    f"UPDATE {RULE_SCHEMA}.{RULE_TABLE} SET "
                    "unit_price = :price, currency = 'CNY', source = :src, "
                    "version = :ver, notes = :notes "
                    "WHERE platform_code = :platform AND warehouse_code = :warehouse "
                    "AND weight_tier_code = :tier"
                ),
                params,
            )
        else:
            bind.execute(
                sa.text(
                    f"UPDATE {RULE_SCHEMA}.{RULE_TABLE} SET "
                    "unit_price = :price, currency = 'CNY', source = :src, "
                    "version = :ver "
                    "WHERE platform_code = :platform AND warehouse_code = :warehouse "
                    "AND weight_tier_code = :tier"
                ),
                params,
            )
