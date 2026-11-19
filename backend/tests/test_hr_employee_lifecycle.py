"""HR 员工生命周期（数据层 + 业务端点）契约测试。

风格与 ``backend/tests/test_hr_employee_identity.py`` 一致：
**不连真库** —— 迁移用「读源码 + 导入模块」断言，端点用 fake session 断言。
"""

import asyncio
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.schemas.hr import (
    EmployeeMergeRequest,
    EmployeeOffboardRequest,
    EmployeeOffboardResponse,
    EmployeeRegularizeRequest,
    EmployeeResponse,
    EmployeeVisitorPromotionRequest,
)
from backend.services.hr_employee_lifecycle import is_payroll_month_allowed

MIGRATION_PATH = Path("current_migrations/versions/20261240_hr_employee_lifecycle.py")


# ---------------------------------------------------------------------------
# 迁移文件
# ---------------------------------------------------------------------------


def _load_migration_module():
    """按路径加载迁移模块（文件名以数字开头，不能用普通 import）。"""
    spec = importlib.util.spec_from_file_location(
        "migration_20261240_hr_employee_lifecycle", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain_and_length():
    module = _load_migration_module()

    assert module.revision == "current_schema_20261240_hr_employee_lifecycle"
    assert module.down_revision == (
        "current_schema_20261239_cost_floor_caliber_closure"
    )
    # ⚠️ version_num 列是 String(64) ⇒ revision 超长会在写版本号时炸
    assert len(module.revision) <= 64


def test_migration_adds_four_new_columns():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for column in ("last_payroll_month", "leave_reason"):
        assert f'"{column}"' in source
    for column in ("void_reason", "voided_at", "voided_by"):
        assert f'"{column}"' in source
    assert "sa.String(7)" in source
    assert "sa.DateTime(timezone=True)" in source
    assert "sa.BigInteger" in source


def test_migration_adds_status_check_constraint_with_four_values():
    module = _load_migration_module()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert module.EMPLOYEE_STATUS_CONSTRAINT == "ck_employees_status_lifecycle"
    assert module.EMPLOYEE_STATUS_VALUES == ("active", "probation", "leave", "inactive")
    assert "create_check_constraint" in source
    assert "drop_constraint" in source
    # 先清洗越界值再加约束
    assert "NOT IN (" in source


def test_migration_data_fixes_target_specific_employee_codes():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for employee_code in ("EMP260004", "EMP260002", "EMP260010", "EMP260011"):
        assert employee_code in source
    # EMP260004 的 4 张草稿工资单作废
    for month in ("2026-03", "2026-04", "2026-06", "2026-07"):
        assert month in source
    assert "void_reason" in source
    # EMP260002 的结算月「待业务确认」⇒ 不许猜
    assert "待业务确认" in source


def test_migration_purges_residual_test_accounts_with_four_criteria():
    module = _load_migration_module()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    condition = module._residual_test_account_condition()
    assert "u.status = 'rejected'" in condition
    assert "u.is_active = false" in condition
    assert "public.user_sessions" in condition
    assert "a_class.employees" in condition
    for prefix in module.RESIDUAL_TEST_ACCOUNT_PREFIXES:
        assert prefix in source
    # 先留痕 → 再删审批日志 → 最后删账号
    assert "dim_user_purge_log" in source
    assert "user_approval_logs" in source
    assert "347" in source


def test_migration_cleans_account_trace_tables_before_deleting_accounts():
    """账号级痕迹表必须先清 —— 否则删 dim_users 会撞外键（本地库已复现）。"""
    module = _load_migration_module()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    trace_tables = {(schema, table) for schema, table, _ in module.ACCOUNT_TRACE_TABLES}
    assert ("public", "user_approval_logs") in trace_tables
    # ⚠️ 实测阻塞项：注册流程给每个注册用户写一条 user_registered 审计痕迹
    assert ("public", "fact_audit_logs") in trace_tables
    assert ("public", "user_sessions") in trace_tables
    # 业务表不许被自动清理 ⇒ 前置检查报错停下
    assert "_assert_no_unexpected_references" in source
    assert "pg_constraint" in source


# ---------------------------------------------------------------------------
# 发钱边界 SSOT：is_payroll_month_allowed 的六种情形
# ---------------------------------------------------------------------------


def _employee(**overrides):
    base = {
        "status": "active",
        "employee_identity_type": "employee",
        "last_payroll_month": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_payroll_month_allowed_active_has_no_upper_bound():
    employee = _employee(status="active")
    assert is_payroll_month_allowed(employee, "2026-07") is True
    assert is_payroll_month_allowed(employee, "2099-12") is True


def test_payroll_month_allowed_rejects_probation():
    employee = _employee(status="probation")
    assert is_payroll_month_allowed(employee, "2026-07") is False


def test_payroll_month_allowed_rejects_leave():
    employee = _employee(status="leave")
    assert is_payroll_month_allowed(employee, "2026-07") is False


def test_payroll_month_allowed_offboarded_inside_boundary():
    employee = _employee(status="inactive", last_payroll_month="2026-07")
    assert is_payroll_month_allowed(employee, "2026-07") is True
    assert is_payroll_month_allowed(employee, "2026-03") is True


def test_payroll_month_allowed_offboarded_outside_boundary():
    employee = _employee(status="inactive", last_payroll_month="2026-07")
    assert is_payroll_month_allowed(employee, "2026-08") is False


def test_payroll_month_allowed_offboarded_without_boundary():
    employee = _employee(status="inactive", last_payroll_month=None)
    assert is_payroll_month_allowed(employee, "2026-07") is False


# ---------------------------------------------------------------------------
# 契约
# ---------------------------------------------------------------------------


def _response_payload(**overrides):
    base = {
        "id": 1,
        "employee_code": "EMP260001",
        "name": "Alice",
        "gender": None,
        "birth_date": None,
        "id_type": None,
        "id_number": None,
        "avatar_url": None,
        "phone": None,
        "email": None,
        "address": None,
        "emergency_contact": None,
        "emergency_phone": None,
        "department_id": None,
        "position_id": None,
        "manager_id": None,
        "hire_date": None,
        "probation_end_date": None,
        "status": "active",
        "created_at": "2026-04-15T00:00:00",
        "updated_at": "2026-04-15T00:00:00",
    }
    base.update(overrides)
    return EmployeeResponse(**base)


def test_employee_response_exposes_lifecycle_fields():
    payload = _response_payload(
        last_payroll_month="2026-07",
        leave_reason="个人原因",
        department_name="运营部",
    )

    assert payload.last_payroll_month == "2026-07"
    assert payload.leave_reason == "个人原因"
    assert payload.department_name == "运营部"


def test_employee_response_normalizes_empty_status_to_active():
    assert _response_payload(status="").status == "active"
    assert _response_payload(status=None).status == "active"
    assert _response_payload(status="inactive").status == "inactive"


def test_offboard_request_validates_last_payroll_month_format():
    request = EmployeeOffboardRequest(
        leave_date=date(2026, 7, 31), last_payroll_month="2026-07"
    )
    assert request.last_payroll_month == "2026-07"

    try:
        EmployeeOffboardRequest(
            leave_date=date(2026, 7, 31), last_payroll_month="2026/07"
        )
    except Exception as exc:  # pydantic.ValidationError
        assert "last_payroll_month" in str(exc)
    else:  # pragma: no cover - 校验必须失败
        raise AssertionError("非法月份格式必须被拒绝")


def test_visitor_promotion_request_only_accepts_employee_or_visitor():
    request = EmployeeVisitorPromotionRequest()
    assert request.employee_identity_type == "employee"

    try:
        EmployeeVisitorPromotionRequest(employee_identity_type="investor")
    except Exception as exc:  # pydantic.ValidationError
        assert "employee" in str(exc)
    else:  # pragma: no cover - 校验必须失败
        raise AssertionError("非法用工身份必须被拒绝")


# ---------------------------------------------------------------------------
# offboard 端点：事务完整性
# ---------------------------------------------------------------------------


class _ScalarOneOrNone:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _employee_row(**overrides):
    base = {
        "id": 7,
        "employee_code": "EMP260004",
        "name": "李四",
        "gender": None,
        "birth_date": None,
        "id_type": None,
        "id_number": None,
        "avatar_url": None,
        "phone": "13800000000",
        "email": None,
        "address": None,
        "emergency_contact": None,
        "emergency_phone": None,
        "department_id": 3,
        "position_id": 9,
        "manager_id": None,
        "hire_date": date(2026, 1, 1),
        "probation_end_date": None,
        "regularization_date": None,
        "leave_date": None,
        "contract_type": None,
        "contract_start_date": None,
        "contract_end_date": None,
        "bank_name": None,
        "bank_account": None,
        "status": "active",
        "employee_identity_type": "employee",
        "user_id": 42,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _offboard_body():
    return EmployeeOffboardRequest(
        leave_date=date(2026, 7, 31),
        last_payroll_month="2026-07",
        leave_reason="个人原因",
    )


def _run_offboard(monkeypatch, employee, payroll_rows, assignment_rows, dim_user=None):
    from backend.domains.business.routers import hr_employee

    audit_calls = {"count": 0, "details": None}

    async def _fake_log_action(**kwargs):
        audit_calls["count"] += 1
        audit_calls["details"] = kwargs

    monkeypatch.setattr(hr_employee.audit_service, "log_action", _fake_log_action)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNone(employee),
            _ScalarRows(payroll_rows),
            _ScalarOneOrNone(dim_user),
            _ScalarRows(assignment_rows),
        ]
    )
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = asyncio.run(
        hr_employee.offboard_employee(
            "EMP260004",
            _offboard_body(),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )
    return result, db, audit_calls


def test_offboard_performs_all_lifecycle_actions_in_one_transaction(monkeypatch):
    employee = _employee_row()
    payroll_rows = [SimpleNamespace(year_month="2026-07")]
    future_assignment = SimpleNamespace(
        employee_code="EMP260004",
        year_month="2026-08",
        status="active",
    )
    dim_user = SimpleNamespace(user_id=42, username="lisi")

    result, db, audit_calls = _run_offboard(
        monkeypatch, employee, payroll_rows, [future_assignment], dim_user
    )

    # 1) 员工本体：离职状态 + 离职日期 + 最后发薪月 + 离职原因 + 更新时间
    assert employee.status == "inactive"
    assert employee.leave_date == date(2026, 7, 31)
    assert employee.last_payroll_month == "2026-07"
    assert employee.leave_reason == "个人原因"
    assert employee.updated_at is not None
    # 2) 解除账号关联
    assert employee.user_id is None
    # 3) 未来归属只改状态、不删行
    assert future_assignment.status == "inactive"
    assert db.delete.await_count == 0
    # 4) 审计日志
    assert audit_calls["count"] == 1
    assert audit_calls["details"]["resource"] == "employee/offboard"
    assert audit_calls["details"]["action"] == "offboard"
    # 5) 业务变更一次提交
    assert db.commit.await_count == 1
    # 草稿工资单只提醒、不阻断
    assert result.pending_payroll_months == ["2026-07"]
    assert result.status == "inactive"


def test_offboard_rejects_already_inactive_employee(monkeypatch):
    from backend.domains.business.routers import hr_employee

    employee = _employee_row(status="inactive")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarOneOrNone(employee)])
    db.commit = AsyncMock()

    response = asyncio.run(
        hr_employee.offboard_employee(
            "EMP260004",
            _offboard_body(),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert response.status_code == 400
    assert db.commit.await_count == 0


# ---------------------------------------------------------------------------
# merge-visitor 端点：只在 target 字段为空时才搬
# ---------------------------------------------------------------------------


def test_merge_contact_fields_only_fills_empty_target_fields():
    from backend.domains.business.routers import hr_employee

    target = SimpleNamespace(
        phone="13900000000",
        email=None,
        address="",
        emergency_contact=None,
        emergency_phone=None,
    )
    source = SimpleNamespace(
        phone="13711111111",
        email="visitor@example.com",
        address="某市某区",
        emergency_contact="张三",
        emergency_phone="13600000000",
    )

    moved = hr_employee._merge_employee_contact_fields(target, source)

    # 有值的字段不被覆盖
    assert target.phone == "13900000000"
    # 空字段被搬过来
    assert target.email == "visitor@example.com"
    assert target.address == "某市某区"
    assert target.emergency_contact == "张三"
    assert target.emergency_phone == "13600000000"
    assert moved == ["email", "address", "emergency_contact", "emergency_phone"]


def test_merge_visitor_deletes_source_and_moves_only_missing_contact_fields(
    monkeypatch,
):
    from backend.domains.business.routers import hr_employee

    audit_calls = {"count": 0, "details": None}

    async def _fake_log_action(**kwargs):
        audit_calls["count"] += 1
        audit_calls["details"] = kwargs

    monkeypatch.setattr(hr_employee.audit_service, "log_action", _fake_log_action)

    target = _employee_row(
        employee_code="EMP260010",
        name="曾维剑",
        phone="13900000000",
        email=None,
        address=None,
        emergency_contact=None,
        emergency_phone=None,
        user_id=None,
    )
    source = _employee_row(
        id=99,
        employee_code="EMP260099",
        name="访客",
        employee_identity_type="visitor",
        phone="13711111111",
        email="visitor@example.com",
        address=None,
        emergency_contact="李四",
        emergency_phone=None,
        user_id=555,
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNone(target),
            _ScalarOneOrNone(source),
            _ScalarRows([]),
            _ScalarOneOrNone(SimpleNamespace(user_id=555, username="visitor")),
        ]
    )
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = asyncio.run(
        hr_employee.merge_visitor_employee(
            "EMP260010",
            EmployeeMergeRequest(source_employee_code="EMP260099"),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    # target 已有值不被覆盖，空值被搬过来
    assert target.phone == "13900000000"
    assert target.email == "visitor@example.com"
    assert target.emergency_contact == "李四"
    # 账号被搬到 target（target 原本没有）
    assert target.user_id == 555
    # source 被真删
    assert db.delete.await_count == 1
    assert db.delete.await_args.args[0] is source
    assert db.commit.await_count == 1
    assert audit_calls["count"] == 1
    assert audit_calls["details"]["resource"] == "employee/merge-visitor"
    assert result.employee_code == "EMP260010"


def test_merge_visitor_rejects_same_source_and_target():
    from backend.domains.business.routers import hr_employee

    db = AsyncMock()
    db.commit = AsyncMock()

    response = asyncio.run(
        hr_employee.merge_visitor_employee(
            "EMP260099",
            EmployeeMergeRequest(source_employee_code="EMP260099"),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert response.status_code == 400
    assert db.commit.await_count == 0


# ---------------------------------------------------------------------------
# regularize / promote-visitor
# ---------------------------------------------------------------------------


def test_regularize_promotes_probation_employee_to_active(monkeypatch):
    from backend.domains.business.routers import hr_employee

    async def _fake_log_action(**kwargs):
        return None

    monkeypatch.setattr(hr_employee.audit_service, "log_action", _fake_log_action)

    employee = _employee_row(status="probation")
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNone(employee),
            _ScalarOneOrNone(SimpleNamespace(user_id=42, username="lisi")),
        ]
    )
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = asyncio.run(
        hr_employee.regularize_employee(
            "EMP260010",
            EmployeeRegularizeRequest(
                regularization_date=date(2026, 7, 1),
                probation_end_date=date(2026, 6, 30),
            ),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert employee.status == "active"
    assert employee.regularization_date == date(2026, 7, 1)
    assert employee.probation_end_date == date(2026, 6, 30)
    assert db.commit.await_count == 1
    assert result.status == "active"


def test_regularize_rejects_non_probation_employee():
    from backend.domains.business.routers import hr_employee

    employee = _employee_row(status="active")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarOneOrNone(employee)])
    db.commit = AsyncMock()

    response = asyncio.run(
        hr_employee.regularize_employee(
            "EMP260010",
            EmployeeRegularizeRequest(regularization_date=date(2026, 7, 1)),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert response.status_code == 400
    assert db.commit.await_count == 0


def test_promote_visitor_switches_identity_and_fills_optional_fields(monkeypatch):
    from backend.domains.business.routers import hr_employee

    async def _fake_log_action(**kwargs):
        return None

    monkeypatch.setattr(hr_employee.audit_service, "log_action", _fake_log_action)

    employee = _employee_row(employee_identity_type="visitor")
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNone(employee),
            _ScalarOneOrNone(SimpleNamespace(user_id=42, username="lisi")),
        ]
    )
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = asyncio.run(
        hr_employee.promote_visitor_employee(
            "EMP260099",
            EmployeeVisitorPromotionRequest(
                department_id=5, position_id=7, hire_date=date(2026, 8, 1)
            ),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert employee.employee_identity_type == "employee"
    assert employee.department_id == 5
    assert employee.position_id == 7
    assert employee.hire_date == date(2026, 8, 1)
    assert db.commit.await_count == 1
    assert result.employee_identity_type == "employee"


def test_promote_visitor_rejects_employee_identity():
    from backend.domains.business.routers import hr_employee

    employee = _employee_row(employee_identity_type="employee")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarOneOrNone(employee)])
    db.commit = AsyncMock()

    response = asyncio.run(
        hr_employee.promote_visitor_employee(
            "EMP260099",
            EmployeeVisitorPromotionRequest(),
            current_user=SimpleNamespace(user_id=9001),
            db=db,
        )
    )

    assert response.status_code == 400
    assert db.commit.await_count == 0


# ---------------------------------------------------------------------------
# 列表筛选
# ---------------------------------------------------------------------------


def test_list_employees_rejects_unknown_identity_type():
    from backend.domains.business.routers import hr_employee

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=AssertionError("不应查询数据库"))

    response = asyncio.run(
        hr_employee.list_employees(
            department_id=None,
            position_id=None,
            status=None,
            identity_type="investor",
            keyword=None,
            page=1,
            page_size=20,
            db=db,
        )
    )

    assert response.status_code == 400


def test_offboard_response_carries_pending_payroll_months():
    payload = _response_payload(status="inactive", last_payroll_month="2026-07")
    result = EmployeeOffboardResponse.model_validate(payload, from_attributes=True)

    assert result.pending_payroll_months == []
