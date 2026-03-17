"""
add-performance-and-personal-income 验收测试

覆盖点:
1) /performance/scores/calculate 无配置 -> 404 + PERF_CONFIG_NOT_FOUND
2) /performance/scores/calculate 未就绪 -> 503 + PERF_CALC_NOT_READY
3) /performance/scores/calculate 周期格式错误 -> 400
4) /hr/me/income 未关联员工 -> linked=False 且触发审计调用
"""

import json
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from starlette.requests import Request

from backend.routers.hr_employee import get_my_income
from backend.routers.performance_management import calculate_performance_scores


def _json_body(resp) -> dict:
    """从 JSONResponse 读取 JSON 内容。"""
    return json.loads(resp.body.decode("utf-8"))


def test_calculate_returns_404_when_config_missing():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    resp = asyncio.run(
        calculate_performance_scores(period="2025-01", config_id=None, db=db)
    )

    assert resp.status_code == 404
    body = _json_body(resp)
    assert body["success"] is False
    assert body["data"]["error_code"] == "PERF_CONFIG_NOT_FOUND"


def test_calculate_returns_503_when_not_ready():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(id=1)
    db.execute.return_value = result

    resp = asyncio.run(
        calculate_performance_scores(period="2025-01", config_id=None, db=db)
    )

    assert resp.status_code == 503
    body = _json_body(resp)
    assert body["success"] is False
    assert body["data"]["error_code"] == "PERF_CALC_NOT_READY"


def test_calculate_returns_400_when_period_invalid():
    db = AsyncMock()

    resp = asyncio.run(
        calculate_performance_scores(period="2025/01", config_id=None, db=db)
    )

    assert resp.status_code == 400
    body = _json_body(resp)
    assert body["success"] is False


def test_my_income_unlinked_returns_linked_false_and_audit_called(monkeypatch):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1001)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is False
    assert called["count"] == 1


def test_my_income_linked_fallback_to_cn_columns_when_orm_columns_missing(monkeypatch):
    class _ResultOne:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _RawMapResult:
        def __init__(self, value):
            self._value = value

        def mappings(self):
            return self

        def first(self):
            return self._value

    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP001")
    execute_calls = {"n": 0}

    async def _execute(_stmt, _params=None):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        # 查询 employee
        if n == 1:
            return _ResultOne(employee)
        # 查询 payroll_records
        if n == 2:
            return _ResultOne(None)
        # 查询 salary_structures
        if n == 3:
            return _ResultOne(None)
        # ORM 查询 employee_commissions 失败 -> 触发 fallback
        if n == 4:
            raise Exception("column employee_commissions.employee_code does not exist")
        # fallback employee_commissions(中文列)
        if n == 5:
            return _RawMapResult({"commission_amount": 123.45})
        # ORM 查询 employee_performance 失败 -> 触发 fallback
        if n == 6:
            raise Exception("column employee_performance.employee_code does not exist")
        # fallback employee_performance(中文列)
        if n == 7:
            return _RawMapResult({"performance_score": 88.0, "achievement_rate": 0.76})
        return _ResultOne(None)

    db.execute = AsyncMock(side_effect=_execute)
    db.rollback = AsyncMock()

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1002)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is True
    assert float(resp.commission_amount) == 123.45
    assert float(resp.performance_score) == 88.0
    assert abs(float(resp.achievement_rate) - 0.76) < 1e-9
    assert db.rollback.await_count >= 2
    assert called["count"] == 1
