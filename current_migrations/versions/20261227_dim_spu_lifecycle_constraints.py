"""给 ``core.dim_spu`` 补上**经营状态取值域**与**生命周期不变量**两条 CHECK 约束。

事故背景（2026-11-12）
----------------------
「这个 SPU 还活着吗 / 还能不能挂新 SKU」这**一个**业务事实，被两个字段分别编码：

* ``dim_spu.active``（布尔）—— 是否被软删；
* ``dim_spu.biz_status``（candidate/testing/promoted/retired）—— 经营成熟度。

两者的写入约定**不一致**：

* 软删 / 批量软删 / 恢复端点**捆绑**写两个字段；
* ``/api/spus/bulk`` 与 ``PATCH /api/spus/{spu}`` 的请求体里两者**各自独立可写**
  ⇒ 能造出 ``active=false + biz_status='candidate'`` 这种自相矛盾的行；
* ``dim_spu`` 上**当时没有任何 CHECK 约束** ⇒ 不变量只靠「大家记得一起写」维持；
* 前端 ``payloadSpu`` 整行回写 ⇒ 每次保存都把 ``active`` 原样提交一次。

⇒ 「能不能挂新 SKU」在系统里**没有唯一答案**。

建模决策（2026-11-12，Walter 拍板）
----------------------------------
**建模 A**：``active=false`` 必然是 ``retired``；但 ``retired`` 可以不删
（业务上不再经营，历史仍要留）。

⇒ 不变量：``active=false ⟹ biz_status='retired'``
⇒ 「可绑定」= ``biz_status`` 不是 ``retired`` ⇒ 判定只需一个条件。

本迁移做两件事
--------------
1. 加上 ``chk_dim_spu_biz_status``（状态取值域）；
2. 加上 ``chk_dim_spu_lifecycle``（建模 A 的不变量）。

⚠️ 两个约束的表达式**都从真源渲染**
   （``backend/services/product_spu_lifecycle.py``）——
   迁移里**不写死**状态清单 ⇒ 真源改了，迁移重新生成就是对的。
   ORM 侧也用同一对渲染函数 ⇒ 三方（ORM / 迁移 / 守护测试）不会漂移。

存量数据
--------
迁移时 ``dim_spu`` 实测 286 行，全部满足新约束
（``active=false`` 的 3 行都是 ``retired``；``active=true`` 的 283 行都是
``candidate``）⇒ **不需要改任何历史行**（符合「只保未来、历史不修」）。

但仍要**校验**存量行都满足新约束 —— 若有行落在集合外（例如历史脏数据
``active=false`` 但 ``biz_status='candidate'``），迁移必须**报错回滚**
而不是悄悄放过 ⇒ fail-closed，不丢数据。

回滚
----
``downgrade`` 把两条约束删掉 ⇒ 恢复成迁移前「无约束」的状态。
（不会丢数据：约束只是拒绝非法写入，删掉它只会让更多状态可写。）
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261227_dim_spu_lifecycle_constraints"
down_revision = "current_schema_20261226_task_center_status_constraint"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 约束所在的表。
TABLE_NAME = "dim_spu"
TABLE_SCHEMA = "core"

#: 约束名。
BIZ_STATUS_CONSTRAINT_NAME = "chk_dim_spu_biz_status"
LIFECYCLE_CONSTRAINT_NAME = "chk_dim_spu_lifecycle"


def _render_biz_status_constraint() -> str:
    """从**真源**渲染状态取值域的约束表达式。"""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.product_spu_lifecycle import (
        render_spu_biz_status_constraint,
    )

    return render_spu_biz_status_constraint()


def _render_lifecycle_constraint() -> str:
    """从**真源**渲染建模 A 不变量的约束表达式。"""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.product_spu_lifecycle import (
        render_spu_lifecycle_constraint,
    )

    return render_spu_lifecycle_constraint()


def _assert_existing_rows_satisfy_constraints(connection) -> None:
    """存量行必须已经满足新约束 —— 否则**报错回滚**（fail-closed）。"""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.product_spu_lifecycle import (
        SPU_BIZ_STATUSES,
        SPU_BIZ_STATUS_RETIRED,
    )

    invalid_status = connection.execute(
        sa.text(
            """
            SELECT biz_status, count(*) AS cnt
            FROM core.dim_spu
            GROUP BY biz_status
            """
        )
    ).fetchall()
    offenders = [
        (row[0], row[1])
        for row in invalid_status
        if row[0] not in set(SPU_BIZ_STATUSES)
    ]
    if offenders:
        raise RuntimeError(
            "core.dim_spu 存在落在经营状态全集之外的行, 拒绝继续: %s" % offenders
        )

    # 建模 A 的不变量：active=false 必须是 retired。
    broken_lifecycle = connection.execute(
        sa.text(
            """
            SELECT spu, active, biz_status
            FROM core.dim_spu
            WHERE active IS FALSE AND biz_status <> :retired
            LIMIT 20
            """
        ),
        {"retired": SPU_BIZ_STATUS_RETIRED},
    ).fetchall()
    if broken_lifecycle:
        raise RuntimeError(
            "core.dim_spu 存在 active=false 但 biz_status 不是 retired 的行 "
            "(违反建模 A 的不变量), 拒绝继续: %s" % broken_lifecycle
        )


def upgrade() -> None:
    """加上两条约束：经营状态取值域 + 生命周期不变量。

    ⚠️ 两条约束只会**拒绝**非法写入，不会让已有行失效
    ⇒ 理论上不需要改任何历史行；但仍显式校验并 fail-closed。
    """
    connection = op.get_bind()
    _assert_existing_rows_satisfy_constraints(connection)

    op.create_check_constraint(
        BIZ_STATUS_CONSTRAINT_NAME,
        TABLE_NAME,
        _render_biz_status_constraint(),
        schema=TABLE_SCHEMA,
    )
    op.create_check_constraint(
        LIFECYCLE_CONSTRAINT_NAME,
        TABLE_NAME,
        _render_lifecycle_constraint(),
        schema=TABLE_SCHEMA,
    )


def downgrade() -> None:
    """删掉两条约束，恢复到迁移前「无约束」的状态。

    ⚠️ 不会丢数据 —— 约束只是拒绝非法写入，删掉它只会让更多状态可写。
    """
    op.drop_constraint(
        LIFECYCLE_CONSTRAINT_NAME, TABLE_NAME, type_="check", schema=TABLE_SCHEMA
    )
    op.drop_constraint(
        BIZ_STATUS_CONSTRAINT_NAME, TABLE_NAME, type_="check", schema=TABLE_SCHEMA
    )
