"""平台尾程占比拆分基准（把尾程从 other_cost_rate 残差桶里剔出去）。

背景
----
``core.dim_platforms.other_cost_rate`` 是**恒等式反推出来的残差桶**：

    other_cost_rate = 1 − 实测采购成本率 − 实测净利率 − SPU退货率 − SPU货损率 − 默认达人佣金率

「实测净利率」来自平台订单事实表的 ``利润`` 列，而平台的 ``利润`` **已经扣过运费**
（生产库 2026-07 实测：TikTok 的 ``总费用`` 里恰好包含 ``实际运费``，
Shopee 的 ``卖家支付运费`` 直接从结算里扣）。所以 **尾程就在这个桶里**。

批次 4 起尾程按 SKU 重量单件计价（``finance.delivery_rate_rules``），如果既把尾程
加进成本底线的分子、又不从分母里剔出去 ⇒ **同一笔尾程被扣两次**，底线被抬高。

因此进底线必须**成对生效**：

    分子 = 采购成本 + 尾程配送费
    分母 = 1 − other_cost_rate + delivery_cost_rate − 达人佣金率 − 货损率 − 退货率 − 目标利润率

``delivery_cost_rate`` = 尾程配送费占收入比（= 平台尾程均值 ÷ 平台平均售价）。

⚠️ **本次不填种子值**
--------------------
尾程占比的权威口径是「**我们自己的费率表**算出来的平台尾程均值 ÷ 平台平均售价」
（费率表是尾程的**唯一真源**，分子里的尾程也出自它 ⇒ 两边天然配对，不重复扣）。

而批次 3 刚建的 ``finance.delivery_rate_rules`` **目前还没有任何费率数据**，
用平台订单事实表反推的运费占比又**混着头程**（平台的运费线 = 国内派送 + 国际头程），
用它当尾程拆分会把头程也从残差里一并剔掉 ⇒ 底线偏低 ⇒ 危险。

所以：**列先建好、语义定死、留空**。业务维护好尾程费率后，在「定价设置」里填上
这个平台级拆分比例，尾程即进入成本底线。留空时**尾程不进成本底线**（宁可不算，
也不重复扣），并在界面上明确提示。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261234_delivery_cost_rate_split"
down_revision = "current_schema_20261233_delivery_rate_rules"
branch_labels = None
depends_on = None


TABLE = "dim_platforms"
SCHEMA = "core"
COLUMN = "delivery_cost_rate"
CONSTRAINT = "ck_dim_platforms_delivery_cost_rate_range"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE, schema=SCHEMA):
        return False
    return COLUMN in {
        column["name"] for column in inspector.get_columns(TABLE, schema=SCHEMA)
    }


def _has_constraint() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE, schema=SCHEMA):
        return False
    return any(
        constraint.get("name") == CONSTRAINT
        for constraint in inspector.get_check_constraints(TABLE, schema=SCHEMA)
    )


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.Numeric(precision=12, scale=8), nullable=True),
            schema=SCHEMA,
        )
    if not _has_constraint():
        op.create_check_constraint(
            CONSTRAINT,
            TABLE,
            "delivery_cost_rate IS NULL OR (delivery_cost_rate >= 0 AND delivery_cost_rate < 1)",
            schema=SCHEMA,
        )


def downgrade() -> None:
    if _has_constraint():
        op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    if _has_column():
        op.drop_column(TABLE, COLUMN, schema=SCHEMA)
