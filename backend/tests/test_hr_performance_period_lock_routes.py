import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.payroll_period_lock_service import PayrollPeriodLockedError


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _LockedPayrollPeriodLockService:
    def __init__(self, _db):
        pass

    async def assert_employee_month_mutable(self, **_kwargs):
        raise PayrollPeriodLockedError("2025-07 工资单已确认，请在下一工资月份补录。")


@pytest.mark.parametrize(
    ("helper_name", "body_factory"),
    [
        (
            "_create_employee_performance_adjustment",
            lambda module: module.EmployeePerformanceAdjustmentCreate(
                year_month="2025-07",
                employee_code="EMP001",
                adjustment_type="manual",
                score_delta=5,
            ),
        ),
        (
            "_create_employee_performance_input",
            lambda module: module.EmployeePerformanceInputCreate(
                year_month="2025-07",
                employee_code="EMP001",
                metric_code="quality",
                metric_direction="up",
                max_score=100,
            ),
        ),
    ],
)
def test_performance_writes_reject_confirmed_payroll_month(
    monkeypatch,
    helper_name,
    body_factory,
):
    module = importlib.import_module("backend.domains.business.routers.hr_commission")
    monkeypatch.setattr(
        module,
        "PayrollPeriodLockService",
        _LockedPayrollPeriodLockService,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[_Result(SimpleNamespace(name="Alice")), _Result(None)]
        )
    )

    response = asyncio.run(
        getattr(module, helper_name)(
            body=body_factory(module),
            db=db,
            current_user=SimpleNamespace(user_id=1),
        )
    )

    assert response.status_code == 409
    assert json.loads(response.body.decode("utf-8"))["success"] is False


def test_performance_calculation_rejects_confirmed_payroll_month(monkeypatch):
    module = importlib.import_module("backend.domains.business.routers.performance_management")

    class _LockedMonthService:
        def __init__(self, _db):
            pass

        async def assert_month_mutable(self, **_kwargs):
            raise PayrollPeriodLockedError("2025-07 工资单已确认，请在下一工资月份补录。")

    monkeypatch.setattr(module, "PayrollPeriodLockService", _LockedMonthService)

    response = asyncio.run(
        module.calculate_performance_scores(
            period="2025-07",
            config_id=None,
            db=SimpleNamespace(rollback=AsyncMock()),
            _current_user=SimpleNamespace(),
        )
    )

    assert response.status_code == 409
    assert json.loads(response.body.decode("utf-8"))["success"] is False
