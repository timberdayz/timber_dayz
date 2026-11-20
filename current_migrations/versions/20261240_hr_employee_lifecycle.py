"""HR 员工生命周期：发钱边界字段 + 工资单作废留痕 + 残留测试账号清理。

背景
----
``a_class.employees.status`` 此前是一个自由字符串，同时兼职三件事：

1. 展示事实 —— 这个人还在不在职
2. 业务开关 —— 这个人能不能发工资
3. 软删除标记 —— 这条档案要不要继续出现在列表里

而「能不能发薪」的真实边界其实是**时间**（这个人最后拿到哪个月的钱），
不是状态。本迁移把「发钱边界」显式落成字段 ``last_payroll_month``，
并把「在职状态」约束成固定词表（``active/probation/leave/inactive``）。

本迁移做四件事
--------------
1. **加字段**（结构层）
   * ``a_class.employees.last_payroll_month VARCHAR(7)`` —— 最后可结算的工资月
     （``None`` = 无上限 / 没有可结算的月份）
   * ``a_class.employees.leave_reason VARCHAR(255)`` —— 离职原因
   * ``a_class.payroll_records.void_reason VARCHAR(255)`` —— 工资单作废原因
   * ``a_class.payroll_records.voided_at TIMESTAMPTZ`` —— 作废时间
   * ``a_class.payroll_records.voided_by BIGINT`` —— 作废操作人
2. **加 CHECK 约束**（结构层）
   ``a_class.employees.status`` 只允许 ``('active','probation','leave','inactive')``。
   ⚠️ **先清洗越界值再加约束** —— 否则历史脏值会让约束建不上。
3. **数据修复**（数据层，**只针对下列具体数据，不泛化**）
4. **清理残留测试账号**（数据层，判据缺一不可）

数据修复明细
------------
* ``EMP260004``（李四）的 4 张工资单（``year_month`` = ``2026-03`` / ``2026-04``
  / ``2026-06`` / ``2026-07``，``status='draft'``）⇒ 置 ``status='void'`` +
  ``void_reason='测试数据，业务确认作废（2026-11-20）'`` + ``voided_at=now()``
  （**行保留**，只是不可再发放 —— 作废是留痕，不是删数据）
* ``EMP260004`` ⇒ ``last_payroll_month = '2026-07'``（依据其最后一张工资单月份）
* ``EMP260002``（张三）⇒ ``status`` 保持 ``'inactive'``，``last_payroll_month``
  **留 NULL**。⚠️ **待业务确认**：他没有工资单，结算月未经业务确认 ——
  **不许猜**（猜一个月份等于凭空给离职员工发一次钱）。
  ⇒ 该员工的离职结算边界目前是「任何月份都不生成」，这是**安全的一侧**。
* ``EMP260010``（曾维剑）、``EMP260011``（文鹏）⇒ ``status`` 由 ``'active'``
  改为 ``'probation'``（业务确认二人为试用员工，试用期不发薪）

清理残留测试账号
----------------
共 **347** 个残留测试账号。判据**缺一不可**（四条全中才清）：

1. ``core.dim_users.status = 'rejected'`` 且 ``is_active = false``
2. ``username`` 命中前缀之一：``ratelimit_`` / ``dup_`` / ``test`` / ``test_``
   / ``test01`` / ``pwd_test_`` / ``pending_login_`` / ``rejected_login_``
   / ``approval_workflow_`` / ``flow_test_`` / ``reset_test_`` /
   ``approve_test_`` / ``reject_test_`` / ``lock_test_``
3. **不存在** ``public.user_sessions`` 记录指向该 ``user_id``（没有活会话）
4. **不存在** ``a_class.employees.user_id`` 指向该 ``user_id``（没有绑定员工）

执行顺序：**前置检查** → **先写留痕**（``core.dim_user_purge_log``）→ 再删
**账号级痕迹表**里这些 ``user_id`` 的行 → **最后**删 ``core.dim_users`` 行。
留痕先写 ⇒ 万一后面任一步失败，也知道清到哪儿了。

⚠️ **账号级痕迹表（实测发现，规格里漏了）**：``public.fact_audit_logs`` 有一条
``action_type='user_registered'``（**注册流程给每个注册用户都写一条**）⇒
生产上这 347 个账号必然各有一条 ⇒ 只删 ``user_approval_logs`` 的话，
``DELETE FROM core.dim_users`` 会直接
``ForeignKeyViolation: fact_audit_logs_user_id_fkey``（本地库已复现）。
⇒ 本迁移在删账号前把**账号级痕迹**（审批日志 / 审计痕迹 / 会话 / 角色绑定）
一起清掉。这些痕迹记的是「这个账号存在过」，不是业务历史；账号身份已经
留在 ``core.dim_user_purge_log`` 里。

⚠️ **业务表不被自动清理**：删账号前会扫一遍所有指向 ``core.dim_users`` 的
``NO ACTION`` 外键（``pg_catalog`` 动态取，不靠硬编码清单）；若**业务表**
（如 ``core.employee_tasks``）还引用着这些
账号 ⇒ **直接报错停下**，并在报错里写清楚是哪张表、还剩多少行 ——
宁可停下来让人判断，也不默默删掉业务数据。

⚠️ **不会误伤正式员工账号**：已实测生产上这 347 个账号**全部**满足以上四条
判据（**0 会话、0 员工绑定**）；而 ``Debug_Fate`` / ``user_XiaoZeng`` 这类正式
员工账号状态为 ``active`` 且用户名不命中任何前缀 ⇒ 第 1、2 条就不成立。

不可逆的部分
------------
``core.dim_users`` 行被**物理删除** ⇒ downgrade **无法**把它们重建回来
（重建等于把脏数据塞回库里，比留着空迁移更糟）。downgrade 只做 schema 层面的
回滚 + 能回滚的数据修复，并写明原因（沿用 ``20261230`` 的做法）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261240_hr_employee_lifecycle"
down_revision = "current_schema_20261239_cost_floor_caliber_closure"
branch_labels = None
depends_on = None


CORE_SCHEMA = "core"
A_CLASS_SCHEMA = "a_class"
PUBLIC_SCHEMA = "public"

EMPLOYEE_TABLE = "employees"
PAYROLL_TABLE = "payroll_records"
PURGE_LOG_TABLE = "dim_user_purge_log"

#: ``a_class.employees.status`` 的 CHECK 约束名。
EMPLOYEE_STATUS_CONSTRAINT = "ck_employees_status_lifecycle"

#: ``status`` 的合法词表（与 ``backend/services/hr_employee_lifecycle.py`` 一致）。
EMPLOYEE_STATUS_VALUES = ("active", "probation", "leave", "inactive")

#: 工资单作废原因（业务确认，2026-11-20）。
VOID_REASON = "测试数据，业务确认作废（2026-11-20）"

#: 本次作废的工资单（``EMP260004`` 的 4 张草稿单）。
VOIDED_PAYROLL_EMPLOYEE_CODE = "EMP260004"
VOIDED_PAYROLL_MONTHS = ("2026-03", "2026-04", "2026-06", "2026-07")

#: ``EMP260004`` 的最后发薪月（依据其最后一张工资单）。
LAST_PAYROLL_MONTH_EMPLOYEE_CODE = "EMP260004"
LAST_PAYROLL_MONTH = "2026-07"

#: ``EMP260002``（张三）—— ``last_payroll_month`` **留 NULL**，待业务确认。
NO_BOUNDARY_EMPLOYEE_CODE = "EMP260002"

#: 业务确认为试用员工（试用期不发薪）的工号。
PROBATION_EMPLOYEE_CODES = ("EMP260010", "EMP260011")

#: 残留测试账号的用户名前缀（命中其一即候选，仍需另外三条判据同时成立）。
RESIDUAL_TEST_ACCOUNT_PREFIXES = (
    "ratelimit_",
    "dup_",
    "test",
    "test_",
    "test01",
    "pwd_test_",
    "pending_login_",
    "rejected_login_",
    "approval_workflow_",
    "flow_test_",
    "reset_test_",
    "approve_test_",
    "reject_test_",
    "lock_test_",
)

#: 留痕表里写的清理原因。
PURGE_REASON = "自动清理：残留测试账号"

#: 账号「痕迹表」—— 删账号之前要一起清掉的**账号级**记录（不是业务记录）。
#:
#: ⚠️ 这些表都有指向 ``core.dim_users`` 的外键（``NO ACTION``）⇒ 不清就会撞外键。
#:
#: ⚠️ **实测（本地库 2026-11-20）**：``public.fact_audit_logs`` 里有一条
#: ``action_type='user_registered'``（注册痕迹）—— **账号注册流程会给每个注册
#: 用户写一条** ⇒ 生产上这 347 个账号**必然**各有一条 ⇒ 只删 ``user_approval_logs``
#: 的话，``DELETE FROM core.dim_users`` 会直接
#: ``ForeignKeyViolation: fact_audit_logs_user_id_fkey``。
#:
#: 这类痕迹不是业务历史（它记的是「这个账号存在过」），账号都没了，
#: 痕迹留着只会变成孤儿行；账号身份已经留在 ``core.dim_user_purge_log`` 里。
ACCOUNT_TRACE_TABLES = (
    # (schema, table, user_id 列)
    (PUBLIC_SCHEMA, "user_approval_logs", "user_id"),  # 审批日志（规格明确要求）
    (PUBLIC_SCHEMA, "fact_audit_logs", "user_id"),  # 注册/操作审计痕迹（实测阻塞项）
    (PUBLIC_SCHEMA, "user_sessions", "user_id"),  # 会话（判据保证为 0，删了更稳）
    (PUBLIC_SCHEMA, "user_roles", "user_id"),  # 角色绑定
)

#: 注册审批模板码 —— 候选账号的注册审批**必须**是这个模板。
REGISTRATION_APPROVAL_TEMPLATE = "user_registration_approval"

#: 「注册审批链」痕迹表 —— 账号注册流程会为每个账号留下这一串记录，
#: 它们指向 ``core.dim_users`` ⇒ 不一起清就会撞外键。
#:
#: ⚠️ **实测（生产 2026-11-20，v7.35.0 首次部署被这条挡住）**：
#: 347 个候选里有 **16 个**（user_id 371~390，全是 ``flow_test_`` /
#: ``approval_workflow_`` / ``ratelimit_test_`` / ``approve_test_`` / ``reject_test_`` /
#: ``pending_login_`` / ``rejected_login_`` / ``lock_test_`` / ``pwd_test_`` /
#: ``dup_user_`` / ``dup_email_`` / ``test_user_`` / ``reset_test_``）**走过注册审批**，
#: 于是留下：
#:
#: * ``public.approval_instances`` —— 该账号自己的注册审批实例
#:   （``template_code='user_registration_approval'``、``business_key='user:<id>'``、
#:   ``status='rejected'``）
#: * ``public.approval_action_logs`` —— 该审批实例上的动作
#:   （它自己的 ``submit`` + **管理员的 ``reject``**；管理员不是候选账号，
#:   但这行挂在候选账号的审批实例上 ⇒ 只按 actor 删会漏）
#: * ``public.approval_steps`` —— 该审批实例的步骤（审批人是管理员）
#: * ``core.employee_tasks`` —— 自动生成的「待审批」待办
#:   （``task_id='approval-task:approval:user_registration_approval:user:<id>:<ts>:1'``，
#:   ``owner_user_id`` = 管理员）
#: * ``core.employee_task_logs`` —— 该待办的创建日志
#:
#: ⇒ 这些行**只**记录「这个账号存在过、注册过、被拒过」，不是业务记录 ⇒ 与账号一起清。
#: ⇒ 但删除必须**精确限定在候选账号自己的注册审批上** ⇒ 删之前逐行核对（见
#:    :func:`_assert_registration_traces_are_account_own`），有任何一行对不上就停下。
REGISTRATION_TRACE_TABLES = (
    (PUBLIC_SCHEMA, "approval_action_logs", "actor_user_id"),
    (PUBLIC_SCHEMA, "approval_instances", "applicant_user_id"),
    (PUBLIC_SCHEMA, "approval_steps", "approver_user_id"),
    (CORE_SCHEMA, "employee_task_logs", "actor_user_id"),
    (CORE_SCHEMA, "employee_tasks", "created_by"),
)


def _has_table(schema: str, table: str) -> bool:
    """表是否已存在（幂等迁移的前提）。"""
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def _has_column(schema: str, table: str, column: str) -> bool:
    """列是否已存在（幂等迁移的前提）。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return column in {
        item["name"] for item in inspector.get_columns(table, schema=schema)
    }


