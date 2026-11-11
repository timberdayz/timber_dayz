from __future__ import annotations

"""
Collection task status SSOT.

Rationale:
- Avoid duplicated hard-coded status strings across routers/executor/services.
- Keep semantics consistent for API responses, DB persistence, and WS events.

⚠️ **本文件是采集任务状态的唯一定义处**（律 1「真源只能有一个，而且必须写在纸上」）。

历史事故（2026-11-11）
--------------------
``public.task_center_tasks`` 的 ``CHECK`` 约束 ``chk_task_center_tasks_status``
里手抄了一份状态清单，**漏掉了** ``verification_required`` /
``verification_submitted`` / ``manual_intervention_required`` 三个状态
⇒ 采集走到「等人工处理」时，写任务中心被 PostgreSQL 直接拒绝
⇒ 上层兜底把真实原因（「平台要求滑块验证码」）换成了
   ``This Session's transaction has been rolled back...``
⇒ 8 家店铺的失败原因不可读，且前端的人工处理入口拿不到正确状态。

根因**不是选错了真源**，而是「真源被复制成了 6 份，其中一份漂移了」。
⇒ 修法不是再补一次手抄，而是：**所有需要状态清单的地方都从本文件派生**。

派生关系（谁引用谁）
--------------------
* ``modules/core/db/schema_parts/collection.py`` 的 ``CheckConstraint``
  → 用 :data:`TASK_CENTER_WRITABLE_STATUSES` 渲染；
* ``backend/domains/collection/routers/collection_schedule.py``
  的 ``ACTIVE_COLLECTION_TASK_STATUSES`` → 用 :data:`ACTIVE_STATUSES`；
* ``backend/services/collection_config_run_service.py``
  的 ``RECOVERABLE_TASK_STATUSES`` → 用 :data:`ACTIVE_STATUSES`；
* ``backend/domains/collection/routers/collection_tasks.py``
  的 ``_collection_status_to_task_center`` → 用 :func:`to_task_center_status`；
* 守护测试 ``backend/tests/test_collection_task_status_ssot_contract.py``
  断言「DB 约束里的集合 == 本文件的集合」——改一处必须红。

⚠️ **不要在本文件之外再手抄状态清单**。要改状态，改这里，
让守护测试逼着所有派生点跟上。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionTaskStatus:
    # Lifecycle
    PENDING: str = "pending"
    QUEUED: str = "queued"
    RUNNING: str = "running"

    # Terminal
    COMPLETED: str = "completed"
    PARTIAL_SUCCESS: str = "partial_success"
    FAILED: str = "failed"
    CANCELLED: str = "cancelled"

    # 服务重启回收（``backend/services/task_service.py::mark_interrupted_tasks``）
    # 写进 ``core.collection_tasks`` 的状态 —— 采集侧真实存在的终态。
    INTERRUPTED: str = "interrupted"

    # Verification / pauses
    VERIFICATION_REQUIRED: str = "verification_required"
    VERIFICATION_SUBMITTED: str = "verification_submitted"
    MANUAL_INTERVENTION_REQUIRED: str = "manual_intervention_required"

    # Legacy / ambiguous (kept for compatibility; avoid introducing new usages)
    PAUSED: str = "paused"


STATUS = CollectionTaskStatus()

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.COMPLETED,
        STATUS.PARTIAL_SUCCESS,
        STATUS.FAILED,
        STATUS.CANCELLED,
        STATUS.INTERRUPTED,
    }
)

ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.PENDING,
        STATUS.QUEUED,
        STATUS.RUNNING,
        STATUS.VERIFICATION_REQUIRED,
        STATUS.VERIFICATION_SUBMITTED,
        STATUS.MANUAL_INTERVENTION_REQUIRED,
        STATUS.PAUSED,  # legacy
    }
)

PAUSE_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.VERIFICATION_REQUIRED,
        STATUS.MANUAL_INTERVENTION_REQUIRED,
        STATUS.PAUSED,  # legacy
    }
)


# ---------------------------------------------------------------------------
# 状态全集（唯一定义处）
# ---------------------------------------------------------------------------

#: **采集任务的全部状态** —— 本文件唯一的状态全集声明。
#:
#: ⚠️ 这不是「某处用到的子集」，而是**这个领域里存在的全部状态**。
#:    任何地方需要「有哪些状态」，都从这里派生。
ALL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS.PENDING,
        STATUS.QUEUED,
        STATUS.RUNNING,
        STATUS.COMPLETED,
        STATUS.PARTIAL_SUCCESS,
        STATUS.FAILED,
        STATUS.CANCELLED,
        STATUS.INTERRUPTED,
        STATUS.VERIFICATION_REQUIRED,
        STATUS.VERIFICATION_SUBMITTED,
        STATUS.MANUAL_INTERVENTION_REQUIRED,
        STATUS.PAUSED,
    }
)


# ---------------------------------------------------------------------------
# 任务中心（``public.task_center_tasks``）可写状态集合
# ---------------------------------------------------------------------------

#: 任务中心**自己**的、采集侧不存在的状态。
#:
#: ⚠️ 任务中心是**跨领域**的任务台账（采集 / 云同步 / 数据入库都往里投影），
#:    所以它有一小批**采集侧不存在的**状态。
#:    ``interrupted`` **不在这里** —— 它是采集侧真实存在的状态
#:    （服务重启回收时写入 ``core.collection_tasks``）⇒ 已由
#:    :data:`ALL_STATUSES` 覆盖。
TASK_CENTER_OWN_STATUSES: frozenset[str] = frozenset(
    {
        "retry_waiting",
    }
)

#: **可以直接写进任务中心的状态全集** —— DB 的 ``CHECK`` 约束由它渲染。
#:
#: ⚠️ 这就是 2026-11-11 那个约束漏掉的东西：原先的约束是**手抄**的
#:    10 个值，漏了 ``verification_required`` / ``verification_submitted`` /
#:    ``manual_intervention_required`` ⇒ 写入被 PostgreSQL 拒绝。
#:
#:    语义:
#:    * 采集的**全部**状态都能写进去（不丢语义 —— 前端要区分
#:      「等验证码」与「等人工处理」）；
#:    * 加上任务中心**自己**的状态（``retry_waiting``）。
TASK_CENTER_WRITABLE_STATUSES: frozenset[str] = frozenset(
    set(ALL_STATUSES) | set(TASK_CENTER_OWN_STATUSES)
)


def render_task_center_status_constraint() -> str:
    """把 :data:`TASK_CENTER_WRITABLE_STATUSES` 渲染成 SQL ``CHECK`` 表达式。

    ORM 约束与迁移脚本**都调它** ⇒ 不可能在其中一处漏状态。

    ⚠️ 渲染成**有序**（排序后）⇒ 同一份状态集合永远渲染出同一串 SQL
    ⇒ 迁移比对（迁移前后约束定义一致）可以按字符串比。
    """
    values = sorted(TASK_CENTER_WRITABLE_STATUSES)
    quoted = ", ".join("'%s'" % value for value in values)
    return "status IN (%s)" % quoted


def to_task_center_status(status: str | None) -> str | None:
    """采集状态 → 任务中心状态。

    默认**原样透传**（采集的每个状态都在任务中心可写集合里）。

    唯一的历史例外：``verification_required`` → ``paused``、
    ``verification_submitted`` → ``running``（见
    ``backend/domains/collection/routers/collection_tasks.py``
    的 :func:`_collection_status_to_task_center`）。

    ⚠️ 保留这个例外是因为**消费方在读**：任务中心的历史行里
    ``verification_required`` 落的就是 ``paused``，突然改口径会让
    「等验证码的任务」在任务中心列表里消失。
    """
    if status is None:
        return None
    return {
        STATUS.VERIFICATION_REQUIRED: STATUS.PAUSED,
        STATUS.VERIFICATION_SUBMITTED: STATUS.RUNNING,
    }.get(status, status)


def is_terminal(status: str | None) -> bool:
    return str(status or "").strip() in TERMINAL_STATUSES


def is_pause(status: str | None) -> bool:
    return str(status or "").strip() in PAUSE_STATUSES
