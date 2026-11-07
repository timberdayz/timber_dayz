"""让 ``semantic.semantic_field_aliases.status`` 能取 ``conflict``。

背景
----
批次 D 的硬原则是「**冲突不静默覆盖**」:
同一个列名被对齐到**两个**语义键时, 原记录保持不动, 额外写一条
``status='conflict'`` 的记录, 交人来裁决。

但库里的 CHECK 约束只允许两个取值::

    CONSTRAINT ck_semantic_field_aliases_status
        CHECK (status IN ('active', 'disabled'))

⇒ 写 ``conflict`` 行会直接被数据库拒绝(``violates check constraint``),
冲突检测功能等于没上线。

为什么需要第三个状态
--------------------
``active`` / ``disabled`` 表达的是「这条别名**生效不生效**」,
无法表达「这条别名**还没定**」。

用一个新状态而不是复用 ``disabled``, 是因为两者的语义不同:

* ``disabled``  —— 人已经裁决过, 就是不要这条;
* ``conflict``  —— 人**还没裁决**, 同一个列名挂着两个候选语义键。

把「还没定」混进 ``disabled`` 会让人误以为冲突已经被处理过,
下一次沉淀又会把它当成「已处理」而跳过 ⇒ 冲突被永久吞掉。

为什么不在代码里绕过去
----------------------
把 conflict 行写成 ``disabled`` 再靠代码标记 —— 那样「未裁决」和「已否决」
在库里长得一模一样, 治理面板没法区分, 报警也没法只报未裁决的那些。
而且 ORM 侧(``modules/core/db/schema_parts/data_platform.py``)已经按
``('active', 'disabled', 'conflict')`` 写了 CHECK —— ORM 与库不一致,
任何 ``create_all`` 都会失败。

幂等
----
先 ``DROP CONSTRAINT IF EXISTS`` 再 ``ADD CONSTRAINT`` ⇒ 可重复执行。
downgrade 反向: 把 ``conflict`` 行改回 ``disabled``(保留数据, 不删),
再把 CHECK 收窄回两值。

为什么 conflict 行要带 ``__conflict__`` 前缀
-------------------------------------------
``standard_field`` 上有唯一约束 ``uq_semantic_field_aliases_identity_norm``。
同一个 (域, 列名, 平台, 粒度) 指向两个语义键时, 如果不加前缀,
第二条行会撞唯一约束 ⇒ 冲突行根本写不进去。
前缀让「冲突候选」与「生效记录」在唯一键上天然分开。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261124_semantic_field_alias_conflict_status"
down_revision = "current_schema_20261123_shopee_analytics_monthly_date_format"
branch_labels = None
depends_on = None


_TABLE = "semantic.semantic_field_aliases"
_CONSTRAINT = "ck_semantic_field_aliases_status"

#: 迁移完成后允许的状态集合。
_AFTER_STATUSES = ("active", "disabled", "conflict")
#: 回滚后的状态集合。
_BEFORE_STATUSES = ("active", "disabled")


def _drop_constraint(bind) -> None:
    bind.execute(sa.text(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_CONSTRAINT}"))


def _add_constraint(bind, statuses: tuple[str, ...]) -> None:
    values = ", ".join(f"'{status}'" for status in statuses)
    bind.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CONSTRAINT} "
            f"CHECK (status IN ({values}))"
        )
    )


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"conflict_rows_promoted": 0}
    _drop_constraint(bind)
    _add_constraint(bind, _AFTER_STATUSES)

    # 兜底: 万一历史上有用别的方式塞进来的 conflict 行(理论上不可能,
    # 因为旧 CHECK 不允许), 这里保持原样即可 —— 只是让统计有意义。
    result = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {_TABLE} WHERE status = 'conflict'")
    )
    stats["conflict_rows_promoted"] = int(result.scalar() or 0)
    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。

    回滚时把 ``conflict`` 行降级成 ``disabled`` —— **不删数据**,
    这样回滚再升级仍然保留冲突痕迹。
    """
    stats = {"conflict_rows_downgraded": 0}
    result = bind.execute(
        sa.text(f"UPDATE {_TABLE} SET status = 'disabled' WHERE status = 'conflict'")
    )
    stats["conflict_rows_downgraded"] = int(result.rowcount or 0)
    _drop_constraint(bind)
    _add_constraint(bind, _BEFORE_STATUSES)
    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
