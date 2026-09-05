import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from modules.core.db import EmployeeShopAssignment


class _ScalarRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return False


def test_copy_previous_month_assignments_updates_existing_and_adds_missing_keys():
    from backend.domains.business.routers import hr_commission

    db = AsyncMock()
    previous_rows = [
        SimpleNamespace(
            employee_code="EMP001",
            platform_code="shopee",
            shop_id="shop-1",
            commission_ratio=0.25,
            role="supervisor",
            effective_from=None,
            effective_to=None,
        ),
        SimpleNamespace(
            employee_code="EMP002",
            platform_code="shopee",
            shop_id="shop-2",
            commission_ratio=0.1,
            role="operator",
            effective_from=None,
            effective_to=None,
        ),
    ]
    target_rows = [
        SimpleNamespace(
            employee_code="EMP001",
            platform_code="shopee",
            shop_id="shop-1",
        )
    ]
    execution_count = 0

    async def execute(statement):
        nonlocal execution_count
        execution_count += 1
        if execution_count == 1:
            return _ScalarRowsResult(previous_rows)
        selected_expr = statement.column_descriptions[0]["expr"]
        if selected_expr is EmployeeShopAssignment:
            return _ScalarRowsResult(target_rows)
        return _ScalarRowsResult([])

    db.execute = execute
    db.add = Mock()
    db.commit = AsyncMock()

    result = asyncio.run(
        hr_commission.copy_employee_shop_assignments_from_prev_month(
            body=hr_commission.CopyFromPrevMonthBody(year_month="2026-09"),
            db=db,
            current_user=SimpleNamespace(),
        )
    )

    assert result["success"] is True
    assert result["data"]["copied"] == 1
    assert result["data"]["updated"] == 1
    db.commit.assert_awaited_once()
    assert db.add.call_count == 1
    copied_assignment = db.add.call_args.args[0]
    assert copied_assignment.employee_code == "EMP002"
    assert copied_assignment.shop_id == "shop-2"


def test_copy_source_includes_shop_commission_config():
    from inspect import getsource
    from backend.domains.business.routers import hr_commission

    source = getsource(hr_commission.copy_employee_shop_assignments_from_prev_month)
    assert "ShopCommissionConfig" in source
    assert "allocatable_profit_rate" in source
