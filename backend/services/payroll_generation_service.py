from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    PayrollRecord,
    SalaryStructure,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


MONEY_QUANT = Decimal("0.01")


class PayrollGenerationService:
    """Generate authoritative payroll drafts from HR income intermediates."""

    MANUAL_MONEY_FIELDS = (
        "overtime_pay",
        "bonus",
        "social_insurance_personal",
        "housing_fund_personal",
        "income_tax",
        "other_deductions",
        "social_insurance_company",
        "housing_fund_company",
    )

    AUTO_MONEY_FIELDS = (
        "base_salary",
        "position_salary",
        "performance_salary",
        "commission",
        "allowances",
        "gross_salary",
        "total_deductions",
        "net_salary",
        "total_cost",
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @classmethod
    def _to_money(cls, value: Any) -> Decimal:
        return cls._to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def _sum_money(cls, *values: Any) -> Decimal:
        total = Decimal("0")
        for value in values:
            total += cls._to_decimal(value)
        return total.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def _recalculate_totals(cls, record: Any) -> None:
        gross_salary = cls._sum_money(
            getattr(record, "base_salary", 0),
            getattr(record, "position_salary", 0),
            getattr(record, "performance_salary", 0),
            getattr(record, "overtime_pay", 0),
            getattr(record, "commission", 0),
            getattr(record, "allowances", 0),
            getattr(record, "bonus", 0),
        )
        total_deductions = cls._sum_money(
            getattr(record, "social_insurance_personal", 0),
            getattr(record, "housing_fund_personal", 0),
            getattr(record, "income_tax", 0),
            getattr(record, "other_deductions", 0),
        )
        total_cost = cls._sum_money(
            gross_salary,
            getattr(record, "social_insurance_company", 0),
            getattr(record, "housing_fund_company", 0),
        )
        record.gross_salary = gross_salary
        record.total_deductions = total_deductions
        record.net_salary = (gross_salary - total_deductions).quantize(
            MONEY_QUANT, rounding=ROUND_HALF_UP
        )
        record.total_cost = total_cost

    @classmethod
    def recalculate_record_totals(cls, record: Any) -> None:
        """Expose totals recalculation for draft manual-field updates."""
        cls._recalculate_totals(record)

    @classmethod
    def _build_payload(
        cls,
        employee_code: str,
        year_month: str,
        salary: Any | None,
        commission: Any | None,
        performance: Any | None,
        existing: Any | None = None,
    ) -> Dict[str, Any]:
        base_salary = cls._to_money(getattr(salary, "base_salary", 0))
        position_salary = cls._to_money(getattr(salary, "position_salary", 0))
        allowances = cls._sum_money(
            getattr(salary, "housing_allowance", 0),
            getattr(salary, "transport_allowance", 0),
            getattr(salary, "meal_allowance", 0),
            getattr(salary, "communication_allowance", 0),
            getattr(salary, "other_allowance", 0),
        )
        commission_amount = cls._to_money(
            getattr(commission, "commission_amount", 0)
        )
        performance_ratio = cls._to_decimal(getattr(salary, "performance_ratio", 0))
        performance_score = cls._to_decimal(
            getattr(performance, "performance_score", 0)
        )
        performance_salary = (
            (base_salary + position_salary)
            * performance_ratio
            * performance_score
            / Decimal("100")
        ).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

        payload: Dict[str, Any] = {
            "employee_code": employee_code,
            "year_month": year_month,
            "base_salary": base_salary,
            "position_salary": position_salary,
            "performance_salary": performance_salary,
            "commission": commission_amount,
            "allowances": allowances,
            "status": getattr(existing, "status", "draft") or "draft",
            "pay_date": getattr(existing, "pay_date", None),
            "remark": getattr(existing, "remark", None),
        }
        for field in cls.MANUAL_MONEY_FIELDS:
            payload[field] = cls._to_money(getattr(existing, field, 0))

        gross_salary = cls._sum_money(
            payload["base_salary"],
            payload["position_salary"],
            payload["performance_salary"],
            payload["overtime_pay"],
            payload["commission"],
            payload["allowances"],
            payload["bonus"],
        )
        total_deductions = cls._sum_money(
            payload["social_insurance_personal"],
            payload["housing_fund_personal"],
            payload["income_tax"],
            payload["other_deductions"],
        )
        payload["gross_salary"] = gross_salary
        payload["total_deductions"] = total_deductions
        payload["net_salary"] = (gross_salary - total_deductions).quantize(
            MONEY_QUANT, rounding=ROUND_HALF_UP
        )
        payload["total_cost"] = cls._sum_money(
            gross_salary,
            payload["social_insurance_company"],
            payload["housing_fund_company"],
        )
        return payload

    @classmethod
    def _has_locked_conflict(cls, existing: Any, payload: Dict[str, Any]) -> bool:
        if existing is None:
            return False
        for field in cls.AUTO_MONEY_FIELDS:
            existing_value = cls._to_money(getattr(existing, field, 0))
            if existing_value != cls._to_money(payload.get(field, 0)):
                return True
        return False

    @classmethod
    def _locked_conflict_detail(cls, existing: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        changed_fields = []
        for field in cls.AUTO_MONEY_FIELDS:
            existing_value = cls._to_money(getattr(existing, field, 0))
            next_value = cls._to_money(payload.get(field, 0))
            if existing_value != next_value:
                changed_fields.append(field)
        return {
            "employee_code": getattr(existing, "employee_code", payload.get("employee_code", "")),
            "year_month": getattr(existing, "year_month", payload.get("year_month", "")),
            "payroll_status": getattr(existing, "status", None),
            "changed_fields": changed_fields,
            "current_net_salary": float(cls._to_money(getattr(existing, "net_salary", 0))),
            "recalculated_net_salary": float(cls._to_money(payload.get("net_salary", 0))),
        }

    async def generate_month(self, year_month: str) -> Dict[str, Any]:
        salary_rows = (
            await self.db.execute(
                select(SalaryStructure).where(SalaryStructure.status == "active")
            )
        ).scalars().all()
        commission_rows = (
            await self.db.execute(
                select(EmployeeCommission).where(
                    EmployeeCommission.year_month == year_month
                )
            )
        ).scalars().all()
        performance_rows = (
            await self.db.execute(
                select(EmployeePerformance).where(
                    EmployeePerformance.year_month == year_month
                )
            )
        ).scalars().all()
        existing_rows = (
            await self.db.execute(
                select(PayrollRecord).where(PayrollRecord.year_month == year_month)
            )
        ).scalars().all()

        salary_by_employee = {
            row.employee_code: row for row in salary_rows if getattr(row, "employee_code", None)
        }
        commission_by_employee = {
            row.employee_code: row
            for row in commission_rows
            if getattr(row, "employee_code", None)
        }
        performance_by_employee = {
            row.employee_code: row
            for row in performance_rows
            if getattr(row, "employee_code", None)
        }
        payroll_by_employee = {
            row.employee_code: row for row in existing_rows if getattr(row, "employee_code", None)
        }

        employee_codes = sorted(
            set(salary_by_employee)
            | set(commission_by_employee)
            | set(performance_by_employee)
            | set(payroll_by_employee)
        )

        payroll_upserts = 0
        locked_conflicts = 0
        locked_conflict_details = []
        for employee_code in employee_codes:
            salary = salary_by_employee.get(employee_code)
            commission = commission_by_employee.get(employee_code)
            performance = performance_by_employee.get(employee_code)
            existing = payroll_by_employee.get(employee_code)
            payload = self._build_payload(
                employee_code=employee_code,
                year_month=year_month,
                salary=salary,
                commission=commission,
                performance=performance,
                existing=existing,
            )

            locked_status = getattr(existing, "status", None)
            if locked_status in {"confirmed", "paid"}:
                if self._has_locked_conflict(existing, payload):
                    locked_conflicts += 1
                    locked_conflict_details.append(
                        self._locked_conflict_detail(existing, payload)
                    )
                continue

            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
                self._recalculate_totals(existing)
            else:
                record = PayrollRecord(**payload)
                self._recalculate_totals(record)
                self.db.add(record)
            payroll_upserts += 1

        return {
            "year_month": year_month,
            "employee_count": len(employee_codes),
            "payroll_upserts": payroll_upserts,
            "locked_conflicts": locked_conflicts,
            "locked_conflict_details": locked_conflict_details,
        }
