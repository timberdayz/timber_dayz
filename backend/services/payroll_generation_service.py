from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    Employee,
    EmployeeCommission,
    EmployeePerformance,
    PayrollManualInput,
    PayrollRecord,
    PersonalPerformanceEmployeeScope,
    PersonalPerformancePlan,
    SalaryStructure,
)
from modules.core.logger import get_logger
from backend.services.hr_employee_lifecycle import is_payroll_voided
from backend.services.payroll_period_lock_service import PAYROLL_LOCKED_STATUSES
from backend.services.performance_readiness_service import PerformanceReadinessService
from backend.services.commission_caliber import calculate_employee_performance_salary
from backend.services.performance_coefficient import calculate_score_coefficient

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

    async def _controlled_scope_membership(
        self, year_month: str
    ) -> dict[str, bool] | None:
        """Return the frozen population for a confirmed controlled month."""
        plan = (
            await self.db.execute(
                select(PersonalPerformancePlan).where(
                    PersonalPerformancePlan.year_month == year_month
                )
            )
        ).scalar_one_or_none()
        if (
            plan is None
            or getattr(plan, "calculation_mode", None) != "controlled_targets_v1"
            or getattr(plan, "scope_confirmed_at", None) is None
        ):
            return None
        scopes = (
            (
                await self.db.execute(
                    select(PersonalPerformanceEmployeeScope).where(
                        PersonalPerformanceEmployeeScope.plan_id == plan.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            str(scope.employee_code).strip(): bool(getattr(scope, "is_included", False))
            for scope in scopes
            if str(getattr(scope, "employee_code", "") or "").strip()
        }

    @staticmethod
    def _coerce_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return None

    @classmethod
    def _salary_effective_cutoff(cls, year_month: str) -> date:
        period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
        return period_start.replace(
            day=monthrange(period_start.year, period_start.month)[1]
        )

    @classmethod
    def _pick_salary_structure_for_month(
        cls, salary_rows: list[Any], year_month: str
    ) -> Any | None:
        if not salary_rows:
            return None
        effective_cutoff = cls._salary_effective_cutoff(year_month)
        eligible_rows = [
            row
            for row in salary_rows
            if cls._coerce_date(getattr(row, "effective_date", None)) is not None
            and cls._coerce_date(getattr(row, "effective_date", None))
            <= effective_cutoff
        ]
        if eligible_rows:
            return eligible_rows[0]
        return salary_rows[0]

    # Cleanup-phase override: prefer English ORM columns only.
    async def _load_employee_commission(self, employee_code: str, year_month: str):
        return (
            await self.db.execute(
                select(EmployeeCommission).where(
                    EmployeeCommission.employee_code == employee_code,
                    EmployeeCommission.year_month == year_month,
                )
            )
        ).scalar_one_or_none()

    async def _load_employee_performance(self, employee_code: str, year_month: str):
        return (
            await self.db.execute(
                select(EmployeePerformance).where(
                    EmployeePerformance.employee_code == employee_code,
                    EmployeePerformance.year_month == year_month,
                )
            )
        ).scalar_one_or_none()

    async def _load_employee_commission_rows(self, year_month: str):
        return (
            (
                await self.db.execute(
                    select(EmployeeCommission).where(
                        EmployeeCommission.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _load_employee_performance_rows(self, year_month: str):
        return (
            (
                await self.db.execute(
                    select(EmployeePerformance).where(
                        EmployeePerformance.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _is_salary_eligible_employee(self, employee_code: str) -> bool:
        employee = (
            await self.db.execute(
                select(Employee).where(Employee.employee_code == employee_code)
            )
        ).scalar_one_or_none()
        if employee is None:
            return True
        return (
            getattr(employee, "status", "active") == "active"
            and getattr(employee, "employee_identity_type", "employee") == "employee"
        )

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
    def _normalize_performance_coefficient(cls, performance: Any | None) -> Decimal:
        """绩效工资用的系数 —— **纯个人的绩效分数档位系数**。

        口径（ADR-2026-11-21）：

            绩效工资 = 绩效包金额 × 绩效分数档位系数(该员工的绩效分数)

        ⚠️ 这里**不再**读 ``EmployeePerformance.performance_coefficient``
        （那个字段原先存的是「逐店结算系数的销售额加权平均」，含店铺赛马排名）
        —— 绩效工资必须是**纯个人**的，与店铺排名无关。

        档位表的唯一真源是
        :data:`backend.services.performance_coefficient.SCORE_BAND_COEFFICIENTS`
        （经 ``calculate_score_coefficient(绩效分数)`` 得出）。

        「未完成考核」的口径保持不变：系数为 0 ⇒ 绩效工资为 0。
        """
        if (
            getattr(performance, "performance_source_type", None)
            == "controlled_targets_v1"
            and getattr(performance, "calculation_status", None) != "complete"
        ):
            return Decimal("0")
        performance_score = getattr(performance, "performance_score", None)
        if performance_score is None:
            return Decimal("0")
        return cls._to_decimal(calculate_score_coefficient(performance_score))

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
        manual_input: Any | None = None,
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
        commission_amount = cls._to_money(getattr(commission, "commission_amount", 0))
        performance_package_amount = cls._to_money(
            getattr(salary, "performance_package_amount", 0)
        )
        performance_coefficient = cls._normalize_performance_coefficient(performance)
        # ⚠️ 绩效工资公式的唯一实现处是 backend/services/commission_caliber.py。
        performance_salary = calculate_employee_performance_salary(
            performance_package_amount=performance_package_amount,
            performance_score_coefficient=performance_coefficient,
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
            "pay_date": getattr(
                manual_input, "pay_date", getattr(existing, "pay_date", None)
            ),
            "remark": getattr(
                manual_input, "remark", getattr(existing, "remark", None)
            ),
        }
        for field in cls.MANUAL_MONEY_FIELDS:
            source = manual_input if manual_input is not None else existing
            payload[field] = cls._to_money(getattr(source, field, 0))
        payload["backfill_source_month"] = getattr(
            manual_input,
            "backfill_source_month",
            getattr(existing, "backfill_source_month", None),
        )
        payload["backfill_note"] = getattr(
            manual_input, "backfill_note", getattr(existing, "backfill_note", None)
        )

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
    def _locked_conflict_detail(
        cls, existing: Any, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        changed_fields = []
        for field in cls.AUTO_MONEY_FIELDS:
            existing_value = cls._to_money(getattr(existing, field, 0))
            next_value = cls._to_money(payload.get(field, 0))
            if existing_value != next_value:
                changed_fields.append(field)
        return {
            "employee_code": getattr(
                existing, "employee_code", payload.get("employee_code", "")
            ),
            "year_month": getattr(
                existing, "year_month", payload.get("year_month", "")
            ),
            "payroll_status": getattr(existing, "status", None),
            "changed_fields": changed_fields,
            "current_net_salary": float(
                cls._to_money(getattr(existing, "net_salary", 0))
            ),
            "recalculated_net_salary": float(
                cls._to_money(payload.get("net_salary", 0))
            ),
        }

    @classmethod
    def _void_conflict_detail(cls, existing: Any) -> Dict[str, Any]:
        """已作废工资单的跳过说明（人话版，直接给前端展示）。"""
        return {
            "employee_code": getattr(existing, "employee_code", ""),
            "year_month": getattr(existing, "year_month", ""),
            "payroll_status": getattr(existing, "status", None),
            "void_reason": getattr(existing, "void_reason", None),
            "voided_at": (
                existing.voided_at.isoformat()
                if getattr(existing, "voided_at", None) is not None
                else None
            ),
            "voided_by": getattr(existing, "voided_by", None),
            "message": "该员工该月工资单已作废，本次未重新生成；如需补发请先撤销作废",
        }

    async def generate_employee_month(
        self, employee_code: str, year_month: str
    ) -> Dict[str, Any]:
        await PerformanceReadinessService(self.db).assert_month_performance_ready(
            year_month,
            employee_codes={employee_code},
        )
        if not await self._is_salary_eligible_employee(employee_code):
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 0,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
                "payroll_record": None,
            }
        salary_rows = (
            (
                await self.db.execute(
                    select(SalaryStructure)
                    .where(
                        SalaryStructure.employee_code == employee_code,
                        SalaryStructure.status == "active",
                    )
                    .order_by(
                        desc(SalaryStructure.effective_date), desc(SalaryStructure.id)
                    )
                )
            )
            .scalars()
            .all()
        )
        salary = self._pick_salary_structure_for_month(salary_rows, year_month)
        commission = await self._load_employee_commission(employee_code, year_month)
        performance = await self._load_employee_performance(employee_code, year_month)
        manual_input = (
            await self.db.execute(
                select(PayrollManualInput).where(
                    PayrollManualInput.employee_code == employee_code,
                    PayrollManualInput.year_month == year_month,
                )
            )
        ).scalar_one_or_none()
        controlled_scope = await self._controlled_scope_membership(year_month)
        if controlled_scope is not None and not controlled_scope.get(
            employee_code, False
        ):
            performance = None
        existing = (
            await self.db.execute(
                select(PayrollRecord).where(
                    PayrollRecord.employee_code == employee_code,
                    PayrollRecord.year_month == year_month,
                )
            )
        ).scalar_one_or_none()

        if (
            salary is None
            and commission is None
            and performance is None
            and existing is None
        ):
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 0,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
                "payroll_record": None,
            }

        payload = self._build_payload(
            employee_code=employee_code,
            year_month=year_month,
            salary=salary,
            commission=commission,
            performance=performance,
            existing=existing,
            manual_input=manual_input,
        )

        locked_status = getattr(existing, "status", None)
        if locked_status in PAYROLL_LOCKED_STATUSES:
            if self._has_locked_conflict(existing, payload):
                return {
                    "employee_code": employee_code,
                    "year_month": year_month,
                    "payroll_upserts": 0,
                    "locked_conflicts": 1,
                    "locked_conflict_details": [
                        self._locked_conflict_detail(existing, payload)
                    ],
                    "void_conflicts": 0,
                    "void_conflict_details": [],
                    "payroll_record": existing,
                }
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 0,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
                "void_conflicts": 0,
                "void_conflict_details": [],
                "payroll_record": existing,
            }

        if is_payroll_voided(existing):
            # 已作废的工资单是**冻结的历史留痕**：不可被刷新改写金额。
            # 也不新建替代单 —— 一人一月只有一张工资单（唯一索引），
            # 坑位已被这张作废单占住；要重新发这个月的工资，
            # 必须先显式「撤销作废」，把作废单恢复成草稿。
            return {
                "employee_code": employee_code,
                "year_month": year_month,
                "payroll_upserts": 0,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
                "void_conflicts": 1,
                "void_conflict_details": [self._void_conflict_detail(existing)],
                "payroll_record": existing,
            }

        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            self._recalculate_totals(existing)
            record = existing
        else:
            record = PayrollRecord(**payload)
            self._recalculate_totals(record)
            self.db.add(record)

        return {
            "employee_code": employee_code,
            "year_month": year_month,
            "payroll_upserts": 1,
            "locked_conflicts": 0,
            "locked_conflict_details": [],
            "void_conflicts": 0,
            "void_conflict_details": [],
            "payroll_record": record,
        }

    async def generate_month(
        self,
        year_month: str,
        *,
        employee_codes: set[str] | list[str] | None = None,
        allow_pending_performance: bool = False,
    ) -> Dict[str, Any]:
        if not allow_pending_performance:
            await PerformanceReadinessService(self.db).assert_month_performance_ready(
                year_month,
                employee_codes=(
                    {str(employee_code).strip() for employee_code in employee_codes}
                    if employee_codes is not None
                    else None
                ),
            )
        salary_rows = (
            (
                await self.db.execute(
                    select(SalaryStructure).where(SalaryStructure.status == "active")
                )
            )
            .scalars()
            .all()
        )
        commission_rows = await self._load_employee_commission_rows(year_month)
        performance_rows = await self._load_employee_performance_rows(year_month)
        manual_input_rows = (
            (
                await self.db.execute(
                    select(PayrollManualInput).where(
                        PayrollManualInput.year_month == year_month,
                    )
                )
            )
            .scalars()
            .all()
        )
        controlled_scope = await self._controlled_scope_membership(year_month)
        existing_rows = (
            (
                await self.db.execute(
                    select(PayrollRecord).where(PayrollRecord.year_month == year_month)
                )
            )
            .scalars()
            .all()
        )

        salary_rows_by_employee: Dict[str, list[Any]] = {}
        for row in salary_rows:
            employee_code = getattr(row, "employee_code", None)
            if not employee_code:
                continue
            salary_rows_by_employee.setdefault(employee_code, []).append(row)
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
        manual_input_by_employee = {
            row.employee_code: row
            for row in manual_input_rows
            if getattr(row, "employee_code", None)
        }
        if controlled_scope is not None:
            performance_by_employee = {
                employee_code: row
                for employee_code, row in performance_by_employee.items()
                if controlled_scope.get(str(employee_code).strip(), False)
            }
        payroll_by_employee = {
            row.employee_code: row
            for row in existing_rows
            if getattr(row, "employee_code", None)
        }

        candidate_employee_codes = (
            set(salary_rows_by_employee)
            | set(commission_by_employee)
            | set(performance_by_employee)
            | set(payroll_by_employee)
        )
        if employee_codes is not None:
            candidate_employee_codes &= {
                str(employee_code).strip()
                for employee_code in employee_codes
                if str(employee_code).strip()
            }
        employee_codes = []
        for employee_code in sorted(candidate_employee_codes):
            if await self._is_salary_eligible_employee(employee_code):
                employee_codes.append(employee_code)

        payroll_upserts = 0
        locked_conflicts = 0
        locked_conflict_details = []
        void_conflicts = 0
        void_conflict_details = []
        for employee_code in employee_codes:
            salary = self._pick_salary_structure_for_month(
                salary_rows_by_employee.get(employee_code, []),
                year_month,
            )
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
                manual_input=manual_input_by_employee.get(employee_code),
            )

            locked_status = getattr(existing, "status", None)
            if locked_status in PAYROLL_LOCKED_STATUSES:
                if self._has_locked_conflict(existing, payload):
                    locked_conflicts += 1
                    locked_conflict_details.append(
                        self._locked_conflict_detail(existing, payload)
                    )
                continue

            if is_payroll_voided(existing):
                # 已作废的工资单是冻结的历史留痕：整月刷新也不许改写它，
                # 且不新建替代单（坑位被这张作废单占着）。
                # ⚠️ 注意这里**不能**把 void 当成「锁定」：
                # 作废只冻结这一张单，不该把整个月钉死 ——
                # 同月其他人的工资单照常重算、照常确认发放。
                void_conflicts += 1
                void_conflict_details.append(self._void_conflict_detail(existing))
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
            "void_conflicts": void_conflicts,
            "void_conflict_details": void_conflict_details,
        }
