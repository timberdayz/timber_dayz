"""重命名档位表列：``min_age_days`` → ``min_restock_days``。

为什么改名
----------
这一列的**实际含义已经变了**：

- 改造前：档位起点 = 「库龄」（商品在这个仓存在了多久），而库龄本身算错了
- 改造后：档位起点 = 「距上次进货天数」（补货才重新开始计时，销售不重置）

继续叫 ``min_age_days`` 会让下一个读代码的人以为「档位还是按库龄触发」，
从而往档位表里塞错的数据。

**只改列名，不改任何数值**：门槛（0/60/90/120）与折扣率（0.10/0.15/0.20/0.30）
原样保留 —— 那是商业参数，不是口径问题。

约束名与索引名由 PostgreSQL 随列自动跟随，无需重建。

迁移是幂等的：目标列已存在则跳过；新旧同存时删掉旧列。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261025_sku_pricing_min_restock_days"
down_revision = "current_schema_20261024_price_adjust_baseline_table"
branch_labels = None
depends_on = None

TABLE = "sku_pricing_policies"
SCHEMA = "finance"
OLD_COLUMN = "min_age_days"
NEW_COLUMN = "min_restock_days"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE, schema=SCHEMA):
        return set()
    return {column["name"] for column in inspector.get_columns(TABLE, schema=SCHEMA)}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    if OLD_COLUMN in columns and NEW_COLUMN not in columns:
        op.alter_column(
            TABLE,
            OLD_COLUMN,
            new_column_name=NEW_COLUMN,
            schema=SCHEMA,
        )
    elif OLD_COLUMN in columns and NEW_COLUMN in columns:
        op.drop_column(TABLE, OLD_COLUMN, schema=SCHEMA)


def downgrade() -> None:
    columns = _columns()
    if not columns:
        return
    if NEW_COLUMN in columns and OLD_COLUMN not in columns:
        op.alter_column(
            TABLE,
            NEW_COLUMN,
            new_column_name=OLD_COLUMN,
            schema=SCHEMA,
        )
