"""语义别名归一化解析能力 —— 让 products 域能真正解析出标准字段。

背景
----
``semantic.fact_products_atomic`` 通过 ``semantic.resolve_alias()`` 从行的
``raw_data`` 里按**逐字相等**取标准字段值。真实表头却带各种修饰:

* ``"销售额（已付款订单） (SGD)"`` —— 口径后缀 + 币种后缀
* ``"商品曝光次数.1"``               —— Excel 多级表头展开后的重名列
* ``"买家支付(RMB)"`` / ``"利润（rmb）"`` —— 币种后缀
* ``"*商品sku"`` / ``"下单时间\\n"``     —— 必填星号 / 换行

实测(2026-11-08, live 开发库)
-----------------------------
* ``semantic.semantic_field_aliases`` 的 products 域 47 条 builtin 别名,
  对 shopee 真实 45 个表头的命中率是 **0/45**;
* ⇒ ``semantic.fact_products_atomic`` 里 shopee **25810 行**的
  ``product_id / product_name / item_status / sales_amount / sales_volume /
  order_count / impressions / clicks / conversion_rate`` **全部为空**;
* ⇒ 视图里的 ``COALESCE(..., 0)`` 把"没解析出来"伪装成"业务上真的是 0"
  ⇒ **25810 行全 0 无人发现**;
* 对照组 ``semantic.fact_orders_atomic``(shopee 30607 行 / tiktok 5567 行)
  **100% 命中** ⇒ 语义层机制本身没问题, 问题精确锁定在 products 域。

本迁移做什么
------------
1. ``semantic.semantic_field_aliases`` 加 ``normalized_alias`` 列
   (存**实际用于匹配的形态**, 与 ``raw_alias`` 的可读写法可以不同);
2. 建 ``semantic.normalize_alias(text)`` —— 与 Python 侧
   ``backend/services/semantic_field_registry.py::normalize_semantic_alias()``
   **同规则**的 PG 侧归一化;
3. 建 ``semantic.resolve_alias_normalized(...)`` —— 按归一形态解析,
   其它语义与 ``resolve_alias()`` 完全一致;
4. seed products 域的**真实表头**别名(36 条, 由字典派生)。

**不改任何视图** —— 视图切换到新解析函数是**下一步**独立迁移的事。
这样本迁移即使有问题也只影响"新能力", 不会动到任何既有取数路径。

fail-closed
-----------
PG 侧归一化与 Python 侧是**两份实现**(迁移自包含, 不允许 import backend),
所以必须逐条比对。本迁移内嵌 **34 条真实表头**的期望归一结果,
执行时逐条调用 PG 函数核对 —— **任一条不一致就抛错回滚**。

⚠ 归一化**只用于匹配**, 原始列名一律保留在 ``raw_data`` 里。
⚠ 归一化**不剥口径后缀**(「已下单」/「已付款」是**不同的业务事实**:
   实测两套口径的销售额平均差 5.15%、最大差 175.89) —— 剥了就混了。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261130_semantic_alias_normalized_resolution"
down_revision = "current_schema_20261129_reclassify_error_page_shop_discoveries"
branch_labels = None
depends_on = None


#: SQL 资产正本(函数定义 + seed)。迁移读它执行 —— 资产是**唯一正本**,
#: 迁移只负责"按顺序落地 + 自检", 不复制 SQL 文本。
_ASSET_RELATIVE_PATH = "sql/semantic/semantic_alias_normalize_asset.sql"

#: 归一化一致性自检用例(原始表头 → 期望归一形态)。
#:
#: 这些期望值由 Python 侧 ``normalize_semantic_alias()`` 产出
#: (见 ``scripts/generate_semantic_alias_normalize_asset.py`` 的用例集),
#: 本迁移在执行时逐条核对 PG 侧结果 —— 不一致即回滚。
_NORMALIZATION_CASES: tuple[tuple[str, str], ...] = (
    ("商品编号", "商品编号"),
    ("商品", "商品"),
    ("Current Item Status", "currentitemstatus"),
    ("规格编号", "规格编号"),
    ("已付款订单", "已付款订单"),
    ("已下订单", "已下订单"),
    ("销售额（已付款订单） (SGD)", "销售额(已付款订单)"),
    ("销售额（已下订单） (SGD)", "销售额(已下订单)"),
    ("销售额（已确定订单）", "销售额(已确定订单)"),
    ("件数（已付款订单）", "件数(已付款订单)"),
    ("件数（已下订单）", "件数(已下订单)"),
    ("转化率（已付款订单）", "转化率(已付款订单)"),
    ("转化率（已下订单）", "转化率(已下订单)"),
    ("订单转化率（已付款订单）", "订单转化率(已付款订单)"),
    ("买家数（已付款订单）", "买家数(已付款订单)"),
    ("每笔订单销售额（已付款订单） (SGD)", "每笔订单销售额(已付款订单)"),
    ("不重复的商品曝光量", "不重复的商品曝光量"),
    ("不重复的商品点击量", "不重复的商品点击量"),
    ("商品展示量", "商品展示量"),
    ("商品点击量", "商品点击量"),
    ("商品访客数量", "商品访客数量"),
    ("商品页面访问量", "商品页面访问量"),
    ("商品跳出率", "商品跳出率"),
    ("商品曝光次数.1", "商品曝光次数"),
    ("GMV.2", "gmv"),
    ("CTOR（SKU 订单）.2", "ctor(sku订单)"),
    ("去重点击成交转化率_订单", "去重点击成交转化率订单"),
    ("已加购的用户数.3", "已加购的用户数"),
    ("买家支付(RMB)", "买家支付"),
    ("利润（rmb）", "利润"),
    ("*商品sku", "商品sku"),
    ("下单时间\n", "下单时间"),
    ("商品 sku", "商品sku"),
    ("商品　sku", "商品sku"),
)


def _bind():
    return op.get_bind()


def _asset_sql() -> str:
    """读 SQL 资产正本。"""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    asset_path = repo_root / _ASSET_RELATIVE_PATH
    if not asset_path.exists():
        raise RuntimeError(f"缺 SQL 资产: {asset_path}")
    return asset_path.read_text(encoding="utf-8")


def _seed_raw_aliases() -> tuple[str, ...]:
    """从资产里取出本次 seed 的 products 域 raw_alias(回滚要精确删这几行)。"""
    import re

    pattern = re.compile(r"\(\s*'products'\s*,\s*'[^']+'\s*,\s*'([^']+)'")
    found: list[str] = []
    for raw in pattern.findall(_asset_sql()):
        if raw not in found:
            found.append(raw)
    return tuple(found)


def _assert_normalization_matches(bind) -> None:
    """PG 侧归一化与 Python 侧逐条比对 —— 不一致即回滚(fail-closed)。"""
    mismatches: list[tuple[str, str, object]] = []
    for raw, expected in _NORMALIZATION_CASES:
        actual = bind.execute(
            sa.text("SELECT semantic.normalize_alias(:raw)"),
            {"raw": raw},
        ).scalar()
        if actual != expected:
            mismatches.append((raw, expected, actual))

    if mismatches:
        details = "; ".join(
            f"{raw!r} 期望 {expected!r} 实得 {actual!r}"
            for raw, expected, actual in mismatches
        )
        raise RuntimeError("PG 侧归一化与 Python 侧不一致, 迁移回滚: " + details)


def _assert_seed_landed(bind) -> None:
    """seed 必须真的落库了 —— 别名表是视图取数的唯一事实源。"""
    row = (
        bind.execute(
            sa.text(
                """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE normalized_alias IS NOT NULL) AS with_norm
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'products'
            """
            )
        )
        .mappings()
        .one()
    )
    total = int(row["total"] or 0)
    with_norm = int(row["with_norm"] or 0)
    if total < 36:
        raise RuntimeError(f"products 域别名条数不足: {total} < 36")
    if with_norm != total:
        raise RuntimeError(
            f"products 域有别名缺 normalized_alias: {total - with_norm} 条"
        )


def upgrade() -> None:
    bind = _bind()

    # 1) 先加列 —— 资产的函数体引用该列(check_function_bodies 会检查)
    bind.execute(
        sa.text(
            """
            ALTER TABLE semantic.semantic_field_aliases
            ADD COLUMN IF NOT EXISTS normalized_alias TEXT
            """
        )
    )

    # 2) 资产: 两个函数 + products 域 seed
    bind.execute(sa.text(_asset_sql()))

    # 3) 回填既有行的归一形态
    bind.execute(
        sa.text(
            """
            UPDATE semantic.semantic_field_aliases
            SET normalized_alias = semantic.normalize_alias(raw_alias)
            WHERE normalized_alias IS NULL
               OR normalized_alias <> semantic.normalize_alias(raw_alias)
            """
        )
    )

    # 4) fail-closed 自检
    _assert_normalization_matches(bind)
    _assert_seed_landed(bind)


def downgrade() -> None:
    bind = _bind()

    # 精确删掉本次 seed 的那几行(按 raw_alias 列表), 不误伤别的别名
    raw_aliases = _seed_raw_aliases()
    if raw_aliases:
        bind.execute(
            sa.text(
                """
                DELETE FROM semantic.semantic_field_aliases
                WHERE data_domain = 'products'
                  AND raw_alias = ANY(CAST(:raw_aliases AS text[]))
                """
            ),
            {"raw_aliases": list(raw_aliases)},
        )

    bind.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS semantic.resolve_alias_normalized(TEXT, TEXT, TEXT, TEXT, TEXT)"
        )
    )
    bind.execute(sa.text("DROP FUNCTION IF EXISTS semantic.normalize_alias(TEXT)"))
    bind.execute(
        sa.text(
            """
            ALTER TABLE semantic.semantic_field_aliases
            DROP COLUMN IF EXISTS normalized_alias
            """
        )
    )
