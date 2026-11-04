from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import EmployeeShopAssignment, PayrollRecord


# 工资单「已锁定」的**唯一定义源**。
#
# 历史上这里有三份各说各话的集合：
#   - 锁定服务   (confirmed, paid)
#   - 工资单路由 (confirmed, paid, approved)
#   - 我的收入路由 (confirmed, paid, approved)
#   - 工资单生成 (confirmed, paid)
# 后果：状态为 ``approved`` 的工资单在界面上显示「已锁定」，
# 但锁定服务并不认为它被锁 ⇒ 整月重算会**静默改掉**用户以为已经锁住的工资单。
#
# 现在统一成一份：``approved`` / ``confirmed`` / ``paid`` 三种状态都视为锁定。
# 判断「锁了没有」的任何地方都必须引用本常量，不要就地写字面量。
PAYROLL_LOCKED_STATUSES: tuple[str, ...] = ("approved", "confirmed", "paid")


class PayrollPeriodLockedError(ValueError):
    """Raised when an upstream item would alter a confirmed payroll month."""


class PayrollPeriodLockService:
    """Own the payroll-confirmation guard shared by salary and commission flows."""

    LOCKED_STATUSES = PAYROLL_LOCKED_STATUSES

    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire_month_transaction_lock(self, *, year_month: str) -> None:
        """Serialize monthly performance mutations on PostgreSQL until commit/rollback."""
        bind = getattr(self.db, "bind", None)
        dialect = getattr(bind, "dialect", None)
        if getattr(dialect, "name", None) != "postgresql":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"payroll-period:{year_month}"},
        )

    async def _has_locked_payroll(self, statement) -> bool:
        result = await self.db.execute(select(statement.exists()))
        return bool(result.scalar_one())

    async def get_month_lock_status(self, *, year_month: str) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(PayrollRecord.status, func.count(PayrollRecord.id))
                .where(
                    PayrollRecord.year_month == year_month,
                    PayrollRecord.status.in_(self.LOCKED_STATUSES),
                )
                .group_by(PayrollRecord.status)
            )
        ).all()
        counts_by_status = {str(status): int(count) for status, count in rows}
        locked_statuses = [
            status for status in self.LOCKED_STATUSES if status in counts_by_status
        ]
        locked_record_count = sum(counts_by_status.values())

        if "paid" in counts_by_status:
            reason = f"{year_month} 工资单已发放，不能重新计算绩效或提成，请在下一工资月份补录。"
        elif "confirmed" in counts_by_status:
            reason = f"{year_month} 工资单已确认，需退回草稿后才能重新计算绩效或提成。"
        else:
            reason = "当前月份可重新计算绩效。"

        return {
            "period": year_month,
            "is_locked": locked_record_count > 0,
            "can_recalculate": locked_record_count == 0,
            "locked_record_count": locked_record_count,
            "locked_statuses": locked_statuses,
            "reason": reason,
        }

    async def assert_employee_month_mutable(
        self,
        *,
        employee_code: str,
        year_month: str,
    ) -> None:
        has_locked_payroll = await self._has_locked_payroll(
            select(PayrollRecord.id).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.year_month == year_month,
                PayrollRecord.status.in_(self.LOCKED_STATUSES),
            )
        )
        if has_locked_payroll:
            raise PayrollPeriodLockedError(
                f"{year_month} 工资单已确认，不能修改会影响提成和人力成本的数据；请在下一工资月份补录。"
            )

    async def assert_month_mutable(self, *, year_month: str) -> None:
        """Block recalculations that would rewrite a confirmed monthly result."""
        has_locked_payroll = await self._has_locked_payroll(
            select(PayrollRecord.id).where(
                PayrollRecord.year_month == year_month,
                PayrollRecord.status.in_(self.LOCKED_STATUSES),
            )
        )
        if has_locked_payroll:
            raise PayrollPeriodLockedError(
                f"{year_month} 工资单已确认，不能重新计算绩效或提成；请在下一工资月份补录。"
            )

    async def assert_salary_effective_date_mutable(
        self,
        *,
        employee_code: str,
        effective_date: date,
    ) -> None:
        """Prevent a salary version from retroactively changing a locked payroll month."""
        effective_month = effective_date.strftime("%Y-%m")
        has_locked_payroll = await self._has_locked_payroll(
            select(PayrollRecord.id).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.year_month >= effective_month,
                PayrollRecord.status.in_(self.LOCKED_STATUSES),
            )
        )
        if has_locked_payroll:
            raise PayrollPeriodLockedError(
                f"{effective_month} 起存在已确认工资单，不能回溯修改薪资结构；请在下一工资月份补录。"
            )

    async def assert_shop_month_mutable(
        self,
        *,
        platform_code: str,
        shop_id: str,
        year_month: str,
    ) -> None:
        has_locked_payroll = await self._has_locked_payroll(
            select(PayrollRecord.id)
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
        if has_locked_payroll:
            raise PayrollPeriodLockedError(
                f"{year_month} 店铺归属已有已确认工资单，不能修改提成比例；请在下一工资月份调整。"
            )
