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

import inspect
from calendar import monthrange
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional

from sqlalchemy import and_, delete, or_, select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    AttendanceRecord,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceAdjustment,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PersonalPerformanceAssignmentSnapshot,
    PersonalPerformanceEmployeeScope,
    PersonalPerformanceEntry,
    PersonalPerformancePlan,
    PerformanceScore,
    PayrollRecord,
    SalaryStructure,
    ShopCommissionConfig,
    ShopProfitBasis,
    ShopAccount,
)
from modules.core.logger import get_logger
from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics
from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from backend.services.payroll_generation_service import PayrollGenerationService

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
    def _field(record: Any, name: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    @classmethod
    def build_controlled_personal_results(
        cls,
        *,
        scopes: list[Any],
        assignments_by_employee: dict[str, list[Any]],
        metrics: list[dict[str, Any]],
        entry_scores_by_employee: dict[str, dict[str, int | None]],
        entry_details_by_employee: dict[str, dict[str, dict[str, Any]]] | None = None,
        shop_scores: dict[str, float],
    ) -> dict[str, dict[str, Any]]:
        """Return final personal rows from confirmed controlled-workbench snapshots."""
        metric_codes = [str(metric["metric_code"]) for metric in metrics]
        results: dict[str, dict[str, Any]] = {}
        entry_details_by_employee = entry_details_by_employee or {}
        for scope in scopes:
            employee_code = str(cls._field(scope, "employee_code", "")).strip()
            if not employee_code:
                continue
            if not bool(cls._field(scope, "is_included", False)):
                results[employee_code] = {
                    "performance_score": None,
                    "calculation_status": "not_participating",
                    "performance_source_type": "controlled_targets_v1",
                    "calculation_details": {
                        "source": "controlled_targets_v1",
                        "status": "not_participating",
                    },
                }
                continue

            assignments = assignments_by_employee.get(employee_code, [])
            weighted_score_numerator = 0.0
            target_weight_total = 0.0
            missing_shops: list[str] = []
            for assignment in assignments:
                platform = str(cls._field(assignment, "platform_code", "")).lower()
                shop_id = str(cls._field(assignment, "shop_id", ""))
                target = cls._to_float(
                    cls._field(assignment, "sales_target_amount_snapshot", 0), 0.0
                )
                score = shop_scores.get(cls._shop_key(platform, shop_id))
                if target <= 0 or score is None:
                    missing_shops.append(f"{platform}|{shop_id}")
                    continue
                target_weight_total += target
                weighted_score_numerator += cls._to_float(score) * target

            entry_scores = entry_scores_by_employee.get(employee_code, {})
            entry_details = entry_details_by_employee.get(employee_code, {})
            personal_target_entries = [
                {
                    "metric_code": metric_code,
                    "metric_name": metric.get("metric_name"),
                    "metric_direction": metric.get("metric_direction"),
                    "target_value": metric.get("default_target_value"),
                    "input_payload": dict(
                        (entry_details.get(metric_code) or {}).get("input_payload") or {}
                    ),
                    "max_score": metric.get("max_score"),
                    "auto_score": entry_scores.get(metric_code),
                    "formula": metric.get("guidance"),
                    "completion_status": (entry_details.get(metric_code) or {}).get(
                        "completion_status",
                        "completed" if entry_scores.get(metric_code) is not None else "pending",
                    ),
                }
                for metric, metric_code in zip(metrics, metric_codes)
            ]
            missing_metrics = [
                metric_code
                for metric_code in metric_codes
                if entry_scores.get(metric_code) is None
            ]
            if missing_shops or target_weight_total <= 0 or missing_metrics:
                results[employee_code] = {
                    "performance_score": None,
                    "calculation_status": "partial",
                    "performance_source_type": "controlled_targets_v1",
                    "calculation_details": {
                        "source": "controlled_targets_v1",
                        "status": "partial",
                        "missing_shop_scores": missing_shops,
                        "missing_personal_metrics": missing_metrics,
                        "personal_target_entries": personal_target_entries,
                    },
                }
                continue

            store_base_score = weighted_score_numerator / target_weight_total
            personal_target_score = sum(int(entry_scores[code]) for code in metric_codes)
            final_score = min(max(store_base_score * 0.8 + personal_target_score, 0.0), 100.0)
            results[employee_code] = {
                "performance_score": final_score,
                "calculation_status": "complete",
                "performance_source_type": "controlled_targets_v1",
                "calculation_details": {
                    "source": "controlled_targets_v1",
                    "status": "complete",
                    "store_base_score": store_base_score,
                    "store_weighted_contribution": store_base_score * 0.8,
                    "personal_target_score": personal_target_score,
                    "personal_metric_scores": {
                        code: int(entry_scores[code]) for code in metric_codes
                    },
                    "personal_target_entries": personal_target_entries,
                    "final_score": final_score,
                },
            }
        return results

    @staticmethod
    def partition_controlled_commission_codes(
        results: dict[str, dict[str, Any]]
    ) -> tuple[set[str], set[str]]:
        """Personal partial rows block commission; excluded rows retain independent commission."""
        blocked = {
            employee_code
            for employee_code, result in results.items()
            if result.get("calculation_status") in {"partial", "pending_scope"}
        }
        return set(results) - blocked, blocked

    async def _refresh_draft_payroll_variable_income(
        self, *, year_month: str, employee_codes: set[str]
    ) -> dict[str, Any]:
        """Remove stale controlled variable pay before applicable commission is rebuilt."""
        if not employee_codes:
            return {}
        records = (
            await self.db.execute(
                select(PayrollRecord).where(
                    PayrollRecord.year_month == year_month,
                    PayrollRecord.status == "draft",
                    PayrollRecord.employee_code.in_(employee_codes),
                )
            )
        ).scalars().all()
        for record in records:
            record.performance_salary = 0
            record.commission = 0
            PayrollGenerationService.recalculate_record_totals(record)
        return {
            str(record.employee_code).strip(): record
            for record in records
            if str(getattr(record, "employee_code", "") or "").strip()
        }

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
        return period_start.replace(
            day=monthrange(period_start.year, period_start.month)[1]
        )

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

    @classmethod
    def _is_formal_store_performance(cls, details: Dict[str, Any] | None) -> bool:
        """Only canonical formal results may feed employee income calculations."""
        summary = cls._score_details_field(details, "summary")
        return bool(
            isinstance(summary, dict)
            and summary.get("calculation_status") == "complete"
            and summary.get("ranking_pool") == "official"
            and summary.get("formal_ready") is True
        )

    async def _load_controlled_personal_context(
        self, year_month: str
    ) -> dict[str, Any] | None:
        plan = (
            await self.db.execute(
                select(PersonalPerformancePlan).where(
                    PersonalPerformancePlan.year_month == year_month
                )
            )
        ).scalar_one_or_none()
        if plan is None or getattr(plan, "calculation_mode", None) != "controlled_targets_v1":
            return None

        scopes = (
            await self.db.execute(
                select(PersonalPerformanceEmployeeScope).where(
                    PersonalPerformanceEmployeeScope.plan_id == plan.id
                )
            )
        ).scalars().all()
        scope_by_id = {row.id: row for row in scopes}
        assignments = (
            await self.db.execute(
                select(PersonalPerformanceAssignmentSnapshot).where(
                    PersonalPerformanceAssignmentSnapshot.scope_id.in_(scope_by_id)
                )
            )
        ).scalars().all() if scope_by_id else []
        assignments_by_employee: dict[str, list[Any]] = {}
        for assignment in assignments:
            scope = scope_by_id.get(assignment.scope_id)
            if scope is not None:
                assignments_by_employee.setdefault(scope.employee_code, []).append(assignment)

        entries = (
            await self.db.execute(
                select(PersonalPerformanceEntry).where(
                    PersonalPerformanceEntry.scope_id.in_(scope_by_id)
                )
            )
        ).scalars().all() if scope_by_id else []
        entry_scores_by_employee: dict[str, dict[str, int | None]] = {}
        entry_details_by_employee: dict[str, dict[str, dict[str, Any]]] = {}
        for entry in entries:
            scope = scope_by_id.get(entry.scope_id)
            if scope is not None:
                entry_scores_by_employee.setdefault(scope.employee_code, {})[
                    entry.metric_code
                ] = entry.auto_score
                entry_details_by_employee.setdefault(scope.employee_code, {})[
                    entry.metric_code
                ] = {
                    "input_payload": getattr(entry, "input_payload", None) or {},
                    "completion_status": getattr(entry, "completion_status", None),
                }

        score_rows = (
            await self.db.execute(
                select(PerformanceScore).where(PerformanceScore.period == year_month)
            )
        ).scalars().all()
        shop_scores = {
            self._shop_key(row.platform_code, row.shop_id): self._to_float(
                row.total_score
            )
            for row in score_rows
            if self._is_formal_store_performance(getattr(row, "score_details", None))
        }
        return {
            "scope_confirmed": getattr(plan, "scope_confirmed_at", None) is not None,
            "scopes": scopes,
            "assignments_by_employee": assignments_by_employee,
            "metrics": list((getattr(plan, "rule_snapshot", {}) or {}).get("metrics", [])),
            "entry_scores_by_employee": entry_scores_by_employee,
            "entry_details_by_employee": entry_details_by_employee,
            "shop_scores": shop_scores,
        }

    @staticmethod
    def _normalize_metric_direction(direction: Any) -> str:
        normalized = str(direction or "").strip().lower()
        if normalized in {"up", "higher", "higher_better", "gte", "maximize", "max"}:
            return "up"
        if normalized in {"down", "lower", "lower_better", "lte", "minimize", "min"}:
            return "down"
        return "up"

    @classmethod
    def _calculate_input_metric_score(cls, row: Any) -> float | None:
        max_score = cls._to_float(getattr(row, "max_score", None), 0.0)
        if max_score <= 0:
            return None

        manual_enabled = bool(getattr(row, "manual_score_enabled", False))
        manual_score_value = getattr(row, "manual_score_value", None)
        if manual_enabled or getattr(row, "metric_direction", None) == "manual_score":
            if manual_score_value is None:
                return None
            return min(max(cls._to_float(manual_score_value, 0.0), 0.0), max_score)

        if getattr(row, "achieved_value", None) is None:
            return None

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
            return None
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
        shop_keys = {
            self._shop_key(row.platform_code, row.shop_id): (
                (row.platform_code or "").lower(),
                row.shop_id,
            )
            for row in assignments
        }
        basis_by_shop: Dict[str, Dict[str, float]] = {}

        snapshot_rows = (
            (
                await self.db.execute(
                    select(ShopProfitBasis).where(
                        ShopProfitBasis.period_month == year_month,
                        ShopProfitBasis.basis_version == LaborCostPolicyService.V2,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in snapshot_rows:
            if getattr(row, "basis_version", None) != LaborCostPolicyService.V2:
                continue
            key = self._shop_key(
                getattr(row, "platform_code", None),
                getattr(row, "shop_id", None),
            )
            if key not in shop_keys:
                continue
            basis_by_shop[key] = {
                "profit_basis_amount": self._to_float(
                    getattr(row, "profit_basis_amount", 0.0),
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

        platform_codes = sorted(
            {platform_code for platform_code, _ in shop_keys.values()}
        )
        shop_ids = sorted({shop_id for _, shop_id in shop_keys.values()})
        rows = (
            (
                await self.db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.period == year_month,
                        PerformanceScore.platform_code.in_(platform_codes),
                        PerformanceScore.shop_id.in_(shop_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

        performance_by_shop: Dict[str, Dict[str, float]] = {}
        for row in rows:
            details = getattr(row, "score_details", None) or {}
            total_score = getattr(row, "total_score", None)
            if total_score is None:
                continue
            if not self._is_formal_store_performance(details):
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
    ) -> tuple[Dict[str, float], set[str]]:
        employee_codes = sorted(
            {
                (row.employee_code or "").strip()
                for row in assignments
                if (row.employee_code or "").strip()
            }
        )
        if not employee_codes:
            return {}, set()

        period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
        if period_start.month == 12:
            next_month = period_start.replace(
                year=period_start.year + 1, month=1, day=1
            )
        else:
            next_month = period_start.replace(month=period_start.month + 1, day=1)

        try:
            # A failed ORM probe must not roll back pending shop-performance rows
            # held by the outer monthly settlement transaction.
            nested_transaction = self.db.begin_nested()
            if inspect.isawaitable(nested_transaction):
                # AsyncSession.begin_nested() is synchronous.  This branch keeps
                # lightweight session doubles usable without changing production
                # transaction semantics.
                nested_transaction.close()
                rows = (
                    (
                        await self.db.execute(
                            select(AttendanceRecord).where(
                                AttendanceRecord.employee_code.in_(employee_codes),
                                AttendanceRecord.attendance_date >= period_start,
                                AttendanceRecord.attendance_date < next_month,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            else:
                async with nested_transaction:
                    rows = (
                        (
                            await self.db.execute(
                                select(AttendanceRecord).where(
                                    AttendanceRecord.employee_code.in_(employee_codes),
                                    AttendanceRecord.attendance_date >= period_start,
                                    AttendanceRecord.attendance_date < next_month,
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
        except Exception:
            rows = (
                (
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
                )
                .mappings()
                .all()
            )

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
            adjustment_by_employee[employee_code] = (
                adjustment_by_employee.get(employee_code, 0.0) + delta
            )
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
            (
                await self.db.execute(
                    select(EmployeePerformanceAdjustment).where(
                        EmployeePerformanceAdjustment.year_month == year_month,
                        EmployeePerformanceAdjustment.status == "active",
                        EmployeePerformanceAdjustment.employee_code.in_(employee_codes),
                    )
                )
            )
            .scalars()
            .all()
        )

        adjustment_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            delta = self._to_float(getattr(row, "score_delta", None), 0.0)
            adjustment_by_employee[employee_code] = (
                adjustment_by_employee.get(employee_code, 0.0) + delta
            )
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
            (
                await self.db.execute(
                    select(EmployeePerformanceInput).where(
                        EmployeePerformanceInput.year_month == year_month,
                        EmployeePerformanceInput.status == "active",
                        EmployeePerformanceInput.employee_code.in_(employee_codes),
                    )
                )
            )
            .scalars()
            .all()
        )

        score_by_employee: Dict[str, float] = {}
        pending_employee_codes: set[str] = set()
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            metric_score = self._calculate_input_metric_score(row)
            if metric_score is None:
                pending_employee_codes.add(employee_code)
                continue
            score_by_employee[employee_code] = (
                score_by_employee.get(employee_code, 0.0) + metric_score
            )
        return {
            employee_code: min(max(score, 0.0), 100.0)
            for employee_code, score in score_by_employee.items()
            if employee_code not in pending_employee_codes
        }, pending_employee_codes

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
            (
                await self.db.execute(
                    select(SalaryStructure)
                    .where(
                        SalaryStructure.status == "active",
                        SalaryStructure.employee_code.in_(employee_codes),
                        SalaryStructure.effective_date <= effective_cutoff,
                    )
                    .order_by(
                        SalaryStructure.employee_code,
                        SalaryStructure.effective_date.desc(),
                        SalaryStructure.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )

        ratio_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            ratio = self._to_float(getattr(row, "commission_ratio", None), 0.0)
            if employee_code in ratio_by_employee:
                continue
            effective_date = self._coerce_date(getattr(row, "effective_date", None))
            if effective_date is not None and effective_date <= effective_cutoff:
                ratio_by_employee[employee_code] = ratio
        return ratio_by_employee

    async def calculate_month(
        self,
        year_month: str,
        commit: bool = True,
        eligible_shop_keys: set[str] | None = None,
    ) -> Dict[str, Any]:
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("year_month format must be YYYY-MM") from exc

        period_lock = PayrollPeriodLockService(self.db)
        await period_lock.acquire_month_transaction_lock(year_month=year_month)
        await period_lock.assert_month_mutable(year_month=year_month)
        controlled_context = await self._load_controlled_personal_context(year_month)

        assignment_rows = (
            (
                await self.db.execute(
                    select(EmployeeShopAssignment)
                    .join(
                        ShopAccount,
                        and_(
                            func.lower(ShopAccount.platform)
                            == func.lower(EmployeeShopAssignment.platform_code),
                            ShopAccount.enabled.is_(True),
                            ShopAccount.business_role == "operating_store",
                            or_(
                                ShopAccount.platform_shop_id
                                == EmployeeShopAssignment.shop_id,
                                ShopAccount.shop_account_id
                                == EmployeeShopAssignment.shop_id,
                            ),
                        ),
                    )
                    .where(EmployeeShopAssignment.status == "active")
                    .where(EmployeeShopAssignment.year_month == year_month)
                )
            )
            .scalars()
            .all()
        )
        if eligible_shop_keys is not None:
            normalized_eligible_shop_keys = {
                str(key).strip().lower() for key in eligible_shop_keys
            }
            assignment_rows = [
                row
                for row in assignment_rows
                if self._shop_key(
                    getattr(row, "platform_code", None),
                    getattr(row, "shop_id", None),
                )
                in normalized_eligible_shop_keys
            ]
        input_population_rows = (
            (
                await self.db.execute(
                    select(EmployeePerformanceInput).where(
                        EmployeePerformanceInput.year_month == year_month,
                        EmployeePerformanceInput.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        salary_population_rows = (
            (
                await self.db.execute(
                    select(SalaryStructure).where(
                        SalaryStructure.status == "active",
                        SalaryStructure.effective_date
                        <= self._year_month_last_day(year_month),
                    )
                )
            )
            .scalars()
            .all()
        )
        population_codes = {
            str(getattr(row, "employee_code", "") or "").strip()
            for row in [
                *assignment_rows,
                *input_population_rows,
                *salary_population_rows,
            ]
            if str(getattr(row, "employee_code", "") or "").strip()
        }
        if controlled_context is not None:
            population_codes.update(
                str(getattr(scope, "employee_code", "") or "").strip()
                for scope in controlled_context["scopes"]
                if str(getattr(scope, "employee_code", "") or "").strip()
            )
        if not population_codes:
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
                "formal_employee_codes": [],
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
        assigned_codes = {
            str(row.employee_code or "").strip()
            for row in assignments
            if str(row.employee_code or "").strip()
        }
        employee_rows = [
            *assignments,
            *[
                SimpleNamespace(employee_code=employee_code)
                for employee_code in sorted(population_codes - assigned_codes)
            ],
        ]

        cfg_rows = (
            (
                await self.db.execute(
                    select(ShopCommissionConfig).where(
                        ShopCommissionConfig.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
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
        attendance_adjustment_by_employee = (
            await self._load_attendance_adjustment_by_employee(
                year_month, employee_rows
            )
        )
        manual_adjustment_by_employee = await self._load_manual_adjustment_by_employee(
            year_month, employee_rows
        )
        input_score_by_employee, pending_input_employee_codes = (
            await self._load_employee_performance_input_score_by_employee(
                year_month, employee_rows
            )
        )
        default_commission_ratio_by_employee = (
            await self._load_default_commission_ratio_by_employee(
                year_month, employee_rows
            )
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
            profit_basis_amount = self._to_float(basis.get("profit_basis_amount"), 0.0)
            alloc_rate = self._to_float(allocatable_by_shop.get(shop_key, 1.0), 1.0)
            alloc_profit = max(profit_basis_amount, 0.0) * alloc_rate

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

        for employee_code in population_codes:
            performance_agg.setdefault(
                employee_code,
                {
                    "sales_amount": 0.0,
                    "weighted_rate_num": 0.0,
                    "weighted_rate_den": 0.0,
                    "weighted_score_num": 0.0,
                    "weighted_score_den": 0.0,
                },
            )

        commission_upserts = 0
        performance_upserts = 0
        commission_allocations: list[dict[str, Any]] = []
        formal_employee_codes: set[str] = set()
        controlled_results: dict[str, dict[str, Any]] = {}
        blocked_commission_codes: set[str] = set()
        refreshed_draft_payrolls: dict[str, Any] = {}
        if controlled_context is not None:
            if controlled_context["scope_confirmed"]:
                controlled_results = self.build_controlled_personal_results(
                    scopes=controlled_context["scopes"],
                    assignments_by_employee=controlled_context["assignments_by_employee"],
                    metrics=controlled_context["metrics"],
                    entry_scores_by_employee=controlled_context["entry_scores_by_employee"],
                    entry_details_by_employee=controlled_context["entry_details_by_employee"],
                    shop_scores=controlled_context["shop_scores"],
                )
            else:
                controlled_results = {
                    employee_code: {
                        "performance_score": None,
                        "calculation_status": "pending_scope",
                        "performance_source_type": "controlled_targets_v1",
                        "calculation_details": {
                            "source": "controlled_targets_v1",
                            "status": "pending_scope",
                            "message": "personal performance scope is not confirmed",
                        },
                    }
                    for employee_code in assigned_codes
                }
            _, blocked_commission_codes = self.partition_controlled_commission_codes(
                controlled_results
            )
            refreshed_draft_payrolls = await self._refresh_draft_payroll_variable_income(
                year_month=year_month,
                employee_codes={
                    employee_code
                    for employee_code, result in controlled_results.items()
                    if result.get("calculation_status")
                    in {"partial", "pending_scope", "not_participating"}
                },
            )
            if blocked_commission_codes:
                await self.db.execute(
                    delete(EmployeeCommission).where(
                        EmployeeCommission.year_month == year_month,
                        EmployeeCommission.employee_code.in_(blocked_commission_codes),
                    )
                )

        for employee_code, rec in commission_agg.items():
            if employee_code in blocked_commission_codes:
                continue
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
                    performance_by_shop.get(shop_key, {}).get(
                        "performance_coefficient"
                    ),
                    1.0,
                )
                coefficient_num += coefficient * sales_share
                coefficient_den += sales_share
            inherited_coefficient = (
                coefficient_num / coefficient_den if coefficient_den > 0 else 1.0
            )
            commission_amount = raw_commission_amount * inherited_coefficient
            if sales_amount > 0:
                commission_rate = commission_amount / sales_amount

            refreshed_payroll = refreshed_draft_payrolls.get(employee_code)
            if refreshed_payroll is not None:
                refreshed_payroll.commission = commission_amount
                PayrollGenerationService.recalculate_record_totals(refreshed_payroll)

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
                profit_basis_amount = self._to_float(
                    profit_basis_by_shop.get(shop_key, {}).get("profit_basis_amount"),
                    0.0,
                )
                alloc_rate = self._to_float(
                    allocatable_by_shop.get(shop_key, 1.0),
                    1.0,
                )
                commission_allocations.append(
                    {
                        "employee_code": employee_code,
                        "platform_code": str(row.platform_code or "").lower(),
                        "shop_id": row.shop_id,
                        "commission_amount": max(profit_basis_amount, 0.0)
                        * alloc_rate
                        * ratio
                        * inherited_coefficient,
                    }
                )

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

        if controlled_context is not None:
            # A controlled month has one authoritative personal population: its scope.
            # Live assignments may still feed independent commission, never personal scores.
            controlled_scope_codes = {
                str(getattr(scope, "employee_code", "") or "").strip()
                for scope in controlled_context["scopes"]
                if str(getattr(scope, "employee_code", "") or "").strip()
            }
            performance_agg = {
                employee_code: aggregate
                for employee_code, aggregate in performance_agg.items()
                if employee_code in controlled_scope_codes
            }

        for employee_code, rec in (
            performance_agg.items() if controlled_context is None else ()
        ):
            sales_amount = rec["sales_amount"]
            if rec["weighted_rate_den"] > 0:
                achievement_rate = rec["weighted_rate_num"] / rec["weighted_rate_den"]
            else:
                achievement_rate = 0.0
            calculation_status = "complete"
            performance_source_type = "shop_inherited"
            if employee_code in input_score_by_employee:
                performance_score = input_score_by_employee[employee_code]
                performance_source_type = "personal_inputs"
            elif rec["weighted_score_den"] > 0:
                performance_score = (
                    rec["weighted_score_num"] / rec["weighted_score_den"]
                )
            elif employee_code in pending_input_employee_codes:
                performance_score = None
                calculation_status = "pending_personal_input"
            else:
                performance_score = None
                calculation_status = (
                    "pending_store_performance"
                    if employee_code in assigned_codes
                    else "pending_personal_input"
                )
                performance_source_type = "pending"
            if performance_score is not None:
                performance_score += self._to_float(
                    attendance_adjustment_by_employee.get(employee_code),
                    0.0,
                )
                performance_score += self._to_float(
                    manual_adjustment_by_employee.get(employee_code),
                    0.0,
                )
                performance_score = min(max(performance_score, 0.0), 100.0)
                if calculation_status == "complete":
                    formal_employee_codes.add(employee_code)

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
                perf.calculation_status = calculation_status
                perf.performance_source_type = performance_source_type
                perf.calculated_at = datetime.now(timezone.utc)
            else:
                self.db.add(
                    EmployeePerformance(
                        employee_code=employee_code,
                        year_month=year_month,
                        actual_sales=sales_amount,
                        achievement_rate=achievement_rate,
                        performance_score=performance_score,
                        calculation_status=calculation_status,
                        performance_source_type=performance_source_type,
                        calculated_at=datetime.now(timezone.utc),
                    )
                )
            performance_upserts += 1

        if controlled_context is not None:
            formal_employee_codes.clear()
            if controlled_context["scope_confirmed"]:
                scope_codes = {
                    str(getattr(scope, "employee_code", "") or "").strip()
                    for scope in controlled_context["scopes"]
                    if str(getattr(scope, "employee_code", "") or "").strip()
                }
                await self.db.execute(
                    delete(EmployeePerformance).where(
                        EmployeePerformance.year_month == year_month,
                        EmployeePerformance.employee_code.not_in(scope_codes),
                    )
                )
            for employee_code, result in controlled_results.items():
                inherited = performance_agg.get(employee_code, {})
                sales_amount = self._to_float(inherited.get("sales_amount"), 0.0)
                rate_den = self._to_float(inherited.get("weighted_rate_den"), 0.0)
                achievement_rate = (
                    self._to_float(inherited.get("weighted_rate_num"), 0.0) / rate_den
                    if rate_den > 0
                    else 0.0
                )
                perf = (
                    await self.db.execute(
                        select(EmployeePerformance).where(
                            EmployeePerformance.employee_code == employee_code,
                            EmployeePerformance.year_month == year_month,
                        )
                    )
                ).scalar_one_or_none()
                if perf is None:
                    perf = EmployeePerformance(
                        employee_code=employee_code,
                        year_month=year_month,
                        actual_sales=sales_amount,
                        achievement_rate=achievement_rate,
                        performance_score=result["performance_score"],
                        calculation_status=result["calculation_status"],
                        performance_source_type=result["performance_source_type"],
                        calculation_details=result["calculation_details"],
                        calculated_at=datetime.now(timezone.utc),
                    )
                    self.db.add(perf)
                else:
                    perf.actual_sales = sales_amount
                    perf.achievement_rate = achievement_rate
                    perf.performance_score = result["performance_score"]
                    perf.calculation_status = result["calculation_status"]
                    perf.performance_source_type = result["performance_source_type"]
                    perf.calculation_details = result["calculation_details"]
                    perf.calculated_at = datetime.now(timezone.utc)
                if result["calculation_status"] == "complete":
                    formal_employee_codes.add(employee_code)
                performance_upserts += 1

        if commit:
            await period_lock.assert_month_mutable(year_month=year_month)
            await self.db.commit()
        return {
            "year_month": year_month,
            "employee_count": len(performance_agg),
            "commission_upserts": commission_upserts,
            "performance_upserts": performance_upserts,
            "formal_employee_codes": sorted(formal_employee_codes),
            "payroll_refresh_employee_codes": sorted(
                set(formal_employee_codes)
                | {
                    employee_code
                    for employee_code, result in controlled_results.items()
                    if result.get("calculation_status") == "not_participating"
                }
            ),
            "commission_allocations": commission_allocations,
            "source": (
                "controlled_targets_v1"
                if controlled_context is not None
                else "employee_shop_assignments + employee_performance_inputs + performance_scores + shop_profit_basis"
            ),
        }
