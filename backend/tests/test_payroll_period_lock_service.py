import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Result:
    def __init__(self, record):
        self.record = record

    def scalar_one_or_none(self):
        return self.record


def test_employee_month_lock_rejects_changes_after_payroll_confirmation():
    from backend.services.payroll_period_lock_service import (
        PayrollPeriodLockedError,
        PayrollPeriodLockService,
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_Result(
                SimpleNamespace(employee_code="EMP001", status="confirmed")
            )
        )
    )

    with pytest.raises(PayrollPeriodLockedError, match="2025-07.*下一工资月份"):
        asyncio.run(
            PayrollPeriodLockService(db).assert_employee_month_mutable(
                employee_code="EMP001",
                year_month="2025-07",
            )
        )


def test_employee_month_lock_allows_draft_or_missing_payroll():
    from backend.services.payroll_period_lock_service import PayrollPeriodLockService

    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(None)))

    assert asyncio.run(
        PayrollPeriodLockService(db).assert_employee_month_mutable(
            employee_code="EMP001",
            year_month="2025-07",
        )
    ) is None


def test_shop_month_lock_rejects_config_changes_when_an_assignee_is_confirmed():
    from backend.services.payroll_period_lock_service import (
        PayrollPeriodLockedError,
        PayrollPeriodLockService,
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_Result(
                SimpleNamespace(employee_code="EMP001", status="confirmed")
            )
        )
    )

    with pytest.raises(PayrollPeriodLockedError, match="2025-07.*店铺归属"):
        asyncio.run(
            PayrollPeriodLockService(db).assert_shop_month_mutable(
                platform_code="shopee",
                shop_id="shop-1",
                year_month="2025-07",
            )
        )
