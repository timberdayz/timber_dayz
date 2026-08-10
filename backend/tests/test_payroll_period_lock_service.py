import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Result:
    def __init__(self, record):
        self.record = record

    def scalar_one_or_none(self):
        return self.record

    def scalar_one(self):
        return bool(self.record)


class _ExistsResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


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

    assert (
        asyncio.run(
            PayrollPeriodLockService(db).assert_employee_month_mutable(
                employee_code="EMP001",
                year_month="2025-07",
            )
        )
        is None
    )


def test_month_lock_rejects_recalculation_after_any_payroll_confirmation():
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
            PayrollPeriodLockService(db).assert_month_mutable(
                year_month="2025-07",
            )
        )


def test_month_lock_handles_multiple_paid_payroll_records():
    from backend.services.payroll_period_lock_service import (
        PayrollPeriodLockedError,
        PayrollPeriodLockService,
    )

    db = SimpleNamespace(execute=AsyncMock(return_value=_ExistsResult(True)))

    with pytest.raises(PayrollPeriodLockedError, match="2026-07"):
        asyncio.run(
            PayrollPeriodLockService(db).assert_month_mutable(
                year_month="2026-07",
            )
        )


def test_month_lock_status_summarizes_confirmed_and_paid_payrolls():
    from backend.services.payroll_period_lock_service import PayrollPeriodLockService

    db = SimpleNamespace(
        execute=AsyncMock(return_value=_RowsResult([("confirmed", 1), ("paid", 3)]))
    )

    status = asyncio.run(
        PayrollPeriodLockService(db).get_month_lock_status(year_month="2026-07")
    )

    assert status == {
        "period": "2026-07",
        "is_locked": True,
        "can_recalculate": False,
        "locked_record_count": 4,
        "locked_statuses": ["confirmed", "paid"],
        "reason": "2026-07 工资单已发放，不能重新计算绩效或提成，请在下一工资月份补录。",
    }


def test_salary_effective_date_lock_rejects_backdated_change_over_confirmed_month():
    from datetime import date

    from backend.services.payroll_period_lock_service import (
        PayrollPeriodLockedError,
        PayrollPeriodLockService,
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_Result(
                SimpleNamespace(
                    employee_code="EMP001", year_month="2025-07", status="confirmed"
                )
            )
        )
    )

    with pytest.raises(PayrollPeriodLockedError, match="2025-07.*下一工资月份"):
        asyncio.run(
            PayrollPeriodLockService(db).assert_salary_effective_date_mutable(
                employee_code="EMP001",
                effective_date=date(2025, 7, 1),
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
