"""
HR employee income C-class write service.

Sources:
- a_class.employee_shop_assignments
- a_class.shop_commission_config
- finance.shop_profit_basis
- c_class.performance_scores
- PostgreSQL monthly shop metrics fallback
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    AttendanceRecord,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceAdjustment,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PerformanceScore,
    SalaryStructure,
    ShopCommissionConfig,
    ShopProfitBasis,
)
from modules.core.logger import get_logger
from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics
from backend.services.profit_basis_service import ProfitBasisService

logger = get_logger(__name__)


class HRIncomeCalculationService:
    """Calculate and persist employee commission and performance rows."""

    ATTENDANCE_PENALTY_BY_STATUS = {
        "late": -1.0,
        "early_leave": -1.0,
        "absent": -5.0,
    }

    def __init__(self, db: AsyncSession, metabase_service: Optional[Any] = None):
        self.db = db
        self.metabase_service = metabase_service

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_achievement_rate(raw_rate: Any) -> float:
        rate = HRIncomeCalculationService._to_float(raw_rate, 0.0)
        if rate > 1:
            rate = rate / 100.0
        if rate < 0:
            return 0.0
        return rate

    @staticmethod
    def _shop_key(platform_code: Any, shop_id: Any) -> str:
        return f"{(platform_code or '').lower()}|{str(shop_id or '').lower()}"

    @staticmethod
    def _year_month_last_day(year_month: str):
        period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
        return period_start.replace(day=monthrange(period_start.year, period_start.month)[1])

    @staticmethod
    def _coerce_date(value: Any):
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _score_details_field(details: Dict[str, Any] | None, *keys: str) -> Any:
        current: Any = details or {}
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

    @staticmethod
    def _normalize_metric_direction(direction: Any) -> str:
        normalized = str(direction or "").strip().lower()
        if normalized in {"up", "higher", "higher_better", "gte", "maximize", "max"}:
            return "up"
        if normalized in {"down", "lower", "lower_better", "lte", "minimize", "min"}:
            return "down"
        return "up"

    @classmethod
    def _calculate_input_metric_score(cls, row: Any) -> float:
        max_score = cls._to_float(getattr(row, "max_score", None), 0.0)
        if max_score <= 0:
            return 0.0

        manual_enabled = bool(getattr(row, "manual_score_enabled", False))
        manual_score_value = getattr(row, "manual_score_value", None)
        if manual_enabled and manual_score_value is not None:
            return min(max(cls._to_float(manual_score_value, 0.0), 0.0), max_score)

        target_value = cls._to_float(getattr(row, "target_value", None), 0.0)
        achieved_value = cls._to_float(getattr(row, "achieved_value", None), 0.0)
        direction = cls._normalize_metric_direction(
            getattr(row, "metric_direction", None)
        )

        if direction == "down":
            if achieved_value <= 0:
                return max_score
            if target_value <= 0:
                return 0.0
            ratio = min(target_value / achieved_value, 1.0)
            return max(ratio * max_score, 0.0)

        if target_value <= 0:
            return 0.0
        ratio = min(achieved_value / target_value, 1.0)
        return max(ratio * max_score, 0.0)

    async def _load_shop_metrics(self, year_month: str) -> Dict[str, Dict[str, float]]:
        metrics_by_shop = await load_shop_monthly_metrics(self.db, year_month)
        return {
            key: {
                "monthly_sales": self._to_float(value.get("monthly_sales"), 0.0),
                "monthly_profit": self._to_float(value.get("monthly_profit"), 0.0),
                "achievement_rate": self._normalize_achievement_rate(
                    value.get("achievement_rate")
                ),
            }
            for key, value in metrics_by_shop.items()
        }

    async def _load_profit_basis_by_shop(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, Dict[str, float]]:
        basis_service = ProfitBasisService(self.db)
        shop_keys = {
            self._shop_key(row.platform_code, row.shop_id): (
                (row.platform_code or "").lower(),
                row.shop_id,
            )
            for row in assignments
        }
        basis_by_shop: Dict[str, Dict[str, float]] = {}

        snapshot_rows = (
            await self.db.execute(
                select(ShopProfitBasis).where(
                    ShopProfitBasis.period_month == year_month,
                    ShopProfitBasis.basis_version == "A_ONLY_V1",
                )
            )
        ).scalars().all()
        for row in snapshot_rows:
            key = self._shop_key(
                getattr(row, "platform_code", None),
                getattr(row, "shop_id", None),
            )
            if key not in shop_keys:
                continue
            if not bool(getattr(row, "is_locked", False)):
                continue
            basis_by_shop[key] = {
                "profit_basis_amount": self._to_float(
                    getattr(row, "profit_basis_amount", 0.0),
                    0.0,
                )
            }

        for key, (platform_code, shop_id) in shop_keys.items():
            if key in basis_by_shop:
                continue
            basis = await basis_service.build_profit_basis(
                year_month=year_month,
                platform_code=platform_code,
                shop_id=shop_id,
            )
            basis_by_shop[key] = {
                "profit_basis_amount": self._to_float(
                    basis.get("profit_basis_amount"),
                    0.0,
                )
            }
        return basis_by_shop

    async def _load_store_performance_by_shop(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, Dict[str, float]]:
        shop_keys = {
            self._shop_key(row.platform_code, row.shop_id): (
                (row.platform_code or "").lower(),
                row.shop_id,
            )
            for row in assignments
        }
        if not shop_keys:
            return {}

        platform_codes = sorted({platform_code for platform_code, _ in shop_keys.values()})
        shop_ids = sorted({shop_id for _, shop_id in shop_keys.values()})
        rows = (
            await self.db.execute(
                select(PerformanceScore).where(
                    PerformanceScore.period == year_month,
                    PerformanceScore.platform_code.in_(platform_codes),
                    PerformanceScore.shop_id.in_(shop_ids),
                )
            )
        ).scalars().all()

        performance_by_shop: Dict[str, Dict[str, float]] = {}
        for row in rows:
            details = getattr(row, "score_details", None) or {}
            summary_status = self._score_details_field(details, "summary", "status")
            total_score = getattr(row, "total_score", None)
            if total_score is None:
                continue
            if summary_status not in (None, "complete"):
                continue
            sales_target = self._to_float(
                self._score_details_field(details, "sales", "target"),
                0.0,
            )
            performance_by_shop[self._shop_key(row.platform_code, row.shop_id)] = {
                "total_score": self._to_float(total_score, 0.0),
                "performance_coefficient": self._to_float(
                    getattr(row, "performance_coefficient", None),
                    1.0,
                ),
                "sales_target": sales_target,
            }
        return performance_by_shop

    async def _load_attendance_adjustment_by_employee(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, float]:
        employee_codes = sorted(
            {
                (row.employee_code or "").strip()
                for row in assignments
                if (row.employee_code or "").strip()
            }
        )
        if not employee_codes:
            return {}

        period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
        if period_start.month == 12:
            next_month = period_start.replace(year=period_start.year + 1, month=1, day=1)
        else:
            next_month = period_start.replace(month=period_start.month + 1, day=1)

        try:
            rows = (
                await self.db.execute(
                    select(AttendanceRecord).where(
                        AttendanceRecord.employee_code.in_(employee_codes),
                        AttendanceRecord.attendance_date >= period_start,
                        AttendanceRecord.attendance_date < next_month,
                    )
                )
            ).scalars().all()
        except Exception:
            await self.db.rollback()
            try:
                rows = (
                    await self.db.execute(
                        text(
                            """
                            select
                              "员工编号" as employee_code,
                              "状态" as status
                            from a_class.attendance_records
                            where "员工编号" = any(:employee_codes)
                              and "考勤日期" >= :period_start
                              and "考勤日期" < :next_month
                            """
                        ),
                        {
                            "employee_codes": employee_codes,
                            "period_start": period_start,
                            "next_month": next_month,
                        },
                    )
                ).mappings().all()
            except Exception:
                await self.db.rollback()
                rows = (
                    await self.db.execute(
                        text(
                            """
                            select
                              "员工编号" as employee_code,
                              "状态" as status
                            from a_class.attendance_records
                            where "员工编号" = any(:employee_codes)
                              and "考勤日期" >= :period_start
                              and "考勤日期" < :next_month
                            """
                        ),
                        {
                            "employee_codes": employee_codes,
                            "period_start": period_start,
                            "next_month": next_month,
                        },
                    )
                ).mappings().all()

        adjustment_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (
                row.get("employee_code", "")
                if isinstance(row, dict)
                else (getattr(row, "employee_code", None) or "")
            ).strip()
            if not employee_code:
                continue
            raw_status = (
                row.get("status", "")
                if isinstance(row, dict)
                else (getattr(row, "status", None) or "")
            )
            status = str(raw_status).strip().lower()
            delta = self.ATTENDANCE_PENALTY_BY_STATUS.get(status, 0.0)
            adjustment_by_employee[employee_code] = adjustment_by_employee.get(employee_code, 0.0) + delta
        return adjustment_by_employee

    async def _load_manual_adjustment_by_employee(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, float]:
        employee_codes = sorted(
            {
                (row.employee_code or "").strip()
                for row in assignments
                if (row.employee_code or "").strip()
            }
        )
        if not employee_codes:
            return {}

        rows = (
            await self.db.execute(
                select(EmployeePerformanceAdjustment).where(
                    EmployeePerformanceAdjustment.year_month == year_month,
                    EmployeePerformanceAdjustment.status == "active",
                    EmployeePerformanceAdjustment.employee_code.in_(employee_codes),
                )
            )
        ).scalars().all()

        adjustment_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            delta = self._to_float(getattr(row, "score_delta", None), 0.0)
            adjustment_by_employee[employee_code] = adjustment_by_employee.get(employee_code, 0.0) + delta
        return adjustment_by_employee

    async def _load_employee_performance_input_score_by_employee(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, float]:
        employee_codes = sorted(
            {
                (row.employee_code or "").strip()
                for row in assignments
                if (row.employee_code or "").strip()
            }
        )
        if not employee_codes:
            return {}

        rows = (
            await self.db.execute(
                select(EmployeePerformanceInput).where(
                    EmployeePerformanceInput.year_month == year_month,
                    EmployeePerformanceInput.status == "active",
                    EmployeePerformanceInput.employee_code.in_(employee_codes),
                )
            )
        ).scalars().all()

        score_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            score_by_employee[employee_code] = score_by_employee.get(employee_code, 0.0) + self._calculate_input_metric_score(row)
        return {
            employee_code: min(max(score, 0.0), 100.0)
            for employee_code, score in score_by_employee.items()
        }

    async def _load_default_commission_ratio_by_employee(
        self,
        year_month: str,
        assignments: list[Any],
    ) -> Dict[str, float]:
        employee_codes = sorted(
            {
                (row.employee_code or "").strip()
                for row in assignments
                if (row.employee_code or "").strip()
            }
        )
        if not employee_codes:
            return {}

        effective_cutoff = self._year_month_last_day(year_month)
        rows = (
            await self.db.execute(
                select(SalaryStructure)
                .where(
                    SalaryStructure.status == "active",
                    SalaryStructure.employee_code.in_(employee_codes),
                )
                .order_by(
                    SalaryStructure.employee_code,
                    SalaryStructure.effective_date.desc(),
                    SalaryStructure.id.desc(),
                )
            )
        ).scalars().all()

        ratio_by_employee: Dict[str, float] = {}
        fallback_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            ratio = self._to_float(getattr(row, "commission_ratio", None), 0.0)
            if employee_code not in fallback_by_employee:
                fallback_by_employee[employee_code] = ratio
            if employee_code in ratio_by_employee:
                continue
            effective_date = self._coerce_date(getattr(row, "effective_date", None))
            if effective_date is not None and effective_date <= effective_cutoff:
                ratio_by_employee[employee_code] = ratio

        for employee_code, ratio in fallback_by_employee.items():
            ratio_by_employee.setdefault(employee_code, ratio)
        return ratio_by_employee

    async def calculate_month(self, year_month: str, commit: bool = True) -> Dict[str, Any]:
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("year_month format must be YYYY-MM") from exc

        assignment_rows = (
            await self.db.execute(
                select(EmployeeShopAssignment)
                .where(EmployeeShopAssignment.status == "active")
                .where(EmployeeShopAssignment.year_month == year_month)
            )
        ).scalars().all()
        if not assignment_rows:
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
                "source": "employee_shop_assignments + shop_commission_config + profit_basis_amount",
            }
        assignments = [
            SimpleNamespace(
                employee_code=getattr(row, "employee_code", None),
                platform_code=getattr(row, "platform_code", None),
                shop_id=getattr(row, "shop_id", None),
                commission_ratio=getattr(row, "commission_ratio", None),
                status=getattr(row, "status", None),
                year_month=getattr(row, "year_month", None),
            )
            for row in assignment_rows
        ]

        cfg_rows = (
            await self.db.execute(
                select(ShopCommissionConfig).where(
                    ShopCommissionConfig.year_month == year_month
                )
            )
        ).scalars().all()
        allocatable_by_shop = {
            self._shop_key(row.platform_code, row.shop_id): self._to_float(
                row.allocatable_profit_rate, 1.0
            )
            for row in cfg_rows
        }

        metrics_by_shop = await self._load_shop_metrics(year_month)
        profit_basis_by_shop = await self._load_profit_basis_by_shop(
            year_month, assignments
        )
        performance_by_shop = await self._load_store_performance_by_shop(
            year_month, assignments
        )
        attendance_adjustment_by_employee = await self._load_attendance_adjustment_by_employee(
            year_month, assignments
        )
        manual_adjustment_by_employee = await self._load_manual_adjustment_by_employee(
            year_month, assignments
        )
        input_score_by_employee = await self._load_employee_performance_input_score_by_employee(
            year_month, assignments
        )
        default_commission_ratio_by_employee = await self._load_default_commission_ratio_by_employee(
            year_month, assignments
        )

        commission_agg: Dict[str, Dict[str, float]] = {}
        performance_agg: Dict[str, Dict[str, float]] = {}
        for row in assignments:
            employee_code = (row.employee_code or "").strip()
            if not employee_code:
                continue

            shop_key = self._shop_key(row.platform_code, row.shop_id)
            metric = metrics_by_shop.get(shop_key, {})
            basis = profit_basis_by_shop.get(shop_key, {})
            score = performance_by_shop.get(shop_key, {})

            monthly_sales = self._to_float(metric.get("monthly_sales"), 0.0)
            achievement_rate = self._normalize_achievement_rate(
                metric.get("achievement_rate")
            )
            profit_basis_amount = self._to_float(
                basis.get("profit_basis_amount"), 0.0
            )
            alloc_rate = self._to_float(allocatable_by_shop.get(shop_key, 1.0), 1.0)
            alloc_profit = profit_basis_amount * alloc_rate

            # Performance aggregation: assignment means full responsibility for the shop.
            perf_rec = performance_agg.setdefault(
                employee_code,
                {
                    "sales_amount": 0.0,
                    "weighted_rate_num": 0.0,
                    "weighted_rate_den": 0.0,
                    "weighted_score_num": 0.0,
                    "weighted_score_den": 0.0,
                },
            )
            perf_rec["sales_amount"] += monthly_sales
            perf_rec["weighted_rate_num"] += achievement_rate * monthly_sales
            perf_rec["weighted_rate_den"] += monthly_sales

            if score:
                store_weight = self._to_float(score.get("sales_target"), 0.0)
                if store_weight <= 0:
                    store_weight = monthly_sales if monthly_sales > 0 else 1.0
                store_score = self._to_float(score.get("total_score"), 0.0)
                perf_rec["weighted_score_num"] += store_score * store_weight
                perf_rec["weighted_score_den"] += store_weight

            # Commission aggregation: still based on commission ratio.
            ratio = self._to_float(row.commission_ratio, 0.0)
            if ratio <= 0:
                ratio = self._to_float(
                    default_commission_ratio_by_employee.get(employee_code),
                    0.0,
                )
            if ratio <= 0:
                continue
            comm_rec = commission_agg.setdefault(
                employee_code,
                {
                    "sales_amount": 0.0,
                    "commission_amount": 0.0,
                    "weighted_rate_num": 0.0,
                    "weighted_rate_den": 0.0,
                },
            )
            sales_share = monthly_sales * ratio
            comm_rec["sales_amount"] += sales_share
            comm_rec["commission_amount"] += alloc_profit * ratio
            comm_rec["weighted_rate_num"] += achievement_rate * sales_share
            comm_rec["weighted_rate_den"] += sales_share

        commission_upserts = 0
        performance_upserts = 0

        for employee_code, rec in commission_agg.items():
            sales_amount = rec["sales_amount"]
            raw_commission_amount = rec["commission_amount"]
            if sales_amount > 0:
                commission_rate = raw_commission_amount / sales_amount
            else:
                commission_rate = 0.0
            coefficient_num = 0.0
            coefficient_den = 0.0
            for row in assignments:
                if (row.employee_code or "").strip() != employee_code:
                    continue
                ratio = self._to_float(row.commission_ratio, 0.0)
                if ratio <= 0:
                    ratio = self._to_float(
                        default_commission_ratio_by_employee.get(employee_code),
                        0.0,
                    )
                if ratio <= 0:
                    continue
                shop_key = self._shop_key(row.platform_code, row.shop_id)
                metric = metrics_by_shop.get(shop_key, {})
                monthly_sales = self._to_float(metric.get("monthly_sales"), 0.0)
                sales_share = monthly_sales * ratio
                coefficient = self._to_float(
                    performance_by_shop.get(shop_key, {}).get("performance_coefficient"),
                    1.0,
                )
                coefficient_num += coefficient * sales_share
                coefficient_den += sales_share
            inherited_coefficient = coefficient_num / coefficient_den if coefficient_den > 0 else 1.0
            commission_amount = raw_commission_amount * inherited_coefficient
            if sales_amount > 0:
                commission_rate = commission_amount / sales_amount

            comm = (
                await self.db.execute(
                    select(EmployeeCommission).where(
                        EmployeeCommission.employee_code == employee_code,
                        EmployeeCommission.year_month == year_month,
                    )
                )
            ).scalar_one_or_none()
            if comm:
                comm.sales_amount = sales_amount
                comm.commission_amount = commission_amount
                comm.commission_rate = commission_rate
                comm.calculated_at = datetime.now(timezone.utc)
            else:
                self.db.add(
                    EmployeeCommission(
                        employee_code=employee_code,
                        year_month=year_month,
                        sales_amount=sales_amount,
                        commission_amount=commission_amount,
                        commission_rate=commission_rate,
                        calculated_at=datetime.now(timezone.utc),
                    )
                )
            commission_upserts += 1

        for employee_code, rec in performance_agg.items():
            sales_amount = rec["sales_amount"]
            if rec["weighted_rate_den"] > 0:
                achievement_rate = rec["weighted_rate_num"] / rec["weighted_rate_den"]
            else:
                achievement_rate = 0.0
            if employee_code in input_score_by_employee:
                performance_score = input_score_by_employee[employee_code]
            elif rec["weighted_score_den"] > 0:
                performance_score = (
                    rec["weighted_score_num"] / rec["weighted_score_den"]
                )
            else:
                performance_score = 0.0
            performance_score += self._to_float(
                attendance_adjustment_by_employee.get(employee_code),
                0.0,
            )
            performance_score += self._to_float(
                manual_adjustment_by_employee.get(employee_code),
                0.0,
            )
            performance_score = min(max(performance_score, 0.0), 100.0)

            perf = (
                await self.db.execute(
                    select(EmployeePerformance).where(
                        EmployeePerformance.employee_code == employee_code,
                        EmployeePerformance.year_month == year_month,
                    )
                )
            ).scalar_one_or_none()
            if perf:
                perf.actual_sales = sales_amount
                perf.achievement_rate = achievement_rate
                perf.performance_score = performance_score
                perf.calculated_at = datetime.now(timezone.utc)
            else:
                self.db.add(
                    EmployeePerformance(
                        employee_code=employee_code,
                        year_month=year_month,
                        actual_sales=sales_amount,
                        achievement_rate=achievement_rate,
                        performance_score=performance_score,
                        calculated_at=datetime.now(timezone.utc),
                    )
                )
            performance_upserts += 1

        if commit:
            await self.db.commit()
        return {
            "year_month": year_month,
            "employee_count": len(performance_agg),
            "commission_upserts": commission_upserts,
            "performance_upserts": performance_upserts,
            "source": "employee_shop_assignments + employee_performance_inputs + performance_scores + shop_profit_basis",
        }

