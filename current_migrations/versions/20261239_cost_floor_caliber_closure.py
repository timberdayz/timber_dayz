"""成本底线口径收口（批次 9）：桶换语义 + 删「尾程占收入比」列。

背景
----
``core.dim_platforms.other_cost_rate``（界面上叫「平台其他成本率」，内部一直叫**残差桶**）
原来是恒等式反推出来的**一坨**：

    other_cost_rate = 1 − 实测采购成本率 − 实测净利率 − SPU退货率 − SPU货损率 − 默认达人佣金率

⇒ 桶里**同时混着**平台佣金、摊进去的运费、以及其它说不清的扣款。
于是产生三个连锁问题：

1. **平台佣金率填了不生效** —— ``product_pricing_service`` 的模块头明写
   「平台佣金率已包含在 other_cost_rate 内，不得单独进入分母」，
   界面上「平台佣金率」那个输入框其实**根本没进计算**。
2. **尾程进不了底线** —— 批次 4 的「成对生效」机制要求
   「分子加尾程 ⇔ 分母加回 ``delivery_cost_rate``」同时有值，
   而生产 ``delivery_cost_rate`` **全 NULL** ⇒ 尾程被完全排除在底线之外。
3. **两条链差一个桶** —— 利润链压根不扣桶 ⇒ 底线链与利润链恒差 26.78 个百分点。

本迁移
------
批次 9 拍板的口径：

    分子 = (采购成本 + 头程 + 仓储 + 贴单 + 尾程) × (1 + SPU退货率 + SPU货损率)
    分母 = 1 − 平台佣金率 − 平台其他成本率 − 达人佣金率 − 目标利润率

⇒ 桶**不再含佣金、不再含尾程**，只装「佣金与尾程之外」的平台侧按收入比例扣款；
⇒ 平台佣金率**单独进分母**；
⇒ 尾程**直接进分子**（按 SKU 重量段算的单件尾程），
   所以 ``delivery_cost_rate``（尾程占收入比）**连同它的成对生效机制一并退役**。

桶的新值：对着结算单实测
----------------------
⚠️ **踩过的坑（重要）**：``b_class.fact_shopee_orders_monthly`` 里
``实付金额`` **全空**、``预估回款金额`` 只填了 9052/13573 行 ⇒ 用它们做分母会把所有比例放大。
必须用 ``订单原始金额``（13573/13573 完整）。

Shopee（13,573 单已核，收入 1,066,248.12）：

    平台佣金 15.77%（官方 16% ✓ 自洽）｜卖家支付运费 19.01%（尾程 ⇒ 桶里剔除）
    联盟佣金 1.19%（平台默认 1.11% ✓ 同量级）｜**服务费 3.58% ⇒ 这就是新桶**
    其余分项（交易费/海外免退服务费/运费补贴/税费…）要么全空、要么全是 0

TikTok（2,515 单已核，买家实付 200,741.48）：

    平台佣金 7.62%（官方 8.175% ✓ 同量级）｜实际运费 15.88%（尾程 ⇒ 桶里剔除）
    达人佣金 5.48%（平台默认 6.06% ✓ 同量级）｜**交易手续费 3.11% ⇒ 这就是新桶**
    「总费用」31.29% ≈ 7.62+15.88+5.48+3.11 = 32.09 ✓ 印证分项齐全

⚠️ 这**推翻了早先的推算值**（旧桶做减法：Shopee 6.49% / TikTok 13.89%）：
旧桶本身的口径已经对不上现在的结算单（TikTok 旧桶 27.27% 甚至**小于**当前分项之和 32.09%）
⇒ 旧桶不可信，不宜再拿它做减法。**对着结算单实测才是能对业务讲清楚的数。**

⚠️ **只有 shopee / tiktok 有费率**：``amazon``（sales）与 ``miaoshou``（source）的费率本来就是全空
⇒ 它们本来就因 ``missing_platform_cost_rate`` 算不出底线 ⇒ 本迁移不动它们。

⚠️ **桶变小 ⇒ 分母变大 ⇒ 底线会降一点**（Shopee / SKU 920 包邮：125.34 → 118.62）。
    这不是放松纪律，是**现状那条底线本来就虚高** ——
    现状底线 157.64 的真实利润率只有 18.28%（低于目标 25%），
    因为现状分子漏了头程/仓储/贴单/尾程四块成本。新口径下利润率精确等于目标利润率。

⚠️ **桶由人工维护**（拍板）：结算单分项列本身残缺（很多扣款项没采集到）⇒ 实测值可能偏小。
    上线后由运营在「定价设置」里按结算单持续维护；上线首月盯实际利润率，低于目标就上调桶。

⚠️ **本迁移的删列必须「退得回去」**（``downgrade`` 是删列迁移最危险的一段）：
    现有演练（``test_schema_cleanup_rehearsal.py``）**只跑 ``upgrade head``**，
    看不见 downgrade 里的问题 ⇒ 本迁移的 ``downgrade`` 一开始真的藏着两个当场崩的 bug：
    ① ``op.drop_column(RETIRED_COLUMN, schema=..., table_name=...)`` ——
       列名必须作**第二个位置参数**，且不能同时传 ``table_name=``；
    ② ``op.add_column(t, sa.Column(..., schema=SCHEMA))`` ——
       ``schema`` 属于 ``op.add_column``，**不能**传给 ``sa.Column`` 本身。
    现在**往返演练已固化成守护测试**：``backend/tests/test_batch9_migration_roundtrip.py``
    （baseline → upgrade 20261238 → upgrade head → **downgrade 20261238** → upgrade head，
    断言列恢复、桶值/来源/版本全部还原）。
"""

