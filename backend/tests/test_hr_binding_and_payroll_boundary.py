"""账号 ↔ 员工绑定收口 + 薪资发钱边界 / 作废动作的回归测试。

覆盖三件事：

1. **绑定链路收口** —— 用户侧 ``PUT /api/users/{user_id}`` 与员工侧同一套校验，
   且**绝不静默覆盖**（员工已被别的账号绑定 ⇒ 400 并点名占用者）。
2. **审批即建档** —— ``approve_user(create_employee=True)`` 在同一事务里建档 + 绑定，
   已有档案时**幂等**跳过建档。
3. **薪资发钱边界与作废** —— 离职员工只结算到 ``last_payroll_month``；
   草稿可作废，已确认 / 已发放不可作废；作废后不可编辑 / 确认 / 发放；
   而**确认与发放对离职员工仍然放行**（离职结算是生命线）。

测试风格：``SimpleNamespace`` + 假 session / monkeypatch，**不连真库**。
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.schemas.hr import PayrollManualInputUpdate, PayrollRecordManualUpdate
from modules.core.db import DimRole, DimUser, Employee


def _load_users_admin():
    return importlib.import_module("backend.domains.platform.routers.users_admin")


def _load_hr_salary():
    return importlib.import_module("backend.domains.business.routers.hr_salary")


class _ResultOne:
    """单值查询结果。"""

    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return [self._value] if self._value is not None else []


class _ResultRows:
    """多行查询结果。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _json_body(response):
    return json.loads(response.body.decode("utf-8"))


def _admin_user(user_id: int = 9001):
    """管理员视角的当前登录用户。"""
    return SimpleNamespace(
        user_id=user_id,
        username="admin",
        is_superuser=True,
        roles=[],
    )


