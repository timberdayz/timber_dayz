"""Single V2 monthly payroll, labor-cost, and profit-basis refresh flow."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.labor_cost_projection_service import LaborCostProjectionService
from backend.services.payroll_generation_service import PayrollGenerationService
from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from backend.services.profit_basis_service import ProfitBasisService


class V2MonthlyRefreshService:
    """Converge a mutable month on the fixed V2 labor-cost basis."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _commission_by_employee_shop(
        income_result: Dict[str, Any],
    ) -> Dict[str, Dict[tuple[str, str], float]]:
        commissions: Dict[str, Dict[tuple[str, str], float]] = {}
        for item in income_result.get("commission_allocations", []):
            employee_code = str(item.get("employee_code") or "").strip()
            if not employee_code:
                continue
            shop_key = (
                str(item.get("platform_code") or "").lower(),
                str(item.get("shop_id") or ""),
            )
            commissions.setdefault(employee_code, {})[shop_key] = float(
                item.get("commission_amount") or 0
            )
        return commissions

    async def refresh_month(
        self,
        year_month: str,
        *,
        commit: bool = True,
    ) -> Dict[str, Any]:
        await PayrollPeriodLockService(self.db).assert_month_mutable(
            year_month=year_month
        )

        payroll_service = PayrollGenerationService(self.db)
        labor_service = LaborCostProjectionService(self.db)
        profit_basis_service = ProfitBasisService(self.db)

        # A new month has no profit basis yet. Materialize draft payroll first so
        # V2 can derive pre-commission labor cost without reading V1.
        await payroll_service.generate_month(
            year_month,
            allow_pending_performance=True,
        )
        await labor_service.refresh_month(
            year_month,
            commission_by_employee_shop={},
            commit=False,
        )
        await profit_basis_service.rebuild_month_v2(year_month, commit=False)

        income_result = await HRIncomeCalculationService(self.db).calculate_month(
            year_month,
            commit=False,
        )
        payroll_result = await payroll_service.generate_month(year_month)
        labor_result = await labor_service.refresh_month(
            year_month,
            commission_by_employee_shop=self._commission_by_employee_shop(
                income_result
            ),
            commit=False,
        )
        basis_result = await profit_basis_service.rebuild_month_v2(
            year_month,
            commit=False,
        )
        if commit:
            await self.db.commit()

        return {
            "success": True,
            "year_month": year_month,
            "commission_upserts": income_result.get("commission_upserts", 0),
            "performance_upserts": income_result.get("performance_upserts", 0),
            "employee_count": payroll_result.get("employee_count", 0),
            "payroll_upserts": payroll_result.get("payroll_upserts", 0),
            "locked_conflicts": payroll_result.get("locked_conflicts", 0),
            "locked_conflict_details": payroll_result.get(
                "locked_conflict_details", []
            ),
            "labor_cost_allocation_upserts": labor_result.get(
                "allocation_upserts", 0
            ),
            "profit_basis_shop_count": basis_result.get("shop_count", 0),
            "calculation_passes": 2,
        }
