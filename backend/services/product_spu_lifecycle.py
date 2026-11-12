"""SPU 生命周期 **SSOT**（律 1「真源只能一个，而且必须写在纸上」）。

⚠️ **本文件是 SPU 经营状态与「能不能挂货」的唯一定义处**。

背景（2026-11-12）
------------------
「这个 SPU 还活着吗 / 还能不能挂新 SKU」这**一个**业务事实，被两个字段分别编码：

* ``dim_spu.active``（布尔）—— 是否被软删；
* ``dim_spu.biz_status``（candidate/testing/promoted/retired）—— 经营成熟度。

而两者的写入约定**不一致**：

* 软删 / 批量软删 / 恢复端点**捆绑**写两个字段；
* ``/api/spus/bulk`` 与 ``PATCH /api/spus/{spu}`` 的请求体里 ``active`` 与
  ``biz_status`` **各自独立可写** ⇒ 能造出 ``active=false +
  biz_status='candidate'`` 这种自相矛盾的行；
* ``dim_spu`` 上当时**没有任何 CHECK 约束** ⇒ 不变量只靠「大家记得一起写」维持；
* 前端 ``payloadSpu`` 整行回写 ⇒ 每次保存都把 ``active`` 原样提交一次。

⇒ 「能不能挂新 SKU」在系统里**没有唯一答案**。

建模决策（2026-11-12，Walter 拍板）
----------------------------------
**建模 A**：``active=false`` 必然是 ``retired``；但 ``retired`` 可以不删
（业务上不再经营，历史仍要留）。

⇒ **不变量**：``active=false ⟹ biz_status='retired'``
⇒ **可绑定** = ``biz_status`` 不是 ``retired``
   ⇒ 判定**只需一个条件**（已删的款必然是 retired，自动被排除）。

派生关系（谁引用谁）
--------------------
* ``modules/core/db/schema_parts/dimensions.py`` 的两个 ``CheckConstraint``
  → 用 :func:`render_spu_biz_status_constraint` 与
  :func:`render_spu_lifecycle_constraint` 渲染；
* ``backend/domains/business/routers/product_center.py`` 的两个值域端点
  与两处绑定入口 → 用 :func:`spu_assignable_condition` /
  :func:`is_spu_assignable`；
* 迁移 ``current_migrations/versions/20261227_dim_spu_lifecycle_constraints.py``
  → 同样从本文件渲染；
* 守护测试 ``backend/tests/test_product_spu_lifecycle_ssot_contract.py``
  断言「ORM 约束 == 路由判定 == 迁移渲染结果」。

⚠️ **不要在本文件之外再手抄状态清单或生命周期条件**。要改，改这里，
让守护测试逼着所有派生点跟上。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 经营状态全集（唯一定义处）
# ---------------------------------------------------------------------------

#: 候选 —— 新建、还没进入经营验证。
SPU_BIZ_STATUS_CANDIDATE = "candidate"

#: 测试 —— 正在验证经营表现。
SPU_BIZ_STATUS_TESTING = "testing"

#: 主推 —— 正式在卖。
SPU_BIZ_STATUS_PROMOTED = "promoted"

#: 淘汰 —— 业务上不再经营这个款。
#:
#: ⚠️ **淘汰不等于删除**（建模 A）：
#:    * 运营把状态改成「淘汰」⇒ ``active`` 保持 true ⇒ 历史仍可查；
#:    * 走删除流程 ⇒ ``active=false`` 且 ``biz_status`` 强制置为 retired。
#:    ⇒ 恒有 ``active=false ⟹ biz_status='retired'``。
SPU_BIZ_STATUS_RETIRED = "retired"


#: **SPU 的全部经营状态** —— 本文件唯一的状态全集声明。
SPU_BIZ_STATUSES: frozenset[str] = frozenset(
    {
        SPU_BIZ_STATUS_CANDIDATE,
        SPU_BIZ_STATUS_TESTING,
        SPU_BIZ_STATUS_PROMOTED,
        SPU_BIZ_STATUS_RETIRED,
    }
)


#: **还能挂新 SKU 的状态集合** —— 「可绑定」的唯一口径。
#:
#: ⚠️ 依赖建模 A 的不变量（``active=false ⟹ biz_status='retired'``）：
#:    已删除的款必然是 retired ⇒ 只看 ``biz_status`` 就够排除它们。
#:    该不变量由 ``dim_spu`` 的 ``CHECK`` 约束在数据库层兜底。
SPU_ASSIGNABLE_STATUSES: frozenset[str] = frozenset(
    set(SPU_BIZ_STATUSES) - {SPU_BIZ_STATUS_RETIRED}
)


# ---------------------------------------------------------------------------
# SQL 渲染（ORM 约束与迁移脚本都调它 ⇒ 不可能在其中一处漏状态）
# ---------------------------------------------------------------------------


def render_spu_biz_status_constraint() -> str:
    """把 :data:`SPU_BIZ_STATUSES` 渲染成 ``biz_status`` 取值域的 ``CHECK`` 表达式。

    ⚠️ 渲染成**有序**（排序后）⇒ 同一份状态集合永远渲染出同一串 SQL
    ⇒ 迁移比对（迁移前后约束定义一致）可以按字符串比。
    """
    values = sorted(SPU_BIZ_STATUSES)
    quoted = ", ".join("'%s'" % value for value in values)
    return "biz_status IN (%s)" % quoted


def render_spu_lifecycle_constraint() -> str:
    """把**建模 A** 的不变量渲染成 ``CHECK`` 表达式。

    不变量：``active=false`` 必然是 ``retired``。

    ⇒ 渲染成 ``active OR biz_status = 'retired'``：
    ``active`` 为真时放行（逻辑淘汰、历史可查），
    为假时强制必须是 ``retired``（已删除的款必然已淘汰）。
    """
    return "active OR biz_status = '%s'" % SPU_BIZ_STATUS_RETIRED


def render_spu_assignable_constraint() -> str:
    """把 :data:`SPU_ASSIGNABLE_STATUSES` 渲染成「可绑定」的 ``CHECK`` 表达式。

    仅用于**展示与比对**（例如迁移里核对存量行）；
    运行时判定请用 :func:`spu_assignable_condition` / :func:`is_spu_assignable`，
    避免同一口径出现第三种写法。
    """
    values = sorted(SPU_ASSIGNABLE_STATUSES)
    quoted = ", ".join("'%s'" % value for value in values)
    return "biz_status IN (%s)" % quoted


# ---------------------------------------------------------------------------
# 运行时判定（查询与校验共用同一口径）
# ---------------------------------------------------------------------------


def spu_assignable_condition():
    """「这个 SPU 现在还能不能挂新 SKU」的**唯一** SQL 判定。

    返回 SQLAlchemy 条件对象 ⇒ 值域端点的候选集查询与写入时的校验
    **引用的是同一个对象**，不可能各写一份而漂移。

    ⚠️ 延迟 import ORM —— 真源模块本身不依赖 ``modules.core.db``，
    避免 ``modules`` ↔ ``backend`` 的循环导入。
    """
    from modules.core.db import DimSpu

    return DimSpu.biz_status.in_(sorted(SPU_ASSIGNABLE_STATUSES))


def is_spu_assignable(spu_row) -> bool:
    """Python 侧的「可绑定」判定 —— 与 :func:`spu_assignable_condition` 同一口径。

    两者都是 :data:`SPU_ASSIGNABLE_STATUSES` 的派生 ⇒ 不会漂移。
    """
    return getattr(spu_row, "biz_status", None) in SPU_ASSIGNABLE_STATUSES
