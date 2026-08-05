from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import EmployeeShopAssignment, PayrollRecord


class PayrollPeriodLockedError(ValueError):
    """Raised when an upstream item would alter a confirmed payroll month."""


class PayrollPeriodLockService:
    """Own the payroll-confirmation guard shared by salary and commission flows."""

    LOCKED_STATUSES = ("confirmed", "paid")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assert_employee_month_mutable(
        self,
        *,
        employee_code: str,
        year_month: str,
    ) -> None:
        record = (
            await self.db.execute(
                select(PayrollRecord).where(
                    PayrollRecord.employee_code == employee_code,
                    PayrollRecord.year_month == year_month,
                    PayrollRecord.status.in_(self.LOCKED_STATUSES),
                )
            )
        ).scalar_one_or_none()
        if record is not None:
            raise PayrollPeriodLockedError(
                f"{year_month} 工资单已确认，不能修改会影响提成和人力成本的数据；请在下一工资月份补录。"
            )

    async def assert_shop_month_mutable(
        self,
        *,
        platform_code: str,
        shop_id: str,
        year_month: str,
    ) -> None:
        record = (
            await self.db.execute(
                select(PayrollRecord)
                .join(
                    EmployeeShopAssignment,
                    EmployeeShopAssignment.employee_code == PayrollRecord.employee_code,
                )
                .where(
                    PayrollRecord.year_month == year_month,
                    PayrollRecord.status.in_(self.LOCKED_STATUSES),
                    EmployeeShopAssignment.year_month == year_month,
                    EmployeeShopAssignment.status == "active",
                    EmployeeShopAssignment.platform_code == (platform_code or "").lower(),
                    EmployeeShopAssignment.shop_id == shop_id,
                )
            )
        ).scalar_one_or_none()
        if record is not None:
            raise PayrollPeriodLockedError(
                f"{year_month} 店铺归属已有已确认工资单，不能修改提成比例；请在下一工资月份调整。"
            )