def _employee(**overrides):
    """员工档案（字段按 ``hr_employee_lifecycle`` 的口径给全）。"""
    base = dict(
        id=1,
        employee_code="EMP260001",
        name="张三",
        status="active",
        employee_identity_type="employee",
        last_payroll_month=None,
        user_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _payroll_record(**overrides):
    """字段齐全的工资单（``PayrollRecordResponse`` 需要的字段一个不少）。"""
    base = dict(
        id=1,
        employee_code="EMP260001",
        year_month="2026-08",
        base_salary=1000.0,
        position_salary=100.0,
        performance_salary=0.0,
        overtime_pay=0.0,
        commission=0.0,
        allowances=0.0,
        bonus=0.0,
        gross_salary=1100.0,
        social_insurance_personal=0.0,
        housing_fund_personal=0.0,
        income_tax=0.0,
        other_deductions=0.0,
        total_deductions=0.0,
        net_salary=1100.0,
        social_insurance_company=0.0,
        housing_fund_company=0.0,
        total_cost=1100.0,
        status="draft",
        pay_date=None,
        remark=None,
        backfill_source_month=None,
        backfill_note=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        void_reason=None,
        voided_at=None,
        voided_by=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _UsersAdminSession:
    """按实体类型分发查询结果的假 session（不连真库）。"""

    def __init__(self, *, users=None, employees=None):
        self._users = list(users or [])
        self._employees = list(employees or [])
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.rollback = AsyncMock()
        self.added: list = []

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is DimUser:
            return _ResultOne(self._users.pop(0) if self._users else None)
        if entity is Employee:
            return _ResultOne(self._employees.pop(0) if self._employees else None)
        return _ResultOne(None)

    def add(self, obj):
        self.added.append(obj)


class _UnlinkedSession:
    """``GET /api/users/unlinked`` 专用假 session：员工查询与用户列表同序。"""

    def __init__(self, *, users, employee_rows):
        self._users = list(users)
        self._employee_rows = list(employee_rows)

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is DimUser:
            return _ResultRows(self._users)
        if entity is Employee:
            return _ResultOne(self._employee_rows.pop(0))
        return _ResultOne(None)


class _PayrollSession:
    """薪资路由专用假 session：记录每次按实体的查询，便于断言「没查员工」。"""

    def __init__(self, *, payroll_records=None, employees=None, record_by_id=None):
        self._payroll_records = list(payroll_records or [])
        self._employees = list(employees or [])
        self._record_by_id = record_by_id
        self.queried_entities: list = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.rollback = AsyncMock()
        self.added: list = []

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        self.queried_entities.append(entity)
        if entity is not None and entity.__name__ == "PayrollRecord":
            return _ResultOne(
                self._payroll_records.pop(0) if self._payroll_records else None
            )
        if entity is Employee:
            return _ResultOne(self._employees.pop(0))
        return _ResultOne(None)

    async def get(self, entity, primary_key):
        self.queried_entities.append(entity)
        return self._record_by_id

    def add(self, obj):
        self.added.append(obj)


class _MutablePayrollPeriodLockService:
    """放行所有月份可变性校验（只测业务分支，不测锁）。"""

    def __init__(self, _db):
        pass

    async def assert_employee_month_mutable(self, **_kwargs):
        return None

    async def assert_month_mutable(self, **_kwargs):
        return None

    async def assert_salary_effective_date_mutable(self, **_kwargs):
        return None


# ---------------------------------------------------------------------------
# 一、绑定链路收口（users_admin）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_rejects_binding_to_non_active_account(monkeypatch):
    """账号未审批 / 未启用 ⇒ 400，且不动员工的绑定关系。"""
    module = _load_users_admin()
    monkeypatch.setattr(module, "_clear_employee_user_id", AsyncMock())

    user = SimpleNamespace(
        user_id=7,
        username="li",
        email="li@example.com",
        full_name="李四",
        status="pending",
        is_active=False,
        roles=[],
    )
    employee = _employee(id=3, employee_code="EMP260001", status="active")
    db = _UsersAdminSession(users=[user], employees=[employee])

    response = await module.update_user(
        user_id=7,
        user_update=module.UserUpdate(employee_id=3),
        current_user=_admin_user(),
        db=db,
    )

    assert response.status_code == 400
    assert "只能关联已审批且启用的账号" in _json_body(response)["message"]
    assert employee.user_id is None  # 不静默覆盖
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_rejects_binding_departed_employee(monkeypatch):
    """已离职员工不可被新账号关联 ⇒ 400，且不动绑定关系。"""
    module = _load_users_admin()
    monkeypatch.setattr(module, "_clear_employee_user_id", AsyncMock())

    user = SimpleNamespace(
        user_id=7,
        username="li",
        email="li@example.com",
        full_name="李四",
        status="active",
        is_active=True,
        roles=[],
    )
    employee = _employee(
        id=3, employee_code="EMP260004", name="李四", status="inactive"
    )
    db = _UsersAdminSession(users=[user], employees=[employee])

    response = await module.update_user(
        user_id=7,
        user_update=module.UserUpdate(employee_id=3),
        current_user=_admin_user(),
        db=db,
    )

    assert response.status_code == 400
    assert "该员工已离职，不可关联账号" in _json_body(response)["message"]
    assert employee.user_id is None  # 不静默覆盖
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_rejects_employee_already_bound_to_other_account(monkeypatch):
    """员工已被别的账号绑定 ⇒ 400 并点名占用者，**绝不静默抢走**。"""
    module = _load_users_admin()
    monkeypatch.setattr(module, "_clear_employee_user_id", AsyncMock())

    target_user = SimpleNamespace(
        user_id=7,
        username="newaccount",
        email="new@example.com",
        full_name="新账号",
        status="active",
        is_active=True,
        roles=[],
    )
    occupant = SimpleNamespace(
        user_id=30,
        username="zhangsan",
        email="zhangsan@example.com",
        status="active",
        is_active=True,
    )
    employee = _employee(id=3, employee_code="EMP260001", user_id=30)
    db = _UsersAdminSession(
        users=[target_user, occupant],
        employees=[employee],
    )

    response = await module.update_user(
        user_id=7,
        user_update=module.UserUpdate(employee_id=3),
        current_user=_admin_user(),
        db=db,
    )

    assert response.status_code == 400
    message = _json_body(response)["message"]
    assert "该员工已关联账号 zhangsan（用户ID 30）" in message
    assert "请先解除关联或从该账号侧解除" in message
    assert employee.user_id == 30  # 旧账号的绑定关系原封不动
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_binds_employee_when_all_checks_pass(monkeypatch):
    """校验全过 ⇒ 正常绑定（正向路径没被收口改坏）。"""
    module = _load_users_admin()
    clear_mock = AsyncMock()
    monkeypatch.setattr(module, "_clear_employee_user_id", clear_mock)
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    user = SimpleNamespace(
        user_id=7,
        username="li",
        email="li@example.com",
        full_name="李四",
        status="active",
        is_active=True,
        roles=[],
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )
    employee = _employee(id=3, employee_code="EMP260001", status="active")
    db = _UsersAdminSession(users=[user], employees=[employee])

    response = await module.update_user(
        user_id=7,
        user_update=module.UserUpdate(employee_id=3),
        current_user=_admin_user(),
        db=db,
    )

    assert response.id == 7
    assert employee.user_id == 7
    clear_mock.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_user_allows_unbinding_departed_employee(monkeypatch):
    """解除关联**总是允许**：员工已离职也不拦截。"""
    module = _load_users_admin()
    clear_mock = AsyncMock()
    monkeypatch.setattr(module, "_clear_employee_user_id", clear_mock)
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    user = SimpleNamespace(
        user_id=7,
        username="li",
        email="li@example.com",
        full_name="李四",
        status="active",
        is_active=True,
        roles=[],
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )
    db = _UsersAdminSession(users=[user])

    response = await module.update_user(
        user_id=7,
        user_update=module.UserUpdate(employee_id=None),
        current_user=_admin_user(),
        db=db,
    )

    # 成功路径返回 UserResponse（不是错误响应）
    assert response.id == 7
    assert response.employee_id is None
    clear_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unlinked_users_reports_departed_employee_occupancy():
    """账号池额外返回「被已离职员工占用的账号」，并保持既有结构向后兼容。"""
    module = _load_users_admin()

    free_user = SimpleNamespace(user_id=1, username="free", email="free@example.com")
    occupied_user = SimpleNamespace(
        user_id=2, username="occupied", email="occupied@example.com"
    )
    working_user = SimpleNamespace(
        user_id=3, username="working", email="work@example.com"
    )
    departed = _employee(
        id=11, employee_code="EMP260004", name="李四", status="inactive", user_id=2
    )
    working = _employee(
        id=12, employee_code="EMP260001", name="张三", status="active", user_id=3
    )
    db = _UnlinkedSession(
        users=[free_user, occupied_user, working_user],
        employee_rows=[None, departed, working],
    )

    response = await module.get_unlinked_users(current_user=_admin_user(), db=db)

    assert response.status_code == 200
    payload = _json_body(response)
    assert payload["success"] is True

    data = payload["data"]
    assert [item["id"] for item in data] == [1, 2]
    assert data[0]["blocked_by_employee"] is None
    assert data[1]["blocked_by_employee"] == {
        "employee_code": "EMP260004",
        "employee_name": "李四",
        "employee_status": "inactive",
    }
    # 既有字段保持不变（前端老代码仍可用）
    assert data[0]["username"] == "free"
    assert data[0]["email"] == "free@example.com"

    assert payload["occupied_by_departed_employee"] == [
        {
            "id": 2,
            "username": "occupied",
            "email": "occupied@example.com",
            "employee_code": "EMP260004",
            "employee_name": "李四",
        }
    ]


# ---------------------------------------------------------------------------
# 二、审批即建档（approve_user）
# ---------------------------------------------------------------------------


class _ApproveSession:
    """审批场景的假 session：员工查询按「账号已关联的档案」回答。"""

    def __init__(self, *, user, operator_role, existing_employee=None):
        self.user = user
        self.operator_role = operator_role
        self.existing_employee = existing_employee
        self.commit = AsyncMock()
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.rollback = AsyncMock()
        self.added: list = []

    def _employees_by_user(self):
        created = [
            obj
            for obj in self.added
            if isinstance(obj, Employee) and obj.user_id == self.user.user_id
        ]
        if created:
            return created[0]
        return self.existing_employee

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        column = stmt.column_descriptions[0].get("name")
        if entity is DimUser:
            return _ResultOne(self.user)
        if entity is DimRole:
            return _ResultOne(self.operator_role)
        if entity is Employee:
            if column == "employee_code":
                # 工号生成：扫描已有工号
                codes = [
                    obj.employee_code for obj in self.added if isinstance(obj, Employee)
                ]
                if self.existing_employee is not None:
                    codes.append(self.existing_employee.employee_code)
                return _ResultRows(codes)
            return _ResultOne(self._employees_by_user())
        return _ResultOne(None)

    def add(self, obj):
        self.added.append(obj)


def _pending_user(user_id: int = 201):
    return SimpleNamespace(
        user_id=user_id,
        username="new_hire",
        email="new_hire@example.com",
        full_name="新员工",
        status="pending",
        is_active=False,
        approved_at=None,
        approved_by=None,
        roles=[],
    )


def _operator_role():
    return SimpleNamespace(role_id=2, role_name="操作员", role_code="operator")


@pytest.mark.asyncio
async def test_approve_user_creates_employee_profile_and_binds_account(monkeypatch):
    """``create_employee=True`` ⇒ 同一事务里激活账号 + 建档 + 绑定。"""
    module = _load_users_admin()
    audit_calls: list = []

    async def _fake_log_action(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(module.audit_service, "log_action", _fake_log_action)
    monkeypatch.setattr(
        "backend.services.approval_center_service.sync_user_registration_approval_decision",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.routers.notifications.notify_user_approved", AsyncMock()
    )

    user = _pending_user()
    db = _ApproveSession(user=user, operator_role=_operator_role())

    response = await module.approve_user(
        user_id=user.user_id,
        request_body=module.ApproveUserRequest(
            notes="入职",
            create_employee=True,
            employee_department_id=5,
            employee_position_id=9,
            employee_hire_date=__import__("datetime").date(2026, 11, 20),
            employee_status="probation",
        ),
        request=SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "pytest"},
        ),
        current_user=_admin_user(),
        db=db,
    )

    assert response.status_code == 200
    payload = _json_body(response)
    assert payload["success"] is True
    assert payload["data"]["employee_created"] is True

    created = [obj for obj in db.added if isinstance(obj, Employee)]
    assert len(created) == 1
    employee = created[0]
    assert employee.employee_code.startswith("EMP")
    assert employee.name == "新员工"
    assert employee.employee_identity_type == "employee"
    assert employee.status == "probation"
    assert employee.department_id == 5
    assert employee.position_id == 9
    assert employee.user_id == user.user_id
    assert user.status == "active"
    assert user.is_active is True

    assert audit_calls, "审批必须留审计日志"
    assert audit_calls[-1]["details"]["employee_created"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_user_with_create_employee_is_idempotent(monkeypatch):
    """账号已有关联档案 ⇒ 幂等跳过建档，不重复建档、不报错。"""
    module = _load_users_admin()
    audit_calls: list = []

    async def _fake_log_action(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(module.audit_service, "log_action", _fake_log_action)
    monkeypatch.setattr(
        "backend.services.approval_center_service.sync_user_registration_approval_decision",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.routers.notifications.notify_user_approved", AsyncMock()
    )

    user = _pending_user()
    existing = _employee(
        id=31, employee_code="EMP260001", name="新员工", user_id=user.user_id
    )
    db = _ApproveSession(
        user=user, operator_role=_operator_role(), existing_employee=existing
    )

    response = await module.approve_user(
        user_id=user.user_id,
        request_body=module.ApproveUserRequest(create_employee=True),
        request=SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "pytest"},
        ),
        current_user=_admin_user(),
        db=db,
    )

    assert response.status_code == 200
    payload = _json_body(response)
    assert payload["success"] is True
    assert payload["data"]["employee_created"] is False
    assert payload["data"]["employee_code"] == "EMP260001"

    created = [obj for obj in db.added if isinstance(obj, Employee)]
    assert created == [], "已有档案时不得重复建档"
    assert audit_calls[-1]["details"]["employee_created"] is False


@pytest.mark.asyncio
async def test_approve_user_rejects_invalid_employee_status():
    """``employee_status`` 只允许 probation / active（契约层拦截）。"""
    module = _load_users_admin()

    with pytest.raises(Exception) as excinfo:
        module.ApproveUserRequest(create_employee=True, employee_status="resigned")

    assert "probation" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 三、薪资发钱边界（月度人工录入）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_input_allows_departed_employee_within_boundary(monkeypatch):
    """离职员工在 ``last_payroll_month`` **之内** ⇒ 允许录入（不误伤结算）。"""
    module = _load_hr_salary()
    monkeypatch.setattr(
        module, "PayrollPeriodLockService", _MutablePayrollPeriodLockService
    )

    employee = _employee(
        employee_code="EMP260004",
        name="李四",
        status="inactive",
        last_payroll_month="2026-08",
    )
    db = _PayrollSession(employees=[employee])

    async def _refresh(obj):
        obj.id = 1
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=_refresh)

    response = await module.upsert_payroll_manual_input(
        "EMP260004",
        "2026-08",
        body=PayrollManualInputUpdate(bonus=500, overtime_pay=120),
        db=db,
        current_user=_admin_user(),
    )

    assert response["success"] is True
    assert response["data"]["employee_code"] == "EMP260004"
    assert response["data"]["year_month"] == "2026-08"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_input_rejects_departed_employee_outside_boundary(monkeypatch):
    """离职员工超出 ``last_payroll_month`` ⇒ 409，消息里带具体月份。"""
    module = _load_hr_salary()
    monkeypatch.setattr(
        module, "PayrollPeriodLockService", _MutablePayrollPeriodLockService
    )

    employee = _employee(
        employee_code="EMP260004",
        name="李四",
        status="inactive",
        last_payroll_month="2026-08",
    )
    db = _PayrollSession(employees=[employee])

    response = await module.upsert_payroll_manual_input(
        "EMP260004",
        "2026-09",
        body=PayrollManualInputUpdate(bonus=500),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    message = _json_body(response)["message"]
    assert "2026-08" in message
    assert "2026-09" in message
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_input_rejects_probation_employee(monkeypatch):
    """试用期员工按现状口径不发薪 ⇒ 409。"""
    module = _load_hr_salary()
    monkeypatch.setattr(
        module, "PayrollPeriodLockService", _MutablePayrollPeriodLockService
    )

    employee = _employee(employee_code="EMP260010", name="曾维剑", status="probation")
    db = _PayrollSession(employees=[employee])

    response = await module.upsert_payroll_manual_input(
        "EMP260010",
        "2026-08",
        body=PayrollManualInputUpdate(bonus=500),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    assert "试用" in _json_body(response)["message"]
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 四、作废动作
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_void_payroll_record_marks_draft_as_void(monkeypatch):
    """草稿 ⇒ 作废成功（行保留 + 留痕）。"""
    module = _load_hr_salary()
    audit_calls: list = []

    async def _fake_log_action(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(module.audit_service, "log_action", _fake_log_action)

    record = _payroll_record(id=7, status="draft")
    db = _PayrollSession(payroll_records=[record], record_by_id=record)

    response = await module.void_payroll_record(
        7,
        body=module.PayrollRecordVoidRequest(reason="测试数据，业务确认作废"),
        db=db,
        current_user=_admin_user(user_id=9001),
    )

    assert response["success"] is True
    assert response["data"]["status"] == "void"
    assert record.status == "void"
    assert record.void_reason == "测试数据，业务确认作废"
    assert record.voided_at is not None
    assert record.voided_by == 9001
    assert audit_calls and audit_calls[-1]["action"] == "void_payroll_record"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_void_payroll_record_rejects_confirmed_and_paid(monkeypatch):
    """已确认 / 已发放的工资单不可作废 ⇒ 409。"""
    module = _load_hr_salary()
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    for status in ("confirmed", "paid"):
        record = _payroll_record(id=7, status=status)
        db = _PayrollSession(payroll_records=[record], record_by_id=record)

        response = await module.void_payroll_record(
            7,
            body=module.PayrollRecordVoidRequest(reason="不该作废"),
            db=db,
            current_user=_admin_user(),
        )

        assert response.status_code == 409
        assert record.status == status
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_void_payroll_record_rejects_double_void(monkeypatch):
    """已作废不可重复作废 ⇒ 409。"""
    module = _load_hr_salary()
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    record = _payroll_record(
        id=7, status="void", void_reason="已作废", voided_at=datetime.now(timezone.utc)
    )
    db = _PayrollSession(payroll_records=[record], record_by_id=record)

    response = await module.void_payroll_record(
        7,
        body=module.PayrollRecordVoidRequest(reason="再作废一次"),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    assert "作废" in _json_body(response)["message"]
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_void_payroll_record_requires_reason():
    """作废原因必填 ⇒ 422（契约层拦截）。"""
    module = _load_hr_salary()

    with pytest.raises(Exception):
        module.PayrollRecordVoidRequest(reason="")


# ---------------------------------------------------------------------------
# 五、编辑 / 确认 / 发放 的边界与作废保护
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_payroll_record_rejects_voided_record(monkeypatch):
    """已作废的工资单不可编辑 ⇒ 409。"""
    module = _load_hr_salary()
    monkeypatch.setattr(
        module, "PayrollPeriodLockService", _MutablePayrollPeriodLockService
    )

    record = _payroll_record(id=7, status="void")
    db = _PayrollSession(payroll_records=[record])

    response = await module.update_payroll_record(
        7,
        body=PayrollRecordManualUpdate(bonus=200),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    assert "作废" in _json_body(response)["message"]
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_payroll_record_rejects_month_outside_payroll_boundary(
    monkeypatch,
):
    """堵后门：超出离职结算边界的月份，草稿工资单也不许改。"""
    module = _load_hr_salary()
    monkeypatch.setattr(
        module, "PayrollPeriodLockService", _MutablePayrollPeriodLockService
    )

    record = _payroll_record(
        id=7, employee_code="EMP260004", year_month="2026-09", status="draft"
    )
    employee = _employee(
        employee_code="EMP260004",
        name="李四",
        status="inactive",
        last_payroll_month="2026-08",
    )
    db = _PayrollSession(payroll_records=[record], employees=[employee])

    response = await module.update_payroll_record(
        7,
        body=PayrollRecordManualUpdate(bonus=200),
        db=db,
        current_user=_admin_user(),
    )

    assert response.status_code == 409
    message = _json_body(response)["message"]
    assert "2026-08" in message
    assert "2026-09" in message
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_payroll_record_rejects_voided_record(monkeypatch):
    """已作废的工资单不可确认 ⇒ 409。"""
    module = _load_hr_salary()

    record = _payroll_record(id=7, status="void")
    db = _PayrollSession(record_by_id=record)

    response = await module.confirm_payroll_record(7, db=db)

    assert response.status_code == 409
    assert "作废" in _json_body(response)["message"]
    assert record.status == "void"


@pytest.mark.asyncio
async def test_mark_payroll_record_paid_rejects_voided_record(monkeypatch):
    """已作废的工资单不可标记为已发放 ⇒ 409。"""
    module = _load_hr_salary()
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    record = _payroll_record(id=7, status="void")
    db = _PayrollSession(payroll_records=[record])

    response = await module.mark_payroll_record_paid(
        7, db=db, current_user=_admin_user()
    )

    assert response.status_code == 409
    assert "作废" in _json_body(response)["message"]
    assert record.status == "void"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_payroll_record_allows_departed_employee_final_payroll(
    monkeypatch,
):
    """防误伤看门狗：离职员工的最后一张工资单**仍然可以确认**。"""
    module = _load_hr_salary()
    record = _payroll_record(
        id=7, employee_code="EMP260004", year_month="2026-07", status="draft"
    )
    db = _PayrollSession(record_by_id=record)

    class _StubConfirmationService:
        """桩：真实确认服务涉及绩效/成本/利润基准，本测试只关心路由不拦离职结算。"""

        def __init__(self, _db):
            pass

        async def confirm_record(self, record_id):
            record.status = "confirmed"
            return record

    monkeypatch.setattr(module, "PayrollConfirmationService", _StubConfirmationService)

    response = await module.confirm_payroll_record(7, db=db)

    assert response["success"] is True
    assert record.status == "confirmed"
    # 确认路径**不查员工状态** ⇒ 离职结算不会被误伤
    assert Employee not in db.queried_entities


@pytest.mark.asyncio
async def test_mark_payroll_record_paid_allows_departed_employee_final_payroll(
    monkeypatch,
):
    """防误伤看门狗：离职员工的最后一张工资单**仍然可以发放**。"""
    module = _load_hr_salary()
    monkeypatch.setattr(module.audit_service, "log_action", AsyncMock())

    record = _payroll_record(
        id=7, employee_code="EMP260004", year_month="2026-07", status="confirmed"
    )
    db = _PayrollSession(payroll_records=[record])

    response = await module.mark_payroll_record_paid(
        7, db=db, current_user=_admin_user()
    )

    assert response["success"] is True
    assert record.status == "paid"
    assert record.pay_date is not None
    # 发放路径**不查员工状态** ⇒ 离职结算不会被误伤
    assert Employee not in db.queried_entities
