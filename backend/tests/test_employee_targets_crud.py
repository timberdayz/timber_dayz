import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domains.business.routers.hr_salary import delete_employee_target, update_employee_target
from backend.schemas.hr import EmployeeTargetUpdate


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


def test_update_employee_target_changes_planning_value():
    record = SimpleNamespace(
        id=8,
        employee_code="E1",
        year_month="2026-03",
        target_type="sales",
        target_value=Decimal("100"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneResult(record))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = asyncio.run(update_employee_target(8, EmployeeTargetUpdate(target_value=Decimal("200")), db=db))

    assert result.target_value == Decimal("200")
    assert db.commit.await_count == 1


def test_delete_employee_target_removes_planning_record():
    record = SimpleNamespace(id=9)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneResult(record))
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    asyncio.run(delete_employee_target(9, db=db))

    db.delete.assert_awaited_once_with(record)
    assert db.commit.await_count == 1