from alembic import op
import sqlalchemy as sa

revision = "current_schema_20261239_cost_floor_caliber_closure"
down_revision = "current_schema_20261238_official_platform_fee_rates"
branch_labels = None
depends_on = None

SCHEMA = "core"
PLATFORM_TABLE = "dim_platforms"

#: 桶的新值（结算单实测，2026-01 ~ 2026-11 已完成订单）。
#:
#: 口径：**佣金与尾程之外**的平台侧按收入比例扣款。
#: Shopee = 「服务费」；TikTok = 「交易手续费」。
#:
#: ⚠️ 只给**有结算单实测**的平台落值；其余平台（amazon / miaoshou）的费率本来就是空，
#:    保持空 ⇒ 它们继续因 ``missing_platform_cost_rate`` 算不出底线（**宁可不算，也不算错**）。
PLATFORM_OTHER_COST_RATE = {
    "shopee": 0.0358,
    "tiktok": 0.0311,
}

#: 桶的来源标注：把「平台佣金是官方牌价」与「桶是结算单实测」两件事分开写清楚。
#:
#: ⚠️ ``fee_rate_effective_from`` 保持**佣金**的官方生效日不动 ——
#:    那一列记的是平台佣金何时生效，桶的实测日写在 source 里。
PLATFORM_FEE_SOURCE = {
    "shopee": (
        "official_3pf_commission_2026_01_01 + "
        "manual_2026_11_19_settlement_ledger_service_fee"
    ),
    "tiktok": (
        "official_sg_2026_04_01 + "
        "manual_2026_11_19_settlement_ledger_transaction_fee"
    ),
}
FEE_RATE_VERSION = "v4"

#: downgrade 用的旧值（旧口径：含佣金、含摊进去的运费）。
LEGACY_OTHER_COST_RATE = {
    "shopee": 0.4165,
    "tiktok": 0.2727,
}
LEGACY_FEE_RATE_SOURCE = {
    "shopee": "official_3pf_commission_2026_01_01 + b_class_measured_2026_01_07_residual",
    "tiktok": "official_sg_2026_04_01 + b_class_measured_2026_01_07_residual",
}
LEGACY_FEE_RATE_VERSION = "v3"

#: 被退役的列与它的检查约束（批次 9 B 路线：尾程直接进分子，不再需要「占收入比」拆分基准）。
RETIRED_COLUMN = "delivery_cost_rate"
RETIRED_CONSTRAINT = "ck_dim_platforms_delivery_cost_rate_range"


