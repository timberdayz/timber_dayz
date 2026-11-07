"""别名登记表的「事实源收敛」迁移 —— 2026-11-08。

背景
----
别名表 ``semantic.semantic_field_aliases`` 的 ``source='builtin'`` 行是
**字典派生**的(:mod:`backend.services.semantic_field_registry`), 事实源只有一处。

但 seed 只会 INSERT / UPSERT, **不会删除** —— 字典里删掉的别名会永远留在表里
⇒ 表认着一套字典里没有的映射(事实源漂移)。

实测(开发库 xihong_erp):

* 表里 195 条 builtin 行, 字典只认 182 条 ⇒ **13 条陈旧**;
* 其中包含 ``item_status`` 的「状态」/ ``status`` —— 状态类列名一旦被认成
  语义键, 就会污染身份推断(守护测试:
  ``backend/tests/test_workbench_template_update_flow.py``);
* 其余 11 条是历史手写 seed 留下的英文/中文别名, 实测在 ``raw_data`` 里
  **0 次出现**, 且大多与字典里的别名在归一化后等价(例: ``Sales Amount``
  ≡ ``sales amount``) ⇒ 清理不丢能力。

本迁移做什么
------------
1. 重新落**别名资产**(字典派生的 seed): 补齐本轮新增的
   ``revenue`` / ``qty`` / ``CVR`` / 「订单数量」四个裸别名, 并把两个
   无歧义的旧表头(「商品标题」/「件数」)吸收进字典;
2. 删掉 ``source='builtin'`` 且**不在当前字典**里的陈旧行
   (只删 builtin —— ``template_confirmed`` / ``manual`` / ``conflict``
   是用户确认过的, 不归字典管, 谁也不许动);
3. 自检: 表里的 builtin 行数必须与资产里的 seed 行数**完全一致**。

⚠️ 本迁移**不碰** ``template_confirmed`` 行(28 条), 也不碰别域的行。
⚠️ 迁移只做「让事实源收敛」, 不改任何一行业务数据。
"""

from alembic import op
import re
import sqlalchemy as sa


revision = "current_schema_20261202_semantic_alias_prune"
down_revision = "current_schema_20261201_semantic_products_row_kind_caliber"
branch_labels = None
depends_on = None


#: 本迁移要落的 SQL 资产(仓库正本, 迁移只负责按顺序落地 + 自检)。
_ALIAS_ASSET = "sql/semantic/semantic_alias_registry.sql"

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

    asset_text = _asset(_ALIAS_ASSET)
    expected_rows = _seed_row_count(asset_text)

    # 1) 落别名资产(INSERT/UPSERT + 清理陈旧 builtin 行)
    bind.execute(sa.text(asset_text))

    # 2) 自检: builtin 行数必须与字典一致(不多不少)
    builtin_rows = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM semantic.semantic_field_aliases
            WHERE source = 'builtin'
              AND data_domain = 'products'
            """
        )
    ).scalar()
    builtin_rows = int(builtin_rows or 0)
    if builtin_rows != expected_rows:
        raise RuntimeError(
            "别名表与字典不一致: "
            f"表里 builtin 行 {builtin_rows} 条, 字典派生 {expected_rows} 条"
        )


def downgrade() -> None:
    """本迁移**不支持降级**。

    降级要么把陈旧 builtin 行恢复回来(等于把事实源漂移再写回库),
    要么把字典派生的别名删掉(等于让表认不出真实表头)。
    两者都是「造数」, 不是回退。迁移链是单向的(fail-closed, 无 downgrade 支持)。
    """
    raise NotImplementedError("\u672c\u8fc1\u79fb\u4e0d\u652f\u6301 downgrade")
