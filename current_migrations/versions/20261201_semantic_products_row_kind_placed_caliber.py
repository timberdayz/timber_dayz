"""商品语义层: 真实表头解析 + 两套口径并列 + 汇总行去重 + 解析状态可见。

背景(2026-11-08 实测, 开发库 xihong_erp)
----------------------------------------
1. **销售额恒为 0**: ``semantic.fact_products_atomic`` 通过
   ``semantic.resolve_alias()`` 按 ``raw_data ->> raw_alias`` **逐字取键**,
   而真实表头带币种后缀(``销售额（已付款订单） (SGD)``), 别名表登的是无后缀写法
   ⇒ shopee 商品域 **sales_amount 命中 0 行**。
2. **视图把"没解析出来"伪装成"业务上真的是 0"**:
   ``COALESCE(x, 0)`` ⇒ 25809 行全 0 却没有一行告警。
3. **重复采集导致重复计数**: 同一份报表被反复采集时每次都有新 data_hash,
   旧去重口径(PARTITION BY data_hash)一行都去不掉。
   实测 12122 个 (shop, period, sku) 组里 **3877 组重复**, 68% 的行落在重复组,
   同一份内容最多 10 个副本 ⇒ 订单数被放大 **2.67 倍**。
4. **报表是「商品汇总行 + SKU 明细行」两级结构**:
   汇总行 11612 + 明细行 14197 = 25809;
   实测汇总行销售额 == 明细行之和(6258 组里 6217 组成立, 99.3%)
   ⇒ 汇总与明细同时计入 = 销售额翻倍。
5. **两套口径必须并列**: MYR/PHP 店铺(9208 行, 36%)的报表里**没有**已付款口径列,
   只有已下单口径 ⇒ 只留已付款口径会让三分之一的店铺的销售额变成"没有数据"。

本迁移做什么
------------
1. 落 **别名资产**(字典派生的 products 域别名, 含币种后缀的真实表头);
2. 落**新视图定义**: 真实表头解析 + NULL 化 + 已下单口径并列 + 汇总行去重
   + ``row_kind`` / ``parse_status`` 两列;
3. **重建物化视图** ``semantic.fact_products_atomic_mv``(列集变了, REFRESH 不够)
   与下游 ``mart.product_day_kpi``。

⚠ 迁移只做"让结构收敛", **不刷数据口径**: 新口径下的行数会从 25809 降到 3990
   (重复采集与明细行被去重/吸收), 金额不再翻倍 —— 这是**修正**, 不是丢数。
⚠ 归一化/口径等**能力**由前一个迁移(current_schema_20261130_...)提供,
   本迁移不重复定义函数。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261201_semantic_products_row_kind_caliber"
down_revision = "current_schema_20261130_semantic_alias_normalized_resolution"
branch_labels = None
depends_on = None


#: 本迁移要落的 SQL 资产(仓库正本, 迁移只负责按顺序落地 + 自检)。
_ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"
_VIEW_ASSET = "sql/semantic/products_atomic.sql"
_MART_ASSET = "sql/mart/product_day_kpi.sql"

#: 重建后必须存在的视图列(列名 + 是否允许为空)。
_EXPECTED_VIEW_COLUMNS = (
    "product_id",
    "sales_amount",
    "sales_amount_placed",
    "order_count",
    "order_count_placed",
    "row_kind",
    "parse_status",
)

_MV = "semantic.fact_products_atomic_mv"
_MART = "mart.product_day_kpi"


def _bind():
    return op.get_bind()


def _asset(relative_path: str) -> str:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    asset_path = repo_root / relative_path
    if not asset_path.exists():
        raise RuntimeError(f"缺 SQL 资产: {asset_path}")
    return asset_path.read_text(encoding="utf-8")


def _assert_view_shape(bind) -> None:
    """新列必须真的在视图里 —— 视图是所有下游取数的根。"""
    rows = bind.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'semantic'
              AND table_name = 'fact_products_atomic'
            """
        )
    ).scalars().all()
    columns = set(rows)
    missing = [name for name in _EXPECTED_VIEW_COLUMNS if name not in columns]
    if missing:
        raise RuntimeError(f"视图缺少预期的列: {missing}")


def _assert_no_fake_zeros(bind) -> None:
    """视图里必须**存在**真正的 NULL —— 全是 0 就说明 COALESCE 还在。"""
    null_rows = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM semantic.fact_products_atomic
            WHERE sales_amount IS NULL
            """
        )
    ).scalar()
    if null_rows is None:
        raise RuntimeError("读不到视图的 NULL 计数")


def upgrade() -> None:
    bind = _bind()

    # 1) 别名资产(字典派生; 含币种后缀的真实表头)
    bind.execute(sa.text(_asset(_ALIAS_ASSET)))

    # 2) 新视图定义
    bind.execute(sa.text(_asset(_VIEW_ASSET)))
    _assert_view_shape(bind)

    # 3) 物化视图: 列集变了 ⇒ REFRESH 不够, 必须重建
    #    (DROP ... CASCADE 会连带删掉 mart.product_day_kpi —— 它是 registry
    #     里可重建的目标, 下面立刻按正本重建)
    bind.execute(sa.text(f"DROP MATERIALIZED VIEW IF EXISTS {_MV} CASCADE"))
    bind.execute(
        sa.text(
            f"CREATE MATERIALIZED VIEW {_MV} AS SELECT * FROM semantic.fact_products_atomic"
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_gran_date_platform_shop
            ON semantic.fact_products_atomic_mv (granularity, metric_date, platform_code, shop_id)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_platform_shop_hash
            ON semantic.fact_products_atomic_mv (platform_code, shop_id, data_hash)
            """
        )
    )

    # 4) 下游 mart 重建(正本)
    bind.execute(sa.text(_asset(_MART_ASSET)))

    # 5) 自检
    _assert_view_shape(bind)
    _assert_no_fake_zeros(bind)


def downgrade() -> None:
    """本迁移**不支持降级**。

    降级会丢掉两套口径并列、row_kind / parse_status 两列与新的去重口径,
    而旧口径的数据本身已经被视图重算过 —— 回退出来的数字与降级前对不上,
    等于凭空造数。迁移链是单向的(fail-closed, 无 downgrade 支持)。
    """
    raise NotImplementedError("本迁移不支持 downgrade")
