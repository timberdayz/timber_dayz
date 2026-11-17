"""包邮开关（批次 6，2026-11-17）：跨境电商不是默认包邮，而是选择性包邮。

背景
----
尾程配送费（仓 → 买家那段快递费）此前是「配了费率就等于我们包邮」——
口径把**承运商报价**与**谁付运费**混成了一件事。

实际业务是：跨境电商**不是默认包邮**，而是**选择性包邮** ——
同一个平台上，有的 listing 包邮、有的不包邮。所以「包不包邮」是
**SKU × 平台** 的经营选择，与费率表（平台 × 仓 × 重量段的承运商报价）**无关**。

本迁移给 ``finance.sku_platform_pricing`` 加一列 ``free_shipping``：

- ``TRUE``  = 包邮 ⇒ 商家承担尾程 ⇒ 尾程进成本底线分子、平台尾程占比进分母
  （成对生效）、利润链扣尾程。
- ``FALSE`` = 明确不包邮 ⇒ 买家付运费 ⇒ 商家不承担尾程 ⇒ 尾程**完全不适用**
  （不进底线、不报「缺尾程费率」、利润链尾程按 0 计）。
- ``NULL``  = 未设置 ⇒ **按不包邮处理**（默认关闭，符合行业现状）。

⚠️ 为什么住在 ``finance.sku_platform_pricing``
----------------------------------------------
这张表的唯一键就是 ``(sku_id, platform_code)`` —— 与「包不包邮」的业务粒度
**完全一致**（同一平台的所有仓共用一个包邮决策：包邮是渠道策略，不是仓库属性）。
而且它**不参与**「采集机 → 云端」的同步 TRUNCATE ⇒ 运营设的包邮开关不会被同步抹掉。

⚠️ **不填种子值**
----------------
现有数据一律是「未设置」⇒ 按不包邮 ⇒ 与改造前「尾程算不出来 ⇒ 利润链算不出来」
相比，利润链会从空白变成有值。这是对的：不包邮的 SKU 本来就没有尾程成本。
包邮的 SKU 由运营在「平台 SKU 利润测算」页逐个开启。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261237_free_shipping_flag"
down_revision = "current_schema_20261236_weight_tiers"
branch_labels = None
depends_on = None


TABLE = "sku_platform_pricing"
SCHEMA = "finance"
COLUMN = "free_shipping"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE, schema=SCHEMA):
        return False
    return COLUMN in {
        column["name"] for column in inspector.get_columns(TABLE, schema=SCHEMA)
    }


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.Boolean(), nullable=True),
            schema=SCHEMA,
        )


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN, schema=SCHEMA)
