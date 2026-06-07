import asyncio
from inspect import signature
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select

from backend.domains.business.routers.hr_salary import delete_employee_target, list_employee_targets, update_employee_target
from backend.schemas.hr import EmployeeTargetUpdate
from modules.core.db import EmployeeTarget


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


def test_list_employee_targets_supports_batch_page_size_used_by_frontend():
    page_size_default = signature(list_employee_targets).parameters["page_size"].default
    page_size_limit = next(item.le for item in page_size_default.metadata if hasattr(item, "le"))

    assert page_size_limit == 500


def test_employee_target_orm_maps_to_existing_chinese_columns():
    compiled = str(select(EmployeeTarget).where(EmployeeTarget.employee_code == "E1"))

    assert "员工编号" in compiled
    assert "employee_targets.employee_code" not in compiled
