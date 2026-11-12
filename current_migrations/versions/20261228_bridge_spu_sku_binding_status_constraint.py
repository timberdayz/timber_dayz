"""给 ``core.bridge_spu_sku`` 补上**归属状态取值域**的 CHECK 约束。

事故背景（2026-11-12）
----------------------
「这个货挂在哪个款上」是**一段带生效区间的关联**，不是货身上的一个字段：

* ``effective_from`` / ``effective_to`` —— 归属的生效区间；
* ``binding_status`` —— 这段关系的**状态**。

而 ``binding_status`` 的三个取值语义**各不相同**，却没有任何一处把它们写在一起：

======================  ==========================================  ==========
取值                   含义                                          可复活？
======================  ==========================================  ==========
``active``             当前有效                                      —
``inactive``           被**软删**封存（款被删 ⇒ 它的货的归属封存）   ✅ 可以
``historical``         被**换款**归档（货从款 A 换到款 B）           ❌ 不可以
======================  ==========================================  ==========

问题
----
1. ``core.bridge_spu_sku`` 上**当时没有任何 CHECK 约束**
   ⇒ 第四个状态值会**静默**写进库；
2. 三个值的判定散落在各处（恢复端点只认 ``inactive``，
   换款路径写的是 ``historical``）⇒ 迟早漂移；
3. 一旦漂移出第四个值，恢复端点就会复活一条**本该留作历史**的关系
   （把货挂回一个可能已经下线的款）。

⇒ 把取值域收进真源（``backend/services/product_spu_binding.py``），
   由真源渲染成 ``CHECK`` 约束 ⇒ ORM / 迁移 / 守护测试三方不会漂移。

存量数据
--------
迁移时 ``core.bridge_spu_sku`` 实测 1121 行：

* 1118 行 ``active``（``effective_to IS NULL``）；
* 3 行 ``inactive``（软删封存）；
* 0 行落在取值域之外。

⇒ **不需要改任何历史行**（符合「只保未来、历史不修」）。

但仍要**校验**存量行都满足新约束 —— 若有行落在集合外，
迁移必须**报错回滚**而不是悄悄放过 ⇒ fail-closed，不丢数据。

回滚
----
``downgrade`` 把约束删掉 ⇒ 恢复成迁移前「无约束」的状态。
（不会丢数据：约束只是拒绝非法写入，删掉它只会让更多状态可写。）
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261228_bridge_spu_sku_binding_status_constraint"
down_revision = "current_schema_20261227_dim_spu_lifecycle_constraints"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 约束所在的表。
TABLE_NAME = "bridge_spu_sku"
TABLE_SCHEMA = "core"

#: 约束名。
CONSTRAINT_NAME = "chk_bridge_spu_sku_binding_status"


def _render_binding_status_constraint() -> str:
    """从**真源**渲染归属状态取值域的约束表达式。"""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.product_spu_binding import (
        render_binding_status_constraint,
    )

    return render_binding_status_constraint()


def _assert_existing_rows_satisfy_constraint(connection) -> None:
    """存量行必须已经满足新约束 —— 否则**报错回滚**（fail-closed）。"""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.product_spu_binding import BINDING_STATUSES

    rows = connection.execute(
        sa.text(
            """
            SELECT binding_status, count(*) AS cnt
            FROM core.bridge_spu_sku
            GROUP BY binding_status
            """
        )
    ).fetchall()
    offenders = [
        (row[0], row[1])
        for row in rows
        if row[0] not in set(BINDING_STATUSES)
    ]
    if offenders:
        raise RuntimeError(
            "core.bridge_spu_sku 存在落在归属状态全集之外的行, 拒绝继续: %s" % offenders
        )


def upgrade() -> None:
    """加上归属状态的取值域约束。

    ⚠️ 该约束只会**拒绝**非法写入，不会让已有行失效
    ⇒ 理论上不需要改任何历史行；但仍显式校验并 fail-closed。
    """
    connection = op.get_bind()
    _assert_existing_rows_satisfy_constraint(connection)

    op.create_check_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        _render_binding_status_constraint(),
        schema=TABLE_SCHEMA,
    )


def downgrade() -> None:
    """删掉约束，恢复到迁移前「无约束」的状态。

    ⚠️ 不会丢数据 —— 约束只是拒绝非法写入，删掉它只会让更多状态可写。
    """
    op.drop_constraint(
        CONSTRAINT_NAME, TABLE_NAME, type_="check", schema=TABLE_SCHEMA
    )
