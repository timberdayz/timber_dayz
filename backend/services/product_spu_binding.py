"""SKU ↔ SPU **归属关系**的 SSOT（律 1「真源只能一个，而且必须写在纸上」）。

⚠️ **本文件是「归属关系」的唯一定义处**（与
``backend/services/product_spu_lifecycle.py`` 管的「SPU 自身状态」是两件事）。

背景（2026-11-12）
------------------
``core.bridge_spu_sku`` 是一张**带生效区间**的关联表：

* ``effective_from`` —— 归属从哪天生效；
* ``effective_to``   —— 归属到哪天为止（``NULL`` = 至今仍有效）；
* ``binding_status`` —— ``active``（当前有效）/ ``inactive``（被软删封存，可复活）/
  ``historical``（被换款归档，历史证据，不可复活）。

⇒ 「SKU 属于哪个 SPU」**不是 SKU 身上的一个字段**，
  而是「一段归属关系在今天的落点」。
⇒ 换款 = 旧关系归档（落 ``effective_to``、状态转 ``historical``）
  + 新关系生效（落 ``effective_from``）。
⇒ 款被软删 = 它的归属被封存（状态转 ``inactive``）—— **可复活**。

问题
----
前端只投影了「今天的落点」（一个字符串），**丢掉了生效日** ⇒
运营看不到「这个货是什么时候挂到这个款上的」「换过几次款」，
审计信息只存在于表里。

派生关系（谁引用谁）
--------------------
* ``backend/domains/business/routers/product_center.py`` 的 SKU 列表
  → 用 :func:`project_current_binding`；
* 路由的恢复端点（``restore_spu`` / ``restore_sku``）
  → 用 :func:`archived_binding_condition`（**只**复活 ``inactive``）；
* 四个业务服务（finance / clearance / feishu_projection / price_adjust_notify）
  与种子脚本 → 用 :func:`current_binding_condition`；
* ORM 约束 ``chk_bridge_spu_sku_binding_status``
  与迁移 ``current_migrations/versions/20261228_bridge_spu_sku_binding_status_constraint.py``
  → 用 :func:`render_binding_status_constraint`；
* 响应模型 ``SkuItem.spu_effective_from`` → 本文件定义的投影字段；
* 守护测试 ``backend/tests/test_product_center_binding_projection.py``
  与 ``backend/tests/test_product_center_binding_write_path_contract.py``
  断言「投影口径只有一处定义」。

⚠️ **不要在本文件之外再手抄「当前有效」的判定条件**。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 判定口径（唯一定义处）
# ---------------------------------------------------------------------------

#: 归属关系处于「当前有效」时的状态值。
CURRENT_BINDING_STATUS = "active"

#: 归属关系**被软删封存**时的状态值。
#:
#: * 款被软删 ⇒ 它的归属被封存（``effective_to`` 落日期）；
#: * ⇒ **可复活**：恢复款时，会复活最早的一条被封存的归属。
INACTIVE_BINDING_STATUS = "inactive"

#: 归属关系**被换款归档**时的状态值。
#:
#: * 货从款 A 换到款 B ⇒ A 的那条归属归档（``effective_to`` 落日期）；
#: * ⇒ **不可复活**：它是「这个货换过款」的追溯证据，
#:   复活它等于把历史改回去（也会把货挂回一个可能已经下线的款）。
HISTORICAL_BINDING_STATUS = "historical"


#: **归属状态的全集** —— 本文件唯一的取值域声明。
#:
#: ⚠️ 三个值语义**各不相同**，不可合并：
#:    * ``active``    —— 当前有效；
#:    * ``inactive``  —— 被软删封存（可复活）；
#:    * ``historical`` —— 被换款归档（历史证据，不可复活）。
BINDING_STATUSES: frozenset[str] = frozenset(
    {
        CURRENT_BINDING_STATUS,
        INACTIVE_BINDING_STATUS,
        HISTORICAL_BINDING_STATUS,
    }
)


#: 「什么关系算**当前有效**」的判定口径（写在这里，免得各处口头相传）。
#:
#: * ``binding_status == 'active'`` —— 不是已归档 / 已失效的那一条；
#: * ``effective_to IS NULL``       —— 没有到期日。
CURRENT_BINDING_CONDITION_DESCRIPTION = (
    "binding_status == 'active' AND effective_to IS NULL"
)


def render_binding_status_constraint() -> str:
    """把 :data:`BINDING_STATUSES` 渲染成 ``binding_status`` 取值域的 ``CHECK`` 表达式。

    ⚠️ 渲染成**有序**（排序后）⇒ 同一份状态集合永远渲染出同一串 SQL
    ⇒ 迁移比对（迁移前后约束定义一致）可以按字符串比。
    """
    values = sorted(BINDING_STATUSES)
    quoted = ", ".join("'%s'" % value for value in values)
    return "binding_status IN (%s)" % quoted


def render_current_binding_index_predicate() -> str:
    """「当前归属唯一」的部分索引谓词（SQL 文本）。

    ORM 的 ``uq_bridge_spu_sku_current`` 用它 ⇒ **一个 SKU 只有一条当前归属**
    这条规则也只在真源里定义一次。

    ⚠️ 与 :data:`CURRENT_BINDING_CONDITION_DESCRIPTION` 是同一口径的两种写法
    （一处写给人看，一处写给索引用）⇒ 不会漂移。
    """
    return "effective_to IS NULL AND binding_status = '%s'" % CURRENT_BINDING_STATUS


def current_binding_condition() -> tuple:
    """「当前有效」的**唯一** SQL 判定条件。

    返回 SQLAlchemy 条件元组 ⇒ 直接摊进 ``where(*current_binding_condition())``，
    各调用点**不可能**各写一份而漂移。

    ⚠️ 延迟 import ORM —— 真源模块本身不依赖 ``modules.core.db``，
    避免 ``modules`` ↔ ``backend`` 的循环导入。
    """
    from modules.core.db import BridgeSpuSku

    return (
        BridgeSpuSku.binding_status == CURRENT_BINDING_STATUS,
        BridgeSpuSku.effective_to.is_(None),
    )


def archived_binding_condition() -> tuple:
    """「被软删封存（**可复活**）」的 SQL 判定条件。

    ⚠️ 只包含 :data:`INACTIVE_BINDING_STATUS` —— **不含**
    :data:`HISTORICAL_BINDING_STATUS`：换款归档是历史证据，
    复活它等于把历史改回去。
    """
    from modules.core.db import BridgeSpuSku

    return (BridgeSpuSku.binding_status == INACTIVE_BINDING_STATUS,)


def is_current_binding(binding) -> bool:
    """这条归属关系是不是**当前**的那一条。

    与 :data:`CURRENT_BINDING_CONDITION_DESCRIPTION` 是同一口径的两种写法
    （一处写给人看，一处写给代码跑）⇒ 不会漂移。
    """
    if binding is None:
        return False
    if getattr(binding, "binding_status", None) != CURRENT_BINDING_STATUS:
        return False
    return getattr(binding, "effective_to", None) is None


def project_current_binding(binding) -> dict:
    """把归属关系投影成 SKU 行上的字段。

    ⚠️ **必须同时带上生效日** —— 只给一个 SPU 编码，就把
    「一段有时效的关联」压扁成了「一个字段」，
    运营再也看不到这个货是什么时候挂到这个款上的。

    历史关系（已归档 / 已失效 / 已到期）**不投影** ——
    它们属于追溯，不属于「当前归属」。

    :param binding: ``BridgeSpuSku`` 行，或 None（该 SKU 没有当前归属）
    :return: ``{"spu": str | None, "spu_effective_from": date | None}``
    """
    if not is_current_binding(binding):
        return {"spu": None, "spu_effective_from": None}
    return {
        "spu": binding.spu,
        "spu_effective_from": binding.effective_from,
    }
