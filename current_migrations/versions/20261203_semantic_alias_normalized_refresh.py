"""别名表的归一化形态补齐 —— 2026-11-08。

背景
----
别名表 ``semantic.semantic_field_aliases`` 有两列:

* ``raw_alias`` —— 人能读懂的原始写法;
* ``normalized_alias`` —— 实际用于**归一化匹配**的形态。

``semantic.resolve_alias_normalized()`` 按 ``normalized_alias`` 匹配
(``alias.normalized_alias IS NOT NULL AND normalized_keys ? alias.normalized_alias``)。

本轮实测出的两个洞:

1. **seed 的 INSERT 列清单里没有 ``normalized_alias``**
   ⇒ 字典新增的别名落库时该列是 NULL ⇒ 归一化解析**看不见这些行**。
   实测受影响的 6 条: ``revenue`` / ``qty`` / ``CVR`` / 「订单数量」/
   「商品标题」/「件数」。
   ⇒ 修法: seed 多带一列 ``normalized_alias``, ON CONFLICT 一并更新
   (``scripts/generate_semantic_alias_seed.py`` 负责生成)。

2. **归一化资产(B1)与字典漂移**: 资产里还留着字典已经撤回的
   ``item_status`` / 「状态」—— 状态类列名一旦被认成语义键就会污染身份推断。
   ⇒ 修法: 归一化资产**由字典重生成**
   (``scripts/generate_semantic_alias_normalize_asset.py``), 不再手改。

本迁移做什么
------------
1. 重落**别名资产**(字典派生的 seed): 补齐 ``normalized_alias``;
2. 重落**归一化资产**: 两个 PG 侧函数 + products 域 seed(带归一形态);
3. 自检:
   * products 域 builtin 行数 == 字典派生行数(不多不少);
   * products 域**没有** ``normalized_alias IS NULL`` 的行
     ⇒ 归一化解析看得见每一行;
   * 字典已撤回的别名(「状态」)确实不在表里。

⚠️ 本迁移**不碰** ``template_confirmed`` 行, 也不碰任何业务数据。
"""

from alembic import op
import re
import sqlalchemy as sa


revision = "current_schema_20261203_semantic_alias_normalized_refresh"
down_revision = "current_schema_20261202_semantic_alias_prune"
branch_labels = None
depends_on = None


#: 本迁移要落的两个 SQL 资产(仓库正本, 迁移只负责按顺序落地 + 自检)。
_ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"
_NORMALIZE_ASSET = "sql/semantic/semantic_alias_normalize_asset.sql"

#: 资产里「陈旧 builtin 行清理」段的标记。
_PRUNE_MARKER = "-- \u9648\u65e7 builtin \u884c\u6e05\u7406"

#: 清理段的 VALUES 元组形态。
_SEED_TUPLE_PATTERN = re.compile(r"\(\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'[^']*'\s*\)")


def _asset(relative_path: str) -> str:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    asset_path = repo_root / relative_path
    if not asset_path.exists():
        raise RuntimeError(f"\u7f3a SQL \u8d44\u4ea7: {asset_path}")
    return asset_path.read_text(encoding="utf-8")


def _seed_row_count(asset_text: str) -> int:
    """数出清理段里登记的 seed 行数(= 字典派生出来的 builtin 行数)。"""
    start = asset_text.find(_PRUNE_MARKER)
    if start < 0:
        raise RuntimeError(
            "\u522b\u540d\u8d44\u4ea7\u91cc\u6ca1\u6709\u9648\u65e7 builtin \u884c\u6e05\u7406\u6bb5"
        )
    end = asset_text.find(";", start)
    segment = asset_text[start:end] if end > 0 else asset_text[start:]
    return len(_SEED_TUPLE_PATTERN.findall(segment))


def upgrade() -> None:
    bind = op.get_bind()

    alias_asset = _asset(_ALIAS_ASSET)
    expected_rows = _seed_row_count(alias_asset)

    # 1) 别名资产: seed(带 normalized_alias) + 清理陈旧 builtin 行
    bind.execute(sa.text(alias_asset))

    # 2) 归一化资产: 两个 PG 侧函数 + products 域 seed
    bind.execute(sa.text(_asset(_NORMALIZE_ASSET)))

    # 3) 自检 ①: builtin 行数必须与字典一致(不多不少)
    row = (
        bind.execute(
            sa.text(
                """
            SELECT
                count(*) FILTER (WHERE source = 'builtin') AS builtin_rows,
                count(*) FILTER (
                    WHERE source = 'builtin' AND normalized_alias IS NULL
                ) AS builtin_without_normalized
            FROM semantic.semantic_field_aliases
            WHERE data_domain = 'products'
            """
            )
        )
        .mappings()
        .one()
    )
    builtin_rows = int(row["builtin_rows"] or 0)
    without_normalized = int(row["builtin_without_normalized"] or 0)

    if builtin_rows != expected_rows:
        raise RuntimeError(
            "\u522b\u540d\u8868\u4e0e\u5b57\u5178\u4e0d\u4e00\u81f4: "
            f"\u8868\u91cc builtin \u884c {builtin_rows} \u6761, \u5b57\u5178\u6d3e\u751f {expected_rows} \u6761"
        )

    # 4) 自检 ②: 不能有 builtin 行缺归一形态(否则归一化解析看不见它)
    if without_normalized:
        raise RuntimeError(
            f"\u522b\u540d\u8868\u91cc\u6709 {without_normalized} \u6761 builtin \u884c\u7f3a normalized_alias"
        )

    # 5) 自检 ③: \u5b57\u5178\u5df2\u64a4\u56de\u7684\u522b\u540d\u4e0d\u5f97\u8fd8\u5728\u8868\u91cc
    withdrawn = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM semantic.semantic_field_aliases
            WHERE standard_field = 'item_status'
              AND raw_alias = '\u72b6\u6001'
            """
        )
    ).scalar()
    if withdrawn:
        raise RuntimeError(
            "\u5b57\u5178\u5df2\u64a4\u56de\u7684\u522b\u540d\u4ecd\u5728\u522b\u540d\u8868\u91cc"
        )


def downgrade() -> None:
    """\u672c\u8fc1\u79fb**\u4e0d\u652f\u6301\u964d\u7ea7**\u3002

    \u964d\u7ea7\u8981\u4e48\u628a\u5df2\u64a4\u56de\u7684\u522b\u540d\u5199\u56de\u53bb(\u7b49\u4e8e\u628a\u4e8b\u5b9e\u6e90\u6f02\u79fb\u518d\u5199\u56de\u5e93),
    \u8981\u4e48\u628a\u5b57\u5178\u6d3e\u751f\u7684\u5f52\u4e00\u5f62\u6001\u5220\u6389(\u7b49\u4e8e\u8ba9\u8868\u8ba4\u4e0d\u51fa\u771f\u5b9e\u8868\u5934)\u3002
    \u4e24\u8005\u90fd\u662f\u300c\u9020\u6570\u300d, \u4e0d\u662f\u56de\u9000\u3002\u8fc1\u79fb\u94fe\u662f\u5355\u5411\u7684
    (fail-closed, \u65e0 downgrade \u652f\u6301)\u3002
    """
    raise NotImplementedError("\u672c\u8fc1\u79fb\u4e0d\u652f\u6301 downgrade")