def _has_column(schema: str, table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return column in {
        item["name"] for item in inspector.get_columns(table, schema=schema)
    }


def _has_constraint(schema: str, table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    # ⚠️ SQLAlchemy 的 ``Inspector`` **没有** ``get_constraints``（那是 Django 的 API）
    #    ⇒ CHECK 约束必须走 ``get_check_constraints``。
    #    写错方法名 ⇒ 迁移在 upgrade 阶段 AttributeError ⇒ **整条迁移链断**。
    return name in {
        item["name"] for item in inspector.get_check_constraints(table, schema=schema)
    }


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1) 桶换口径：落结算单实测值 -------------------------------------------
    for platform_code, rate in PLATFORM_OTHER_COST_RATE.items():
        bind.execute(
            sa.text(
                f"UPDATE {SCHEMA}.{PLATFORM_TABLE} SET "
                "other_cost_rate = :rate, "
                "fee_rate_source = :src, "
                "fee_rate_version = :ver "
                "WHERE platform_code = :code"
            ),
            {
                "rate": rate,
                "src": PLATFORM_FEE_SOURCE[platform_code],
                "ver": FEE_RATE_VERSION,
                "code": platform_code,
            },
        )

    # --- 2) 退役「尾程占收入比」列 ------------------------------------------------
    # ⚠️ 删列前先删它的 CHECK 约束：约束依赖这一列，顺序反了会报错。
    if _has_constraint(SCHEMA, PLATFORM_TABLE, RETIRED_CONSTRAINT):
        op.drop_constraint(
            RETIRED_CONSTRAINT,
            PLATFORM_TABLE,
            schema=SCHEMA,
            type_="check",
        )
    if _has_column(SCHEMA, PLATFORM_TABLE, RETIRED_COLUMN):
        # ⚠️ SQLAlchemy 2.x 的 ``op.drop_column`` 签名是 ``(table_name, column_name, schema=...)``
        #    —— 列名是**第二个位置参数**，**不能**再同时传 ``table_name=`` 关键字
        #    （否则 TypeError: drop_column() got multiple values for argument 'table_name'）。
        #    注意：``op.add_column`` 的签名相反，是 ``(table_name, column, schema=...)``。
        op.drop_column(PLATFORM_TABLE, RETIRED_COLUMN, schema=SCHEMA)

def downgrade() -> None:
    bind = op.get_bind()

    # --- 1) 恢复「尾程占收入比」列 + 检查约束 ------------------------------------
    if not _has_column(SCHEMA, PLATFORM_TABLE, RETIRED_COLUMN):
        # ⚠️ ``schema`` 是 **``op.add_column``** 的参数，**不能**传给 ``sa.Column`` 本身
        #    （``Column`` 会把它当「方言专属参数」⇒ TypeError: Additional arguments
        #    should be named <dialectname>_<argument>, got 'schema'）。
        #    ⚠️ 这条只有**真正跑 downgrade** 才会暴露 —— 现有演练只跑 upgrade head。
        op.add_column(
            PLATFORM_TABLE,
            sa.Column(
                RETIRED_COLUMN,
                sa.Numeric(12, 8),
                nullable=True,
            ),
            schema=SCHEMA,
        )
    if not _has_constraint(SCHEMA, PLATFORM_TABLE, RETIRED_CONSTRAINT):
        op.create_check_constraint(
            RETIRED_CONSTRAINT,
            PLATFORM_TABLE,
            "delivery_cost_rate IS NULL OR (delivery_cost_rate >= 0 AND delivery_cost_rate < 1)",
            schema=SCHEMA,
        )

    # --- 2) 桶恢复旧值（旧口径：含佣金、含摊进去的运费）--------------------------
    for platform_code, rate in LEGACY_OTHER_COST_RATE.items():
        bind.execute(
            sa.text(
                f"UPDATE {SCHEMA}.{PLATFORM_TABLE} SET "
                "other_cost_rate = :rate, "
                "fee_rate_source = :src, "
                "fee_rate_version = :ver "
                "WHERE platform_code = :code"
            ),
            {
                "rate": rate,
                "src": LEGACY_FEE_RATE_SOURCE[platform_code],
                "ver": LEGACY_FEE_RATE_VERSION,
                "code": platform_code,
            },
        )