def _has_constraint(schema: str, table: str, name: str) -> bool:
    """CHECK 约束是否存在。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    # ⚠️ SQLAlchemy 的 ``Inspector`` **没有** ``get_constraints``（那是 Django 的 API）
    #    ⇒ CHECK 约束必须走 ``get_check_constraints``。
    return name in {
        item["name"] for item in inspector.get_check_constraints(table, schema=schema)
    }


def _residual_test_account_condition() -> str:
    """构造「残留测试账号」判据 SQL 片段（四条，缺一不可）。

    复用同一段条件 ⇒ 留痕、删审批日志、删账号三步**判据完全一致**，
    不会出现「留痕了但没删」或「删了但没留痕」。
    """
    prefix_like = " OR ".join(
        "u.username LIKE '{}%'".format(prefix.replace("_", r"\_"))
        for prefix in RESIDUAL_TEST_ACCOUNT_PREFIXES
    )
    return (
        "u.status = 'rejected' "
        "AND u.is_active = false "
        f"AND ({prefix_like}) "
        f"AND NOT EXISTS (SELECT 1 FROM {PUBLIC_SCHEMA}.user_sessions s "
        "WHERE s.user_id = u.user_id) "
        f"AND NOT EXISTS (SELECT 1 FROM {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} e "
        "WHERE e.user_id = u.user_id)"
    )


def _candidate_user_ids(bind: sa.Connection, condition: str) -> list[int]:
    """取出命中判据的账号 user_id 列表。"""
    rows = bind.execute(
        sa.text(f"SELECT u.user_id FROM {CORE_SCHEMA}.dim_users u WHERE {condition}")
    ).fetchall()
    return [int(row[0]) for row in rows]


def _blocking_foreign_key_tables(bind: sa.Connection) -> list[tuple[str, str, str]]:
    """找出所有**会阻塞删账号**的外键表（``NO ACTION`` / ``RESTRICT``）。

    用 ``pg_catalog`` 动态取 ⇒ 新增外键时不需要改这份清单。
    """
    rows = bind.execute(
        sa.text(
            "SELECT n.nspname, c.relname, a.attname "
            "FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_class rc ON rc.oid = con.confrelid "
            "JOIN pg_namespace rn ON rn.oid = rc.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid "
            "AND a.attnum = con.conkey[1] "
            "WHERE con.contype = 'f' "
            "AND rn.nspname = :core_schema AND rc.relname = 'dim_users' "
            "AND con.confdeltype IN ('a', 'r')"
        ),
        {"core_schema": CORE_SCHEMA},
    ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


def _assert_no_unexpected_references(
    bind: sa.Connection,
    user_ids: list[int],
    skip_tables: set[tuple[str, str]] | None = None,
) -> None:
    """删账号前的前置检查：确认没有**业务表**还在引用这些账号。

    ⚠️ 账号级痕迹表（:data:`ACCOUNT_TRACE_TABLES`）与注册审批链痕迹表
    （:data:`REGISTRATION_TRACE_TABLES`）会被本迁移一起清掉；
    其它表（业务表）如果还引用着 ⇒ **报错停下**，而不是默默删掉业务数据。

    报清楚是哪张表、还剩多少行 ⇒ 运维能直接处理，不用去猜。

    ``skip_tables`` 传 ``set()`` 时**不跳过任何表** ⇒ 用于「清理完成、准备删账号本体」
    那一刻的终检：那一刻还不该有任何残留引用。
    """
    if not user_ids:
        return
    trace_tables = {(schema, table) for schema, table, _ in ACCOUNT_TRACE_TABLES}
    trace_tables |= {(schema, table) for schema, table, _ in REGISTRATION_TRACE_TABLES}
    if skip_tables is not None:
        trace_tables = set(skip_tables)
    id_list = ", ".join(str(user_id) for user_id in user_ids)
    blockers = []
    for schema, table, column in _blocking_foreign_key_tables(bind):
        if (schema, table) in trace_tables:
            continue
        count = bind.execute(
            sa.text(
                f'SELECT count(*) FROM "{schema}"."{table}" '
                f'WHERE "{column}" IN ({id_list})'
            )
        ).scalar()
        if count:
            blockers.append(f"{schema}.{table}.{column}（{count} 行）")
    if blockers:
        raise RuntimeError(
            "残留测试账号仍被业务表引用，拒绝删除（避免误删业务数据）："
            + "；".join(blockers)
        )


def _assert_registration_traces_are_account_own(
    bind: sa.Connection, user_ids: list[int]
) -> None:
    """确认「注册审批链」里的行确实**只是候选账号自己的注册痕迹**。

    逐行核对，任何一行对不上 ⇒ **直接报错停下**（不猜、不删）：

    * ``public.approval_instances``：``template_code`` 必须是
      ``user_registration_approval``、``business_key`` 必须是 ``user:<该账号 id>``；
    * ``core.employee_tasks``：``task_id`` 必须是
      ``approval-task:approval:user_registration_approval:user:<该账号 id>:<时间戳>:1``。

    ⇒ 这一步是「不误伤业务数据」的**最后一道证明**：证明不了就不删。
    """
    if not user_ids:
        return
    id_list = ", ".join(str(user_id) for user_id in user_ids)

    for row in bind.execute(
        sa.text(
            f"SELECT id, applicant_user_id, template_code, business_key "
            f"FROM {PUBLIC_SCHEMA}.approval_instances "
            f"WHERE applicant_user_id IN ({id_list})"
        )
    ).fetchall():
        instance_id, applicant_user_id, template_code, business_key = row
        if template_code != REGISTRATION_APPROVAL_TEMPLATE:
            raise RuntimeError(
                "注册审批链痕迹核对失败：该账号的审批实例不是「用户注册审批」，"
                f"拒绝删除（实例 id={instance_id}，template_code={template_code}）"
            )
        expected_key = "user:{0}".format(applicant_user_id)
        if business_key != expected_key:
            raise RuntimeError(
                "注册审批链痕迹核对失败：该审批实例的业务键与申请人不匹配，"
                f"拒绝删除（实例 id={instance_id}，business_key={business_key}，"
                f"期望 {expected_key}）"
            )

    for row in bind.execute(
        sa.text(
            f"SELECT task_id, created_by FROM {CORE_SCHEMA}.employee_tasks "
            f"WHERE created_by IN ({id_list})"
        )
    ).fetchall():
        task_id, created_by = row
        expected_prefix = "approval-task:approval:{0}:user:{1}:".format(
            REGISTRATION_APPROVAL_TEMPLATE, created_by
        )
        if not str(task_id).startswith(expected_prefix):
            raise RuntimeError(
                "注册审批链痕迹核对失败：该账号创建的待办不是「它自己的注册审批待办」，"
                f"拒绝删除（task_id={task_id}）"
            )

    # ⚠️ 候选账号若是某个审批的**审批人**（approver_user_id），那一步也是指向它的外键。
    #    只有当这一步属于「它自己的注册审批」时才是痕迹；否则是**别人的业务审批** ⇒ 停下。
    own_instance_ids = {
        int(row[0])
        for row in bind.execute(
            sa.text(
                f"SELECT id FROM {PUBLIC_SCHEMA}.approval_instances "
                f"WHERE applicant_user_id IN ({id_list})"
            )
        ).fetchall()
    }
    for row in bind.execute(
        sa.text(
            f"SELECT id, approver_user_id, approval_pk FROM {PUBLIC_SCHEMA}.approval_steps "
            f"WHERE approver_user_id IN ({id_list})"
        )
    ).fetchall():
        step_id, approver_user_id, approval_pk = row
        if int(approval_pk) not in own_instance_ids:
            raise RuntimeError(
                "注册审批链痕迹核对失败：该账号是**别人**审批的审批人，"
                f"那一步是业务数据，拒绝删除（step id={step_id}，"
                f"approval_pk={approval_pk}）"
            )


def _purge_registration_traces(bind: sa.Connection, user_ids: list[int]) -> None:
    """清掉候选账号**自己的**注册审批链痕迹（按外键依赖顺序，先子后父）。

    顺序（踩错就撞外键）：

    ① ``approval_action_logs``（审批实例上的动作：它自己的 submit + 管理员的 reject）
    ② ``approval_steps``（审批实例的步骤）
    ③ ``approval_instances``（审批实例本体）
    ④ ``employee_task_logs``（待办的日志）
    ⑤ ``employee_task_participants``（待办的参与人，生产实测 0 行，防御性清理）
    ⑥ ``employee_tasks``（待办本体）

    ⚠️ 删除条件都**带上两把钥匙**（actor/created_by 与 approval_pk/task_pk），
    避免「同一行的两个引用键只清了一个」留下残留引用。
    """
    if not user_ids:
        return
    id_list = ", ".join(str(user_id) for user_id in user_ids)

    instance_ids = (
        f"(SELECT id FROM {PUBLIC_SCHEMA}.approval_instances "
        f"WHERE applicant_user_id IN ({id_list}))"
    )
    task_ids = (
        f"(SELECT id FROM {CORE_SCHEMA}.employee_tasks "
        f"WHERE created_by IN ({id_list}))"
    )

    bind.execute(
        sa.text(
            f"DELETE FROM {PUBLIC_SCHEMA}.approval_action_logs "
            f"WHERE approval_pk IN {instance_ids} "
            f"OR actor_user_id IN ({id_list})"
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM {PUBLIC_SCHEMA}.approval_steps "
            f"WHERE approval_pk IN {instance_ids}"
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM {PUBLIC_SCHEMA}.approval_instances "
            f"WHERE applicant_user_id IN ({id_list})"
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM {CORE_SCHEMA}.employee_task_logs "
            f"WHERE task_pk IN {task_ids} "
            f"OR actor_user_id IN ({id_list})"
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM {CORE_SCHEMA}.employee_task_participants "
            f"WHERE task_pk IN {task_ids}"
        )
    )
    bind.execute(
        sa.text(
            f"DELETE FROM {CORE_SCHEMA}.employee_tasks "
            f"WHERE created_by IN ({id_list})"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1) 加字段（结构层）----------------------------------------------------
    if not _has_column(A_CLASS_SCHEMA, EMPLOYEE_TABLE, "last_payroll_month"):
        op.add_column(
            EMPLOYEE_TABLE,
            sa.Column("last_payroll_month", sa.String(7), nullable=True),
            schema=A_CLASS_SCHEMA,
        )
    if not _has_column(A_CLASS_SCHEMA, EMPLOYEE_TABLE, "leave_reason"):
        op.add_column(
            EMPLOYEE_TABLE,
            sa.Column("leave_reason", sa.String(255), nullable=True),
            schema=A_CLASS_SCHEMA,
        )
    if not _has_column(A_CLASS_SCHEMA, PAYROLL_TABLE, "void_reason"):
        op.add_column(
            PAYROLL_TABLE,
            sa.Column("void_reason", sa.String(255), nullable=True),
            schema=A_CLASS_SCHEMA,
        )
    if not _has_column(A_CLASS_SCHEMA, PAYROLL_TABLE, "voided_at"):
        op.add_column(
            PAYROLL_TABLE,
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            schema=A_CLASS_SCHEMA,
        )
    if not _has_column(A_CLASS_SCHEMA, PAYROLL_TABLE, "voided_by"):
        op.add_column(
            PAYROLL_TABLE,
            sa.Column("voided_by", sa.BigInteger, nullable=True),
            schema=A_CLASS_SCHEMA,
        )

    # --- 2) status 词表约束（先清洗越界值，再加约束）--------------------------
    status_values = ", ".join(f"'{value}'" for value in EMPLOYEE_STATUS_VALUES)
    # ⚠️ 先清洗：历史脏值（自由字符串时代留下的）会让约束直接建不上。
    bind.execute(
        sa.text(
            f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} SET status = 'active' "
            f"WHERE status IS NOT NULL AND status NOT IN ({status_values})"
        )
    )
    # ⚠️ 加约束前先删同名旧约束 ⇒ 重复执行安全（幂等）。
    if _has_constraint(A_CLASS_SCHEMA, EMPLOYEE_TABLE, EMPLOYEE_STATUS_CONSTRAINT):
        op.drop_constraint(
            EMPLOYEE_STATUS_CONSTRAINT,
            EMPLOYEE_TABLE,
            schema=A_CLASS_SCHEMA,
            type_="check",
        )
    op.create_check_constraint(
        EMPLOYEE_STATUS_CONSTRAINT,
        EMPLOYEE_TABLE,
        f"status IN ({status_values})",
        schema=A_CLASS_SCHEMA,
    )

    # --- 3) 留痕表（账号清理前先建好）----------------------------------------
    if not _has_table(CORE_SCHEMA, PURGE_LOG_TABLE):
        op.create_table(
            PURGE_LOG_TABLE,
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(255), nullable=True),
            sa.Column("user_id", sa.BigInteger, nullable=True),
            sa.Column("status", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "purged_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("reason", sa.String(255), nullable=True),
            schema=CORE_SCHEMA,
        )

    # --- 4) 数据修复（只针对下列具体数据，不泛化）--------------------------
    # 4.1) EMP260004 的 4 张草稿工资单 ⇒ 作废（行保留，只是不再可发放）
    void_months = ", ".join(f"'{month}'" for month in VOIDED_PAYROLL_MONTHS)
    bind.execute(
        sa.text(
            f"UPDATE {A_CLASS_SCHEMA}.{PAYROLL_TABLE} "
            "SET status = 'void', void_reason = :reason, voided_at = now() "
            "WHERE employee_code = :code "
            "AND status = 'draft' "
            f"AND year_month IN ({void_months})"
        ),
        {"reason": VOID_REASON, "code": VOIDED_PAYROLL_EMPLOYEE_CODE},
    )

    # 4.2) EMP260004 ⇒ 最后发薪月 = 其最后一张工资单月份
    bind.execute(
        sa.text(
            f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} "
            "SET last_payroll_month = :month WHERE employee_code = :code"
        ),
        {"month": LAST_PAYROLL_MONTH, "code": LAST_PAYROLL_MONTH_EMPLOYEE_CODE},
    )

    # 4.3) EMP260002（张三）⇒ status 保持 'inactive'，last_payroll_month 留 NULL。
    #      ⚠️ 待业务确认：他没有工资单 ⇒ 结算月不明 ⇒ **不许猜**。
    #      显式写 NULL 是为了把「不猜」这件事落到代码里（而不是碰巧为空）。
    bind.execute(
        sa.text(
            f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} "
            "SET last_payroll_month = NULL WHERE employee_code = :code"
        ),
        {"code": NO_BOUNDARY_EMPLOYEE_CODE},
    )

    # 4.4) EMP260010 / EMP260011 ⇒ 试用期（试用期不发薪）
    for employee_code in PROBATION_EMPLOYEE_CODES:
        bind.execute(
            sa.text(
                f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} "
                "SET status = 'probation' "
                "WHERE employee_code = :code AND status = 'active'"
            ),
            {"code": employee_code},
        )

    # --- 5) 清理残留测试账号（347 个）----------------------------------------
    condition = _residual_test_account_condition()
    candidate_ids = _candidate_user_ids(bind, condition)

    # 5.1) 前置检查 A：注册审批链里的行必须是候选账号**自己**的注册痕迹。
    #      ⚠️ 证明不了 ⇒ 直接停下（不删任何东西）。
    _assert_registration_traces_are_account_own(bind, candidate_ids)

    # 5.2) 前置检查 B：业务表若还引用着这些账号 ⇒ 报错停下（不默默删业务数据）
    _assert_no_unexpected_references(bind, candidate_ids)

    # 5.3) 先留痕（万一后面失败，也知道清到哪儿了）
    bind.execute(
        sa.text(
            f"INSERT INTO {CORE_SCHEMA}.{PURGE_LOG_TABLE} "
            "(username, user_id, status, created_at, purged_at, reason) "
            "SELECT u.username, u.user_id, u.status, now(), now(), :reason "
            f"FROM {CORE_SCHEMA}.dim_users u WHERE {condition}"
        ),
        {"reason": PURGE_REASON},
    )

    # 5.4) 清「注册审批链」痕迹（先子后父，见 _purge_registration_traces）
    _purge_registration_traces(bind, candidate_ids)

    # 5.5) 再删其余账号级痕迹（它们的 user_id 外键指向 dim_users ⇒ 不先删会撞外键）
    for schema, table, column in ACCOUNT_TRACE_TABLES:
        bind.execute(
            sa.text(
                f'DELETE FROM "{schema}"."{table}" '
                f'WHERE "{column}" IN (SELECT u.user_id '
                f"FROM {CORE_SCHEMA}.dim_users u WHERE {condition})"
            )
        )

    # 5.6) 删账号本体**之前再查一遍**：此刻不该有任何残留引用
    #      （skip_tables=set() ⇒ 一张表都不放过）⇒ 有残留就停下，绝不硬删。
    _assert_no_unexpected_references(bind, candidate_ids, skip_tables=set())

    # 5.7) 最后删账号本体
    bind.execute(sa.text(f"DELETE FROM {CORE_SCHEMA}.dim_users AS u WHERE {condition}"))


def downgrade() -> None:
    bind = op.get_bind()

    # --- 1) 撤掉本次置的数据修复 ---------------------------------------------
    # 1.1) 作废的工资单恢复 draft（只恢复本次作废的那几张：靠 void_reason 精确匹配）
    bind.execute(
        sa.text(
            f"UPDATE {A_CLASS_SCHEMA}.{PAYROLL_TABLE} "
            "SET status = 'draft', void_reason = NULL, voided_at = NULL, "
            "voided_by = NULL "
            "WHERE employee_code = :code AND status = 'void' AND void_reason = :reason"
        ),
        {"reason": VOID_REASON, "code": VOIDED_PAYROLL_EMPLOYEE_CODE},
    )

    # 1.2) 试用员工恢复在职
    for employee_code in PROBATION_EMPLOYEE_CODES:
        bind.execute(
            sa.text(
                f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} "
                "SET status = 'active' "
                "WHERE employee_code = :code AND status = 'probation'"
            ),
            {"code": employee_code},
        )

    # 1.3) 最后发薪月回滚为 NULL（列本来是本次新增的，回滚后整列删除）
    for employee_code in (
        LAST_PAYROLL_MONTH_EMPLOYEE_CODE,
        NO_BOUNDARY_EMPLOYEE_CODE,
    ):
        bind.execute(
            sa.text(
                f"UPDATE {A_CLASS_SCHEMA}.{EMPLOYEE_TABLE} "
                "SET last_payroll_month = NULL WHERE employee_code = :code"
            ),
            {"code": employee_code},
        )

    # --- 2) 删 CHECK 约束 ------------------------------------------------------
    if _has_constraint(A_CLASS_SCHEMA, EMPLOYEE_TABLE, EMPLOYEE_STATUS_CONSTRAINT):
        op.drop_constraint(
            EMPLOYEE_STATUS_CONSTRAINT,
            EMPLOYEE_TABLE,
            schema=A_CLASS_SCHEMA,
            type_="check",
        )

    # --- 3) 删新增列 ----------------------------------------------------------
    # ⚠️ SQLAlchemy 2.x 的 ``op.drop_column`` 签名是 ``(table_name, column_name, schema=...)``
    #    —— 列名是**第二个位置参数**，**不能**再同时传 ``table_name=`` 关键字。
    #    ``op.add_column`` 的签名相反，是 ``(table_name, column, schema=...)``。
    for table_name, column_name in (
        (EMPLOYEE_TABLE, "last_payroll_month"),
        (EMPLOYEE_TABLE, "leave_reason"),
        (PAYROLL_TABLE, "void_reason"),
        (PAYROLL_TABLE, "voided_at"),
        (PAYROLL_TABLE, "voided_by"),
    ):
        if _has_column(A_CLASS_SCHEMA, table_name, column_name):
            op.drop_column(table_name, column_name, schema=A_CLASS_SCHEMA)

    # --- 4) 删留痕表 ----------------------------------------------------------
    # ⚠️ ``core.dim_users`` 里被物理删除的 347 行**无法**重建（那是数据删除，
    #    重建等于把脏数据塞回库里）。真正的回退方式是从备份恢复。
    if _has_table(CORE_SCHEMA, PURGE_LOG_TABLE):
        op.drop_table(PURGE_LOG_TABLE, schema=CORE_SCHEMA)
