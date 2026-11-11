"""任务中心状态约束**对齐真源**（律 1「真源只能有一个，而且必须写在纸上」）。

事故背景（2026-11-11）
----------------------
``public.task_center_tasks`` 的 ``CHECK`` 约束 ``chk_task_center_tasks_status``
里**手抄**了一份状态清单，**漏掉了** ``verification_required`` /
``verification_submitted`` / ``manual_intervention_required``。

⇒ 采集走到「等人工处理」时（``_on_verification_required`` → 写任务中心）
   被 PostgreSQL 直接拒绝（``CheckViolationError``）
⇒ SQLAlchemy 的 session 事务被回滚 ⇒ 上层兜底捕获到的异常变成
   ``This Session's transaction has been rolled back...``
⇒ **真实原因**（「平台要求滑块验证码，等人工处理」）被技术噪音覆盖
⇒ 8 家店铺的失败原因不可读；前端的人工处理入口拿不到正确状态。

为什么**不是**「直接加一条迁移把这三个值补进去」
----------------------------------------------------
那只是把**第 6 份手抄**再补一次 —— 下次真源加状态时它照样漂移。

根因是「真源被复制成 6 份，其中一份漂移」。⇒ 本迁移做两件事：

1. **约束表达式从真源渲染**（``render_task_center_status_constraint()``）
   —— 迁移里**不写死**状态清单 ⇒ 真源改了，迁移重新生成就是对的；
2. **ORM 也改成从真源渲染**
   （``modules/core/db/schema_parts/collection.py``）。

⇒ 真源 ``backend/services/collection_task_status.py`` 是唯一定义处；
   守护测试 ``backend/tests/test_collection_task_status_ssot_contract.py``
   断言「ORM 约束 == 真源集合 == 迁移渲染结果」。

存量数据
--------
约束放宽**只会**让更多状态可写，不会让已有行失效
⇒ 不需要改任何历史行（符合「只保未来、历史不修」）。

但仍要**校验**存量行都满足新约束 —— 若有行落在集合外（理论上不可能，
因为旧约束更严），迁移必须**报错回滚**而不是悄悄放过。

回滚
----
``downgrade`` 把约束恢复成**迁移前的旧定义**（旧集合手抄在迁移里）——
⚠️ 旧集合更严 ⇒ 若回滚时表里已有 ``verification_required`` 等新状态行，
``ALTER TABLE ... ADD CONSTRAINT`` 会失败 ⇒ **fail-closed**，不丢数据。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261226_task_center_status_constraint"
down_revision = "current_schema_20261225_rebuild_identity_candidates_copy"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 约束名。
CONSTRAINT_NAME = "chk_task_center_tasks_status"

#: 约束所在的表。
#:
#: ⚠️ ``op.drop_constraint(name, table_name, type_=...)`` 的第二个参数是
#:    **表名**（不是 schema）—— 传 schema 会生成
#:    ``ALTER TABLE public DROP CONSTRAINT ...`` ⇒ 报
#:    ``relation "public" does not exist``。
#:    表本身在 ``public`` schema ⇒ 用 ``schema=`` 显式指定。
TABLE_NAME = "task_center_tasks"
TABLE_SCHEMA = "public"

#: 迁移前（生产现存）的约束表达式 —— 迁移前是**手抄**的 10 个状态,
#: 漏了 ``verification_required`` / ``verification_submitted`` /
#: ``manual_intervention_required``。
#:
#: ⚠️ 只用于 **downgrade 恢复** 与「迁移前现状核对」——
#:    新的约束表达式**从真源渲染**, 不在这里写死。
LEGACY_CONSTRAINT_EXPRESSION = (
    "status IN ('pending', 'queued', 'running', 'paused', 'retry_waiting', "
    "'partial_success', 'completed', 'failed', 'cancelled', 'interrupted')"
)


def _render_current_constraint() -> str:
    """从**真源**渲染当前应有的约束表达式。

    真源在 ``backend/services/collection_task_status.py``
    ⇒ 状态集合只在那一处定义（律 1）。
    """
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.collection_task_status import (
        render_task_center_status_constraint,
    )

    return render_task_center_status_constraint()


def _read_constraint_expression(connection) -> str | None:
    """读出数据库里**当前**的约束定义（规范化成 SQLAlchemy 的 text 形态）。

    PostgreSQL 会把 ``status IN (...)`` 归一化成
    ``status = ANY (ARRAY[...])`` ⇒ 直接比对字符串会失败，
    所以这里比对的是**集合**（从定义文本里抽出所有引号里的值）。
    """
    from sqlalchemy import text

    row = connection.execute(
        text(
            """
            SELECT pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE c.conname = :name
              AND n.nspname = 'public'
              AND t.relname = 'task_center_tasks'
            """
        ),
        {"name": CONSTRAINT_NAME},
    ).fetchone()
    return row[0] if row else None


def _extract_status_values(definition: str | None) -> set[str]:
    """从约束定义文本里抽出全部状态值。

    两种形态都要吃:
    * 手写形态: ``status IN ('a', 'b')``
    * PostgreSQL 归一化形态: ``status = ANY (ARRAY['a'::character varying, ...])``
    """
    import re

    if not definition:
        return set()
    return set(re.findall(r"'([^']+)'", definition))


def upgrade() -> None:
    """放宽约束：允许写入**全部**采集状态。

    ⚠️ 放宽方向 ⇒ 存量行必然仍满足新约束 ⇒ **不需要**改任何历史行。
    """
    connection = op.get_bind()

    # 迁移前核对：现状与「旧手抄版」一致（说明没有第三方改过这个约束）。
    before_definition = _read_constraint_expression(connection)
    before_values = _extract_status_values(before_definition)
    legacy_values = _extract_status_values(LEGACY_CONSTRAINT_EXPRESSION)

    if before_values and before_values != legacy_values:
        raise RuntimeError(
            "chk_task_center_tasks_status 的迁移前定义与预期不符 —— "
            "可能已被手工改过。拒绝盲目覆盖。\n"
            "预期: %s\n实际: %s" % (sorted(legacy_values), sorted(before_values))
        )

    # 存量行校验：新约束更宽 ⇒ 理论上不可能失败；但仍显式校验并 fail-closed。
    target_expression = _render_current_constraint()
    target_values = _extract_status_values(target_expression)
    invalid_rows = connection.execute(
        sa.text(
            """
            SELECT status, count(*) AS cnt
            FROM public.task_center_tasks
            GROUP BY status
            """
        )
    ).fetchall()
    offenders = [
        (row[0], row[1]) for row in invalid_rows if row[0] not in target_values
    ]
    if offenders:
        raise RuntimeError(
            "task_center_tasks 存在落在目标状态集合之外的行, 拒绝继续: %s" % offenders
        )

    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check", schema=TABLE_SCHEMA)
    op.create_check_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        target_expression,
        schema=TABLE_SCHEMA,
    )


def downgrade() -> None:
    """恢复迁移前的（更严的）约束。

    ⚠️ 若表里已有新状态行（``verification_required`` 等），
    ``ADD CONSTRAINT`` 会**失败** ⇒ fail-closed，不丢数据。
    """
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check", schema=TABLE_SCHEMA)
    op.create_check_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        LEGACY_CONSTRAINT_EXPRESSION,
        schema=TABLE_SCHEMA,
    )
