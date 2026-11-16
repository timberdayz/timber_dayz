"""调价通知基线下沉到仓维度（批次 4 · 仓维度统一）。

背景
----
批次 4 起尾程配送费按「平台 × 仓 × 重量段」计价 ⇒ 最低售价底线变成
**SKU × 平台 × 仓** 的量（同一件商品在马来仓与新加坡仓的底线可以不同）。

基线表 ``ops.price_adjust_baselines`` 的主键必须跟着走，否则：
A 仓的底线变了，会被记成「所有仓的底线都变了」。

变更
----
1. 新增列 ``warehouse_code``；
2. 老行回填成**空串**（老口径的底线没有仓维度）；
3. 主键改成 ``(sku_id, platform_code, warehouse_code)``。

⚠️ **老基线自动失效，而且这是有意的**
老行（``warehouse_code = ''``）与任何真实仓都对不上 ⇒ 不会被拿来和新状态比较
⇒ **不会误报一批"底线变了"**。代价是上线后第一轮变更只重建基线、不通知 ——
安全的方向（宁可少报，不可错报）。

迁移是幂等的：每一步都带存在性检查。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261235_price_adjust_baseline_warehouse"
down_revision = "current_schema_20261234_delivery_cost_rate_split"
branch_labels = None
depends_on = None


TABLE = "price_adjust_baselines"
SCHEMA = "ops"
COLUMN = "warehouse_code"
LEGACY_MARKER = ""
# ⚠️ 主键名**不能硬编码**：建表时叫 `pk_price_adjust_baselines`，
#    但 20261115 那次改复合主键把它重建成了 `price_adjust_baselines_pkey`
#    （PostgreSQL 的默认名）。这里从库里读实际名字，读不到才回落。
PK_FALLBACK_NAME = "price_adjust_baselines_pkey"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table(TABLE, schema=SCHEMA)


def _has_column() -> bool:
    if not _has_table():
        return False
    return COLUMN in {
        column["name"] for column in _inspector().get_columns(TABLE, schema=SCHEMA)
    }


def _primary_key_columns() -> list[str]:
    if not _has_table():
        return []
    return list(
        _inspector().get_pk_constraint(TABLE, schema=SCHEMA)["constrained_columns"]
    )


def _primary_key_name() -> str | None:
    if not _has_table():
        return None
    return _inspector().get_pk_constraint(TABLE, schema=SCHEMA).get("name")


def upgrade() -> None:
    if not _has_table():
        return
    if not _has_column():
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=32), nullable=True),
            schema=SCHEMA,
        )
    # 老行回填：老口径的底线没有仓维度 ⇒ 用空串标记（与任何真实仓都对不上）。
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.{TABLE} SET {COLUMN} = :marker WHERE {COLUMN} IS NULL"
        ).bindparams(marker=LEGACY_MARKER)
    )
    op.alter_column(
        TABLE, COLUMN, nullable=False, existing_type=sa.String(length=32), schema=SCHEMA
    )
    if _primary_key_columns() != ["sku_id", "platform_code", COLUMN]:
        op.drop_constraint(
            _primary_key_name() or PK_FALLBACK_NAME,
            TABLE,
            schema=SCHEMA,
            type_="primary",
        )
        op.create_primary_key(
            PK_FALLBACK_NAME, TABLE, ["sku_id", "platform_code", COLUMN], schema=SCHEMA
        )


def downgrade() -> None:
    if not _has_table():
        return
    if _primary_key_columns() == ["sku_id", "platform_code", COLUMN]:
        op.drop_constraint(
            _primary_key_name() or PK_FALLBACK_NAME,
            TABLE,
            schema=SCHEMA,
            type_="primary",
        )
        # 回退到 (sku_id, platform_code)：仓维度的行会先折叠成老口径的行。
        op.execute(
            sa.text(
                "DELETE FROM {schema}.{table} a USING {schema}.{table} b "
                "WHERE a.sku_id = b.sku_id AND a.platform_code = b.platform_code "
                "AND a.{column} <> b.{column}".format(
                    schema=SCHEMA, table=TABLE, column=COLUMN
                )
            )
        )
        op.create_primary_key(
            PK_FALLBACK_NAME, TABLE, ["sku_id", "platform_code"], schema=SCHEMA
        )
    if _has_column():
        op.drop_column(TABLE, COLUMN, schema=SCHEMA)
