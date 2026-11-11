"""采集任务状态 **SSOT 守卫**（律 1「真源只能有一个，而且必须写在纸上」）。

事故背景（2026-11-11）
----------------------
``public.task_center_tasks`` 的 ``CHECK`` 约束 ``chk_task_center_tasks_status``
里**手抄**了一份状态清单，**漏掉了** ``verification_required`` /
``verification_submitted`` / ``manual_intervention_required``。

⇒ 采集走到「等人工处理」时，写任务中心被 PostgreSQL 直接拒绝
   （``CheckViolationError``）⇒ 上层兜底把真实原因
   （「平台要求滑块验证码，等人工处理」）换成了
   ``This Session's transaction has been rolled back...``
⇒ 8 家店铺的失败原因不可读；前端的人工处理入口拿不到正确状态。

根因**不是选错了真源**，而是「真源被复制成了 6 份，其中一份漂移了」：
真源 ``backend/services/collection_task_status.py`` 只定义了状态的**分组**
（终态 / 活跃 / 暂停），**没有定义**「任务中心能写哪些状态」。

⇒ 本守卫测试断言：**所有需要状态清单的地方都从真源派生**，
   任何一处手抄 ⇒ 本文件必须红。

被守护的派生点
--------------
1. ORM 的 ``CHECK`` 约束（``modules/core/db/schema_parts/collection.py``）
2. ``backend/services/collection_config_run_service.py`` 的两个集合
3. ``backend/domains/collection/routers/collection_schedule.py`` 的集合
4. ``backend/domains/collection/routers/collection_tasks.py`` 的状态映射
5. 前端两个视图的活跃状态清单（跨语言 ⇒ 用「解析前端数组再比对」的方式）
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.services.collection_task_status import (
    ACTIVE_STATUSES,
    ALL_STATUSES,
    STATUS,
    TASK_CENTER_OWN_STATUSES,
    TASK_CENTER_WRITABLE_STATUSES,
    TERMINAL_STATUSES,
    render_task_center_status_constraint,
    to_task_center_status,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLLECTION_TASKS_VIEW = (
    PROJECT_ROOT
    / "frontend/src/domains/collection/views/collection/CollectionTasks.vue"
)
COLLECTION_CONFIG_VIEW = (
    PROJECT_ROOT
    / "frontend/src/domains/collection/views/collection/CollectionConfig.vue"
)


def _parse_string_array(text: str, prefix: str, label: str) -> list:
    assert prefix in text, f"{label} definition not found"
    remainder = text.split(prefix, 1)[1]
    start = remainder.index("[")
    end = remainder.index("]", start)
    body = remainder[start + 1 : end]
    return [item.strip().strip("'\"") for item in body.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# ① 真源自身
# ---------------------------------------------------------------------------


def test_all_statuses_contains_every_declared_status():
    """``ALL_STATUSES`` 必须覆盖真源里声明的每一个状态。"""
    declared = {
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
    missing = declared - set(ALL_STATUSES)

    assert not missing, f"真源声明了但 ALL_STATUSES 漏掉的状态: {sorted(missing)}"


def test_status_groups_are_subsets_of_all_statuses():
    """终态 / 活跃 / 暂停三个分组都必须是全集的子集。"""
    all_statuses = set(ALL_STATUSES)

    assert set(TERMINAL_STATUSES) <= all_statuses, "终态集合含全集之外的状态"
    assert set(ACTIVE_STATUSES) <= all_statuses, "活跃集合含全集之外的状态"


def test_interrupted_is_a_collection_terminal_status():
    """``interrupted`` 由服务重启回收写入 ``core.collection_tasks`` ⇒ 必须成终态。

    这是真源的**第三个缺口**：原先 ``ALL_STATUSES`` / ``TERMINAL_STATUSES``
    都没它，但 ``backend/services/task_service.py::mark_interrupted_tasks``
    真的在写它 ⇒ 状态清单与实际写入不一致。
    """
    assert STATUS.INTERRUPTED in ALL_STATUSES, "interrupted 必须属于状态全集"
    assert STATUS.INTERRUPTED in TERMINAL_STATUSES, "interrupted 必须是终态"
    assert STATUS.INTERRUPTED not in ACTIVE_STATUSES, "interrupted 不该是活跃态"


def test_task_center_writable_set_covers_all_collection_statuses():
    """任务中心必须能写下**每一个**采集状态 —— 少一个就是一次写入被拒。"""
    writable = set(TASK_CENTER_WRITABLE_STATUSES)

    missing = set(ALL_STATUSES) - writable
    assert (
        not missing
    ), f"任务中心约束缺这些采集状态（写入会被 PostgreSQL 拒）: {sorted(missing)}"


def test_task_center_writable_set_includes_retry_waiting():
    """``retry_waiting`` 是任务中心自己的状态（云同步侧在用）⇒ 必须可写。"""
    writable = set(TASK_CENTER_WRITABLE_STATUSES)

    assert "retry_waiting" in writable
    assert "retry_waiting" in set(TASK_CENTER_OWN_STATUSES)


def test_rendered_constraint_contains_every_writable_status():
    """渲染出来的 SQL 表达式必须逐个包含可写状态。"""
    rendered = render_task_center_status_constraint()

    missing = [
        value
        for value in sorted(TASK_CENTER_WRITABLE_STATUSES)
        if "'%s'" % value not in rendered
    ]
    assert not missing, f"渲染的约束漏掉状态: {missing}"


def test_rendered_constraint_is_deterministic():
    """同一份状态集合必须永远渲染出同一串 SQL ⇒ 迁移可按字符串比对。"""
    first = render_task_center_status_constraint()
    second = render_task_center_status_constraint()

    assert first == second


# ---------------------------------------------------------------------------
# ② ORM 派生点
# ---------------------------------------------------------------------------


def test_orm_task_center_constraint_is_rendered_from_ssot():
    """ORM 的 ``CHECK`` 约束必须**由真源渲染**, 不是手抄。"""
    schema_source = (
        PROJECT_ROOT / "modules/core/db/schema_parts/collection.py"
    ).read_text(encoding="utf-8")

    assert (
        "render_task_center_status_constraint()" in schema_source
    ), "ORM 约束必须调用真源的渲染函数, 不能手抄状态清单"

    # 只盯着**任务中心那张表**的约束块 —— 同一文件里还有别的领域的
    # 状态约束(员工任务 / 刷新队列), 它们各有各的口径, 不在本守卫范围内。
    task_center_block = schema_source.split("class TaskCenterTask(Base)", 1)[1].split(
        "class TaskCenterLog(Base)", 1
    )[0]
    hand_copied = re.search(
        r"status\s+IN\s*\(\s*'pending'", task_center_block, re.IGNORECASE
    )
    assert hand_copied is None, "任务中心的 ORM 约束里仍存在手抄的状态清单"


def test_orm_constraint_matches_ssot_at_runtime():
    """ORM 实际生效的约束表达式必须与真源一致。"""
    from modules.core.db.schema_parts.collection import TaskCenterTask

    constraint = next(
        item
        for item in TaskCenterTask.__table__.constraints
        if getattr(item, "name", None) == "chk_task_center_tasks_status"
    )
    rendered = str(constraint.sqltext)

    for value in sorted(TASK_CENTER_WRITABLE_STATUSES):
        assert "'%s'" % value in rendered, f"ORM 约束缺状态: {value}"


# ---------------------------------------------------------------------------
# ③ 服务层派生点
# ---------------------------------------------------------------------------


def test_config_run_service_derives_status_sets_from_ssot():
    """``collection_config_run_service.py`` 的集合必须引用真源, 不能手抄。"""
    source = (
        PROJECT_ROOT / "backend/services/collection_config_run_service.py"
    ).read_text(encoding="utf-8")

    assert (
        "from backend.services.collection_task_status import" in source
    ), "collection_config_run_service 必须从真源导入状态"
    assert "TERMINAL_TASK_STATUSES = set(TERMINAL_STATUSES)" in source
    assert "RECOVERABLE_TASK_STATUSES = set(ACTIVE_STATUSES)" in source


def test_config_run_service_recoverable_set_equals_active_statuses():
    """可恢复集合必须**等于**真源的活跃状态集合。"""
    from backend.services.collection_config_run_service import (
        RECOVERABLE_TASK_STATUSES,
    )

    assert set(RECOVERABLE_TASK_STATUSES) == set(ACTIVE_STATUSES)


def test_config_run_service_terminal_set_equals_ssot_terminal():
    """终态集合必须**等于**真源的终态集合。"""
    from backend.services.collection_config_run_service import (
        TERMINAL_TASK_STATUSES,
    )

    assert set(TERMINAL_TASK_STATUSES) == set(TERMINAL_STATUSES)


def test_collection_schedule_derives_active_statuses_from_ssot():
    """``collection_schedule.py`` 的活跃状态集合必须引用真源。"""
    source = (
        PROJECT_ROOT / "backend/domains/collection/routers/collection_schedule.py"
    ).read_text(encoding="utf-8")

    assert (
        "from backend.services.collection_task_status import ACTIVE_STATUSES" in source
    ), "collection_schedule 必须从真源导入 ACTIVE_STATUSES"
    assert "ACTIVE_COLLECTION_TASK_STATUSES = set(ACTIVE_STATUSES)" in source


def test_collection_schedule_active_set_equals_ssot():
    """``collection_schedule`` 的活跃集合必须**等于**真源的活跃集合。"""
    from backend.domains.collection.routers.collection_schedule import (
        ACTIVE_COLLECTION_TASK_STATUSES,
    )

    assert set(ACTIVE_COLLECTION_TASK_STATUSES) == set(ACTIVE_STATUSES)


def test_collection_tasks_status_mapping_uses_ssot():
    """状态映射必须调用真源的映射函数, 不能手抄 dict。"""
    source = (
        PROJECT_ROOT / "backend/domains/collection/routers/collection_tasks.py"
    ).read_text(encoding="utf-8")

    assert (
        "to_task_center_status" in source
    ), "collection_tasks 必须使用真源的状态映射函数"


def test_status_mapping_keeps_historical_verification_semantics():
    """保留历史映射例外：等验证码 → paused，等验证码已提交 → running。

    ⚠️ 这是**有意保留**的：任务中心的历史行里 ``verification_required``
    落的就是 ``paused``；突然改口径会让「等验证码的任务」在任务中心列表里消失。
    """
    assert to_task_center_status(STATUS.VERIFICATION_REQUIRED) == STATUS.PAUSED
    assert to_task_center_status(STATUS.VERIFICATION_SUBMITTED) == STATUS.RUNNING


def test_status_mapping_passes_through_every_other_status():
    """除那两个历史例外，其余状态**原样透传** ⇒ 不丢语义。"""
    for status in sorted(ALL_STATUSES):
        if status in {STATUS.VERIFICATION_REQUIRED, STATUS.VERIFICATION_SUBMITTED}:
            continue
        assert to_task_center_status(status) == status


def test_mapped_status_is_always_writable_to_task_center():
    """映射结果**必须**落在任务中心可写集合里 ⇒ 永远不会写入被拒。"""
    writable = set(TASK_CENTER_WRITABLE_STATUSES)

    for status in sorted(ALL_STATUSES):
        mapped = to_task_center_status(status)
        assert (
            mapped in writable
        ), f"状态 {status} 映射成 {mapped}, 不在任务中心可写集合里"


# ---------------------------------------------------------------------------
# ④ 前端派生点（跨语言 ⇒ 解析前端数组后比对）
# ---------------------------------------------------------------------------


def test_frontend_collection_tasks_active_statuses_match_ssot():
    """前端 ``CollectionTasks.vue`` 的活跃状态清单必须与真源一致。"""
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")
    frontend_statuses = _parse_string_array(
        text, "const ACTIVE_TASK_STATUSES = ", "ACTIVE_TASK_STATUSES"
    )

    # ⚠️ 断言消息必须**提到变量里**，不能写成 `assert cond, ( "..." )`：
    #    black 25.1.0 在 Python 3.11（CI）与 3.13（本机）对这种写法的换行判定不同
    #    ⇒ 同一份代码在两端会被 black 改出不同结果，CI 必判「格式不一致」红。
    drift_message = (
        "前端活跃状态清单与真源漂移了 —— 后端加了状态前端没跟上, "
        "或前端多写了后端不存在的状态"
    )
    assert set(frontend_statuses) == set(ACTIVE_STATUSES), drift_message


def test_frontend_collection_config_active_statuses_match_ssot():
    """前端 ``CollectionConfig.vue`` 的活跃状态清单必须与真源一致。"""
    text = COLLECTION_CONFIG_VIEW.read_text(encoding="utf-8")
    frontend_statuses = _parse_string_array(
        text, "const ACTIVE_TASK_STATUSES = ", "ACTIVE_TASK_STATUSES"
    )

    assert set(frontend_statuses) == set(
        ACTIVE_STATUSES
    ), "前端活跃状态清单与真源漂移了"


def test_frontend_terminal_statuses_cover_ssot_terminal():
    """前端终态清单必须**覆盖**后端真源的终态集合。"""
    text = COLLECTION_TASKS_VIEW.read_text(encoding="utf-8")
    frontend_statuses = _parse_string_array(
        text, "const TERMINAL_STATUSES = ", "TERMINAL_STATUSES"
    )

    missing = set(TERMINAL_STATUSES) - set(frontend_statuses)
    assert not missing, f"前端终态清单缺这些状态: {sorted(missing)}"


# ---------------------------------------------------------------------------
# ⑤ 迁移
# ---------------------------------------------------------------------------

MIGRATION_PATH = (
    PROJECT_ROOT
    / "current_migrations/versions/20261226_task_center_status_constraint.py"
)


def test_migration_exists_and_chains_from_previous_head():
    """迁移必须存在, 且接在上一版 head 之后。"""
    assert MIGRATION_PATH.exists(), "缺任务中心状态约束迁移"

    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert (
        'revision = "current_schema_20261226_task_center_status_constraint"' in source
    )
    assert (
        'down_revision = "current_schema_20261225_rebuild_identity_candidates_copy"'
        in source
    ), "迁移必须接在 20261225 之后"


def test_migration_renders_constraint_from_ssot_not_hardcoded():
    """迁移必须**从真源渲染**约束表达式, 不能写死状态清单。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert (
        "render_task_center_status_constraint" in source
    ), "迁移必须调用真源的渲染函数"
    assert (
        "_render_current_constraint" in source
    ), "迁移必须通过渲染函数取目标约束表达式"


def test_migration_renders_the_same_expression_as_orm():
    """迁移渲染出的表达式必须与 ORM 用的**完全一致** ⇒ 两边不会漂移。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "def _render_current_constraint()" in source
    assert "render_task_center_status_constraint()" in source

    # 真源的渲染函数是唯一来源 ⇒ 两者必然一致。
    from modules.core.db.schema_parts.collection import TaskCenterTask

    constraint = next(
        item
        for item in TaskCenterTask.__table__.constraints
        if getattr(item, "name", None) == "chk_task_center_tasks_status"
    )
    assert str(constraint.sqltext) == render_task_center_status_constraint()
