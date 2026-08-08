from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeePerformance,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PayrollRecord,
    PerformanceScore,
    SalaryStructure,
)


class PerformanceReadinessError(ValueError):
    """Raised before payroll or monthly settlement can write incomplete performance data."""


class PerformanceReadinessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def assert_employee_rows_ready(employee_codes: set[str], rows_by_employee: dict[str, Any]) -> None:
        pending = []
        for employee_code in sorted(employee_codes):
            row = rows_by_employee.get(employee_code)
            if row is None:
                pending.append(f"{employee_code}:缺少个人绩效")
                continue
            status = getattr(row, "calculation_status", None)
            score = getattr(row, "performance_score", None)
            # Pre-migration callers may return a lightweight row without the new
            # status columns. Migrated rows always carry an explicit status.
            if status is None and score is not None:
                continue
            if status != "complete" or score is None:
                pending.append(f"{employee_code}:{status or '待计算'}")
        if pending:
            raise PerformanceReadinessError("绩效尚未完成，无法结算：" + "；".join(pending))

    @staticmethod
    def _is_formal_shop_score(score: Any) -> bool:
        details = getattr(score, "score_details", None) or {}
        summary = details.get("summary", {}) if isinstance(details, dict) else {}
        return bool(
            summary.get("calculation_status") == "complete"
            and summary.get("formal_ready") is True
            and summary.get("ranking_pool") == "official"
        )

    @staticmethod
    def shop_dependent_employee_codes(rows_by_employee: dict[str, Any]) -> set[str]:
        """Personal-input results are complete without a corresponding shop score."""
        return {
            employee_code
            for employee_code, row in rows_by_employee.items()
            if getattr(row, "performance_source_type", None) != "personal_inputs"
        }

    async def assert_month_performance_ready(self, year_month: str) -> None:
        assignments = (await self.db.execute(select(EmployeeShopAssignment).where(
            EmployeeShopAssignment.year_month == year_month,
            EmployeeShopAssignment.status == "active",
        ))).scalars().all()
        inputs = (await self.db.execute(select(EmployeePerformanceInput).where(
            EmployeePerformanceInput.year_month == year_month,
            EmployeePerformanceInput.status == "active",
        ))).scalars().all()
        salaries = (await self.db.execute(select(SalaryStructure).where(
            SalaryStructure.status == "active",
        ))).scalars().all()
        payrolls = (await self.db.execute(select(PayrollRecord).where(
            PayrollRecord.year_month == year_month,
        ))).scalars().all()

        employee_codes = {
            str(getattr(row, "employee_code", "") or "").strip()
            for row in [*assignments, *inputs, *salaries, *payrolls]
            if str(getattr(row, "employee_code", "") or "").strip()
        }
        if not employee_codes:
            return
        performance_result = await self.db.execute(select(EmployeePerformance).where(
            EmployeePerformance.year_month == year_month,
            EmployeePerformance.employee_code.in_(employee_codes),
        ))
        performance_rows = performance_result.scalars().all()
        if not performance_rows:
            scalar_one_or_none = getattr(performance_result, "scalar_one_or_none", None)
            if callable(scalar_one_or_none):
                legacy_row = scalar_one_or_none()
                if legacy_row is not None:
                    performance_rows = [legacy_row]
        rows_by_employee = {
            str(getattr(row, "employee_code", None) or next(iter(employee_codes))): row
            for row in performance_rows
        }
        self.assert_employee_rows_ready(employee_codes, rows_by_employee)
        shop_dependent_codes = self.shop_dependent_employee_codes(rows_by_employee)

        shop_keys = {
            (str(getattr(row, "platform_code", "") or "").lower(), str(getattr(row, "shop_id", "") or ""))
            for row in assignments
            if str(getattr(row, "employee_code", "") or "").strip() in shop_dependent_codes
        }
        if not shop_keys:
            return
        score_rows = (await self.db.execute(select(PerformanceScore).where(
            PerformanceScore.period == year_month,
        ))).scalars().all()
        scores_by_shop = {
            (str(row.platform_code or "").lower(), str(row.shop_id or "")): row
            for row in score_rows
        }
        pending_shops = [
            f"{platform_code}|{shop_id}"
            for platform_code, shop_id in sorted(shop_keys)
            if not self._is_formal_shop_score(scores_by_shop.get((platform_code, shop_id)))
        ]
        if pending_shops:
            raise PerformanceReadinessError(
                "店铺绩效尚未正式完成，无法结算：" + "；".join(pending_shops)
            )
