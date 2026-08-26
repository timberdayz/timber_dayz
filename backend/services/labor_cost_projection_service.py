from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeeLaborCostAllocation,
    EmployeeShopAssignment,
    PayrollRecord,
)


MONEY_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.000001")
LABOR_COST_CALCULATION_VERSION = "LABOR_COST_V2"


class LaborCostProjectionService:
    """Build reusable store-level labor-cost allocations from payroll data."""

    PRE_COMMISSION_FIELDS = (
        "base_salary",
        "position_salary",
        "allowances",
        "overtime_pay",
        "bonus",
        "social_insurance_company",
        "housing_fund_company",
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _money(value: Any) -> Decimal:
        return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def _split_evenly(cls, amount: Decimal, count: int) -> list[Decimal]:
        if count <= 0:
            return []
        base = (amount / count).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        values = [base] * count
        values[-1] += amount - sum(values)
        return values

    @classmethod
    def build_allocation_rows(
        cls,
        *,
        payroll: Any,
        assignments: Iterable[Any],
        commission_by_shop: Mapping[tuple[str, str], Any],
    ) -> list[dict[str, Any]]:
        """Return shop or company rows without persisting them.

        `commission_by_shop` is the authoritative per-shop calculation. The
        employee payroll commission is intentionally not averaged as a fallback.
        """
        active_assignments = [
            assignment
            for assignment in assignments
            if str(getattr(assignment, "status", "active") or "active") == "active"
        ]
        pre_commission = sum(
            (cls._money(getattr(payroll, field, 0)) for field in cls.PRE_COMMISSION_FIELDS),
            Decimal("0.00"),
        )
        performance = cls._money(getattr(payroll, "performance_salary", 0))
        employee_code = str(getattr(payroll, "employee_code", "") or "").strip()
        source_payroll_status = str(getattr(payroll, "status", "draft") or "draft")

        if not active_assignments:
            commission = sum(
                (cls._money(amount) for amount in commission_by_shop.values()),
                Decimal("0.00"),
            )
            total = pre_commission + performance + commission
            return [
                {
                    "employee_code": employee_code,
                    "platform_code": None,
                    "shop_id": None,
                    "allocation_scope": "company",
                    "allocation_ratio": Decimal("1").quantize(RATIO_QUANT),
                    "pre_commission_amount": pre_commission,
                    "performance_amount": performance,
                    "commission_amount": commission,
                    "total_amount": total,
                    "source_payroll_status": source_payroll_status,
                }
            ]

        pre_parts = cls._split_evenly(pre_commission, len(active_assignments))
        performance_parts = cls._split_evenly(performance, len(active_assignments))
        ratio = (Decimal("1") / len(active_assignments)).quantize(
            RATIO_QUANT, rounding=ROUND_HALF_UP
        )
        rows = []
        for index, assignment in enumerate(active_assignments):
            platform_code = str(getattr(assignment, "platform_code", "") or "").lower()
            shop_id = str(getattr(assignment, "shop_id", "") or "")
            commission = cls._money(commission_by_shop.get((platform_code, shop_id), 0))
            total = pre_parts[index] + performance_parts[index] + commission
            rows.append(
                {
                    "employee_code": employee_code,
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "allocation_scope": "shop",
                    "allocation_ratio": ratio,
                    "pre_commission_amount": pre_parts[index],
                    "performance_amount": performance_parts[index],
                    "commission_amount": commission,
                    "total_amount": total,
                    "source_payroll_status": source_payroll_status,
                }
            )
        return rows

    async def refresh_month(
        self,
        year_month: str,
        *,
        commission_by_employee_shop: Mapping[str, Mapping[tuple[str, str], Any]] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        payroll_rows = (
            await self.db.execute(
                select(PayrollRecord).where(PayrollRecord.year_month == year_month)
            )
        ).scalars().all()
        assignment_rows = (
            await self.db.execute(
                select(EmployeeShopAssignment).where(
                    EmployeeShopAssignment.year_month == year_month,
                    EmployeeShopAssignment.status == "active",
                )
            )
        ).scalars().all()
        existing_rows = (
            await self.db.execute(
                select(EmployeeLaborCostAllocation).where(
                    EmployeeLaborCostAllocation.period_month == year_month,
                    EmployeeLaborCostAllocation.calculation_version == LABOR_COST_CALCULATION_VERSION,
                )
            )
        ).scalars().all()

        assignments_by_employee: dict[str, list[Any]] = {}
        for assignment in assignment_rows:
            employee_code = str(getattr(assignment, "employee_code", "") or "").strip()
            if employee_code:
                assignments_by_employee.setdefault(employee_code, []).append(assignment)

        existing_by_key: dict[tuple[str, str, str, str], Any] = {}
        commission_by_employee: dict[str, dict[tuple[str, str], Decimal]] = {}
        for record in existing_rows:
            employee_code = str(getattr(record, "employee_code", "") or "").strip()
            scope = str(getattr(record, "allocation_scope", "") or "")
            platform_code = str(getattr(record, "platform_code", "") or "").lower()
            shop_id = str(getattr(record, "shop_id", "") or "")
            existing_by_key[(employee_code, scope, platform_code, shop_id)] = record
            if scope == "shop":
                commission_by_employee.setdefault(employee_code, {})[(platform_code, shop_id)] = self._money(
                    getattr(record, "commission_amount", 0)
                )

        for employee_code, values in (commission_by_employee_shop or {}).items():
            commission_by_employee[str(employee_code)] = {
                (str(platform_code or "").lower(), str(shop_id or "")): self._money(amount)
                for (platform_code, shop_id), amount in values.items()
            }

        allocation_upserts = 0
        for payroll in payroll_rows:
            employee_code = str(getattr(payroll, "employee_code", "") or "").strip()
            if not employee_code:
                continue
            rows = self.build_allocation_rows(
                payroll=payroll,
                assignments=assignments_by_employee.get(employee_code, []),
                commission_by_shop=commission_by_employee.get(employee_code, {}),
            )
            for row in rows:
                scope = row["allocation_scope"]
                platform_code = str(row["platform_code"] or "").lower()
                shop_id = str(row["shop_id"] or "")
                key = (employee_code, scope, platform_code, shop_id)
                record = existing_by_key.get(key)
                if record is not None and getattr(record, "pre_commission_locked_at", None):
                    if self._money(getattr(record, "pre_commission_amount", 0)) != row["pre_commission_amount"]:
                        raise ValueError(
                            f"pre-commission labor cost is locked for {employee_code}; reopen settlement before refresh"
                        )

                status = "confirmed" if row["source_payroll_status"] in {"confirmed", "paid"} else "projected"
                values = {
                    **row,
                    "period_month": year_month,
                    "source_payroll_record_id": getattr(payroll, "id", None),
                    "calculation_status": status,
                    "calculation_version": LABOR_COST_CALCULATION_VERSION,
                }
                if record is None:
                    record = EmployeeLaborCostAllocation(**values)
                    self.db.add(record)
                    existing_by_key[key] = record
                else:
                    for field, value in values.items():
                        setattr(record, field, value)
                allocation_upserts += 1

        if commit:
            await self.db.commit()
        return {"year_month": year_month, "allocation_upserts": allocation_upserts}
