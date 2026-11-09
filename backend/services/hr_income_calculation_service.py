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
from typing import Any, Dict, Mapping, Optional

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
from backend.services.commission_reason_service import commission_zero_reason
from backend.services.performance_coefficient import (
    calculate_score_coefficient,
    calculate_settlement_coefficient,
    describe_settlement_coefficient,
)

logger = get_logger(__name__)


def _absorb_commission_rounding_residue(
    shop_coefficients: list[dict[str, Any]],
    total_amount: float,
) -> None:
    """把逐店舍入产生的尾差并到金额最大的那家店。

    提成总额的口径是「各店未舍入金额累加后统一舍入一次」，
    而逐店明细各自舍入后再相加可能差 1 分。这笔尾差必须有归属，
    否则运营在页面上按店加起来永远对不上工资单。

    这里**只调整逐店明细的展示值**，不碰总额、不碰工资单。
    """
    if not shop_coefficients:
        return
    total_rounded = round(float(total_amount or 0.0), 2)
    displayed_sum = round(
        sum(float(item.get("commission_amount") or 0.0) for item in shop_coefficients),
        2,
    )
    residue = round(total_rounded - displayed_sum, 2)
    if abs(residue) < 0.005:
        return
    target = max(
        shop_coefficients,
        key=lambda item: float(item.get("commission_amount") or 0.0),
    )
    target["commission_amount"] = round(
        float(target.get("commission_amount") or 0.0) + residue, 2
    )


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
    def _require_complete_profit_basis(shop_key: str, basis: Dict[str, Any]) -> None:
        if str(basis.get("cost_status") or "").lower() in {
            "missing_labor_allocation",
            "pending_labor_allocation",
            "data_incomplete",
        }:
            raise ValueError(
                f"missing labor allocation for V2 profit basis: {shop_key}"
            )

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
                        (entry_details.get(metric_code) or {}).get("input_payload")
                        or {}
                    ),
                    "max_score": metric.get("max_score"),
                    "auto_score": entry_scores.get(metric_code),
                    "formula": metric.get("guidance"),
                    "completion_status": (entry_details.get(metric_code) or {}).get(
                        "completion_status",
                        (
                            "completed"
                            if entry_scores.get(metric_code) is not None
                            else "pending"
                        ),
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
            personal_target_score = sum(
                int(entry_scores[code]) for code in metric_codes
            )
            final_score = min(
                max(store_base_score * 0.8 + personal_target_score, 0.0), 100.0
            )
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
        results: dict[str, dict[str, Any]],
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
            (
                await self.db.execute(
                    select(PayrollRecord).where(
                        PayrollRecord.year_month == year_month,
                        PayrollRecord.status == "draft",
                        PayrollRecord.employee_code.in_(employee_codes),
                    )
                )
            )
            .scalars()
            .all()
        )
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
        if (
            plan is None
            or getattr(plan, "calculation_mode", None) != "controlled_targets_v1"
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
        scope_by_id = {row.id: row for row in scopes}
        assignments = (
            (
                await self.db.execute(
                    select(PersonalPerformanceAssignmentSnapshot).where(
                        PersonalPerformanceAssignmentSnapshot.scope_id.in_(scope_by_id)
                    )
                )
            )
            .scalars()
            .all()
            if scope_by_id
            else []
        )
        assignments_by_employee: dict[str, list[Any]] = {}
        for assignment in assignments:
            scope = scope_by_id.get(assignment.scope_id)
            if scope is not None:
                assignments_by_employee.setdefault(scope.employee_code, []).append(
                    assignment
                )

        entries = (
            (
                await self.db.execute(
                    select(PersonalPerformanceEntry).where(
                        PersonalPerformanceEntry.scope_id.in_(scope_by_id)
                    )
                )
            )
            .scalars()
            .all()
            if scope_by_id
            else []
        )
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
            (
                await self.db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.period == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
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
            "metrics": list(
                (getattr(plan, "rule_snapshot", {}) or {}).get("metrics", [])
            ),
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
                        ShopProfitBasis.basis_version.in_(
                            LaborCostPolicyService.KNOWN_BASIS_VERSIONS
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in snapshot_rows:
            # 只认「结算基数口径」的快照（当前口径 + 历史同口径版本）；
            # 「仅 A 类成本」的历史快照不参与工资与提成计算。
            if LaborCostPolicyService.is_legacy_a_only_basis_version(
                getattr(row, "basis_version", None)
            ):
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
                ),
                "cost_status": str(
                    getattr(row, "cost_status", "missing_labor_allocation")
                    or "missing_labor_allocation"
                ),
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

    def _resolve_commission_ratio(
        self,
        row: Any,
        *,
        employee_code: str,
        default_commission_ratio_by_employee: Mapping[str, float],
    ) -> tuple[float, str]:
        """解析「这个员工在这个店铺」的提成比例，返回 ``(比例, 来源)``。

        比例有**两个来源**，权威性不同：

        1. ``a_class.employee_shop_assignments.commission_ratio`` —— **权威来源**。
           它是「谁负责哪个店、这个店给他多少提成比例」的正式定义（可为空）。
        2. ``a_class.salary_structures.commission_ratio`` —— **员工级兜底**。
           归属行没填比例时用它；它是薪资结构上的默认值（NOT NULL DEFAULT 0）。

        以前这段「先取归属行、取不到再取薪资结构」的逻辑被**抄了三遍**
        （金额聚合 / 系数加权 / 店铺分摊），改一处必漏两处 ⇒ 现在收敛成一个方法。

        来源标记会写进 ``calculation_details``，让「这个人的提成比例到底哪来的」
        可审计 —— 之前完全看不出来，只能靠猜。
        """
        ratio = self._to_float(getattr(row, "commission_ratio", None), 0.0)
        if ratio > 0:
            return ratio, "shop_assignment"
        fallback = self._to_float(
            default_commission_ratio_by_employee.get(employee_code), 0.0
        )
        if fallback > 0:
            return fallback, "salary_structure_fallback"
        return 0.0, "missing"

    def _resolve_employee_performance_profile(
        self,
        employee_code: str,
        *,
        agg: Dict[str, Any],
        input_score_by_employee: Mapping[str, float],
        pending_input_employee_codes: set[str],
        assigned_codes: set[str],
        controlled_mode: bool,
        controlled_result: Optional[Dict[str, Any]] = None,
        attendance_adjustment_by_employee: Optional[Mapping[str, float]] = None,
        manual_adjustment_by_employee: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, Any]:
        """解析一个人当月的绩效画像：分数 / 状态 / 来源 / 分数档位系数。

        提成和绩效工资必须用**同一个**分数档位系数，所以这里只解析一次，
        两个口子共用同一份画像 —— 否则就会出现「提成按 A 系数、绩效工资按 B 系数」。

        返回::

            {
                "performance_score": float | None,
                "calculation_status": str,
                "performance_source_type": str,
                "score_coefficient": float | None,   # 个人分数档位系数
            }
        """
        attendance_adjustment_by_employee = attendance_adjustment_by_employee or {}
        manual_adjustment_by_employee = manual_adjustment_by_employee or {}

        performance_score: Optional[float]
        if controlled_mode:
            if controlled_result is None:
                # 受控月份里不在个人考核范围内的人：不参与考核，
                # 没有个人分数，也就没有「个人分数档位系数」这一层约束。
                performance_score = None
                calculation_status = "not_participating"
                performance_source_type = "controlled_targets_v1"
            else:
                performance_score = controlled_result.get("performance_score")
                calculation_status = str(
                    controlled_result.get("calculation_status") or "pending_scope"
                )
                performance_source_type = str(
                    controlled_result.get("performance_source_type")
                    or "controlled_targets_v1"
                )
        else:
            calculation_status = "complete"
            performance_source_type = "shop_inherited"
            if employee_code in input_score_by_employee:
                performance_score = input_score_by_employee[employee_code]
                performance_source_type = "personal_inputs"
            elif self._to_float(agg.get("weighted_score_den"), 0.0) > 0:
                performance_score = self._to_float(
                    agg.get("weighted_score_num"), 0.0
                ) / self._to_float(agg.get("weighted_score_den"), 0.0)
            elif employee_code in pending_input_employee_codes:
                performance_score = None
                calculation_status = "pending_personal_input"
            else:
                performance_score = None
                if employee_code in assigned_codes:
                    calculation_status = "pending_store_performance"
                    performance_source_type = "pending"
                else:
                    # 既没有店铺归属，也没有个人绩效录入：明确记为「不参与考核」。
                    # 这类人（如总部、仓库、客服）不阻断整月结算，工资照常确认。
                    calculation_status = "not_participating"
                    performance_source_type = "not_participating"

        if performance_score is not None:
            performance_score += self._to_float(
                attendance_adjustment_by_employee.get(employee_code), 0.0
            )
            performance_score += self._to_float(
                manual_adjustment_by_employee.get(employee_code), 0.0
            )
            performance_score = min(max(performance_score, 0.0), 100.0)

        score_coefficient = (
            calculate_score_coefficient(performance_score)
            if performance_score is not None
            else None
        )
        return {
            "performance_score": performance_score,
            "calculation_status": calculation_status,
            "performance_source_type": performance_source_type,
            "score_coefficient": score_coefficient,
        }

    async def build_settlement_preview(self, year_month: str) -> Dict[str, Any]:
        """结算预览：谁在哪家店、系数多少、预计拿到多少钱。

        **只读，不写库。** 页面上的钱一律以这里为准 ——
        前端不再自己算「可分配利润 × 提成比例 × 系数」。

        数据来源与 :meth:`calculate_month` 完全一致：

        * 已算好的个人绩效（``c_class.employee_performance``）→ 个人分数档位系数
        * 已算好的店铺绩效（``c_class.performance_scores``）→ 店铺结算系数
        * 利润基数（``finance.shop_profit_basis``）+ 可分配率配置 → 可分配利润
        * 归属关系（``a_class.employee_shop_assignments``）→ 归属提成比

        返回结构::

            {
              "year_month": "2026-10",
              "employees": [
                {
                  "employee_code": "EMP260001",
                  "performance_score": 85.0,
                  "score_coefficient": 1.0,
                  "settlement_coefficient": 1.0,
                  "calculation_status": "complete",
                  "expected_commission": 279.15,
                  "shops": [
                    {
                      "platform_code": "shopee",
                      "shop_id": "1407964586",
                      "commission_ratio": 0.5,
                      "allocatable_profit_rate": 0.25,
                      "allocatable_profit_amount": 120.0,
                      "profit_basis_amount": 480.0,
                      "shop_coefficient": 1.0,
                      "settlement_coefficient": 1.0,
                      "estimated_commission": 60.0,
                      "commission_zero_reason": null
                    }
                  ]
                }
              ]
            }
        """
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
        assignments = [
            SimpleNamespace(
                employee_code=getattr(row, "employee_code", None),
                platform_code=getattr(row, "platform_code", None),
                shop_id=getattr(row, "shop_id", None),
                commission_ratio=getattr(row, "commission_ratio", None),
            )
            for row in assignment_rows
        ]
        if not assignments:
            return {"year_month": year_month, "employees": []}

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
                row.allocatable_profit_rate, 0.0
            )
            for row in cfg_rows
        }
        profit_basis_by_shop = await self._load_profit_basis_by_shop(
            year_month, assignments
        )
        performance_by_shop = await self._load_store_performance_by_shop(
            year_month, assignments
        )
        # 店铺级考核状态（「本月不参与考核」「亏损」「待补数据」）——
        # 前端要靠它区分「这家店没参与考核」和「这家店参与考核但没分钱」。
        shop_status_by_key: Dict[str, Dict[str, Any]] = {}
        for score_row in (
            (
                await self.db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.period == year_month
                    )
                )
            )
            .scalars()
            .all()
        ):
            details = getattr(score_row, "score_details", None) or {}
            summary = details.get("summary", {}) if isinstance(details, dict) else {}
            profit_detail = (
                details.get("profit", {}) if isinstance(details, dict) else {}
            )
            shop_status_by_key[
                self._shop_key(score_row.platform_code, score_row.shop_id)
            ] = {
                "calculation_status": str(summary.get("calculation_status") or ""),
                "profit_status": str((profit_detail or {}).get("status") or ""),
                "ranking_pool": str(summary.get("ranking_pool") or ""),
                "message": str(summary.get("message") or ""),
                "total_score": self._to_float(
                    getattr(score_row, "total_score", None), 0.0
                ),
                "rank": getattr(score_row, "rank", None),
                "shop_coefficient": (
                    self._to_float(
                        getattr(score_row, "performance_coefficient", None), 1.0
                    )
                    if getattr(score_row, "performance_coefficient", None) is not None
                    else None
                ),
            }
        default_commission_ratio_by_employee = (
            await self._load_default_commission_ratio_by_employee(
                year_month, assignments
            )
        )

        employee_codes = sorted(
            {
                str(row.employee_code or "").strip()
                for row in assignments
                if str(row.employee_code or "").strip()
            }
        )
        performance_rows = (
            (
                await self.db.execute(
                    select(EmployeePerformance).where(
                        EmployeePerformance.year_month == year_month,
                        EmployeePerformance.employee_code.in_(employee_codes),
                    )
                )
            )
            .scalars()
            .all()
        )
        performance_by_employee = {
            str(row.employee_code or "").strip(): row for row in performance_rows
        }

        by_employee: Dict[str, Dict[str, Any]] = {}
        for row in assignments:
            employee_code = str(row.employee_code or "").strip()
            if not employee_code:
                continue
            ratio, ratio_source = self._resolve_commission_ratio(
                row,
                employee_code=employee_code,
                default_commission_ratio_by_employee=default_commission_ratio_by_employee,
            )
            shop_key = self._shop_key(row.platform_code, row.shop_id)
            profit_basis_amount = self._to_float(
                profit_basis_by_shop.get(shop_key, {}).get("profit_basis_amount"),
                0.0,
            )
            alloc_rate = self._to_float(allocatable_by_shop.get(shop_key, 0.0), 0.0)
            # 「可分配利润」展示值保留 2 位小数，但**计算提成用未舍入的值** ——
            # 后端算提成时中间步骤不舍入，只在最后对合计舍入。
            # 中间多舍一次，页面就会比工资单多 1 分钱。
            allocatable_profit_exact = max(profit_basis_amount, 0.0) * alloc_rate
            allocatable_profit_amount = round(allocatable_profit_exact, 2)
            shop_coefficient = self._to_float(
                performance_by_shop.get(shop_key, {}).get("performance_coefficient"),
                1.0,
            )

            employee_perf = performance_by_employee.get(employee_code)
            performance_score = getattr(employee_perf, "performance_score", None)
            score_coefficient = (
                calculate_score_coefficient(performance_score)
                if performance_score is not None
                else None
            )
            settlement = describe_settlement_coefficient(
                shop_coefficient=shop_coefficient,
                score_coefficient=score_coefficient,
            )
            settlement_coefficient = settlement["settlement_coefficient"]
            estimated_commission = round(
                allocatable_profit_exact * ratio * settlement_coefficient, 2
            )

            entry = by_employee.setdefault(
                employee_code,
                {
                    "employee_code": employee_code,
                    "performance_score": performance_score,
                    "score_coefficient": score_coefficient,
                    "settlement_coefficient": settlement_coefficient,
                    "calculation_status": str(
                        getattr(employee_perf, "calculation_status", "") or ""
                    ),
                    "performance_source_type": str(
                        getattr(employee_perf, "performance_source_type", "") or ""
                    ),
                    "expected_commission": 0.0,
                    "shops": [],
                },
            )
            entry["shops"].append(
                {
                    "platform_code": str(row.platform_code or "").lower(),
                    "shop_id": row.shop_id,
                    "commission_ratio": round(ratio, 6),
                    "commission_ratio_source": ratio_source,
                    "allocatable_profit_rate": round(alloc_rate, 6),
                    "allocatable_profit_amount": allocatable_profit_amount,
                    "profit_basis_amount": round(profit_basis_amount, 2),
                    "shop_coefficient": shop_coefficient,
                    "settlement_coefficient": settlement_coefficient,
                    "estimated_commission": estimated_commission,
                    "calculation_status": (
                        shop_status_by_key.get(shop_key, {}).get("calculation_status")
                        or ""
                    ),
                    "profit_status": (
                        shop_status_by_key.get(shop_key, {}).get("profit_status") or ""
                    ),
                    "ranking_pool": (
                        shop_status_by_key.get(shop_key, {}).get("ranking_pool") or ""
                    ),
                    "shop_total_score": shop_status_by_key.get(shop_key, {}).get(
                        "total_score"
                    ),
                    "shop_rank": shop_status_by_key.get(shop_key, {}).get("rank"),
                    "commission_zero_reason": commission_zero_reason(
                        is_rate_configured=shop_key in allocatable_by_shop,
                        allocatable_rate=alloc_rate,
                        profit_basis_amount=profit_basis_amount,
                        # 必须把实际算出来的预计提成传进去：有提成时不能报「提成为 0」
                        estimated_total_commission=estimated_commission,
                        has_assignment=True,
                        cost_status=profit_basis_by_shop.get(shop_key, {}).get(
                            "cost_status"
                        )
                        or "missing_labor_allocation",
                        commission_ratio=ratio,
                    )
                    or (
                        "本店本月结算利润为 0，暂不产生提成"
                        if estimated_commission <= 0
                        else None
                    ),
                }
            )
            # 合计要「先累加未舍入值、最后舍入一次」，与后端一致。
            # 每家店都 round 一次再累加，会和工资单差 1 分钱。
            entry["expected_commission_raw"] = (
                self._to_float(entry.get("expected_commission_raw"), 0.0)
                + allocatable_profit_exact * ratio * settlement_coefficient
            )

        employees = sorted(by_employee.values(), key=lambda item: item["employee_code"])
        for entry in employees:
            entry["expected_commission"] = round(
                self._to_float(entry.pop("expected_commission_raw", 0.0), 0.0), 2
            )
        return {"year_month": year_month, "employees": employees}

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
        # 可分配率缺省口径：某店当月**没有配置行** = 该店本月不参与提成分配（0）。
        # 必须与前端「店铺归属与提成比」页面、统计接口的缺省值保持一致，
        # 否则会出现「页面显示 0、实发却按 100% 给」的钱差。
        allocatable_by_shop = {
            self._shop_key(row.platform_code, row.shop_id): self._to_float(
                row.allocatable_profit_rate, 0.0
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

        commission_agg: Dict[str, Dict[str, Any]] = {}
        performance_agg: Dict[str, Dict[str, float]] = {}
        for row in assignments:
            employee_code = (row.employee_code or "").strip()
            if not employee_code:
                continue

            shop_key = self._shop_key(row.platform_code, row.shop_id)
            metric = metrics_by_shop.get(shop_key, {})
            basis = profit_basis_by_shop.get(shop_key, {})
            self._require_complete_profit_basis(shop_key, basis)
            score = performance_by_shop.get(shop_key, {})

            monthly_sales = self._to_float(metric.get("monthly_sales"), 0.0)
            achievement_rate = self._normalize_achievement_rate(
                metric.get("achievement_rate")
            )
            profit_basis_amount = self._to_float(basis.get("profit_basis_amount"), 0.0)
            alloc_rate = self._to_float(allocatable_by_shop.get(shop_key, 0.0), 0.0)
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
            ratio, ratio_source = self._resolve_commission_ratio(
                row,
                employee_code=employee_code,
                default_commission_ratio_by_employee=default_commission_ratio_by_employee,
            )
            comm_rec = commission_agg.setdefault(
                employee_code,
                {
                    "sales_amount": 0.0,
                    "commission_amount": 0.0,
                    "weighted_rate_num": 0.0,
                    "weighted_rate_den": 0.0,
                    "ratio_sources": set(),
                    "has_positive_ratio": False,
                },
            )
            if ratio > 0:
                comm_rec["has_positive_ratio"] = True
                comm_rec["ratio_sources"].add(ratio_source)
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
                    assignments_by_employee=controlled_context[
                        "assignments_by_employee"
                    ],
                    metrics=controlled_context["metrics"],
                    entry_scores_by_employee=controlled_context[
                        "entry_scores_by_employee"
                    ],
                    entry_details_by_employee=controlled_context[
                        "entry_details_by_employee"
                    ],
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
            refreshed_draft_payrolls = (
                await self._refresh_draft_payroll_variable_income(
                    year_month=year_month,
                    employee_codes={
                        employee_code
                        for employee_code, result in controlled_results.items()
                        if result.get("calculation_status")
                        in {"partial", "pending_scope", "not_participating"}
                    },
                )
            )
            if blocked_commission_codes:
                await self.db.execute(
                    delete(EmployeeCommission).where(
                        EmployeeCommission.year_month == year_month,
                        EmployeeCommission.employee_code.in_(blocked_commission_codes),
                    )
                )

        # ------------------------------------------------------------------
        # 绩效画像：先解析每个人当月的分数与分数档位系数，
        # 提成和绩效工资共用这一份，避免同一个人出现两套系数。
        # ------------------------------------------------------------------
        controlled_mode = controlled_context is not None
        employee_profiles: Dict[str, Dict[str, Any]] = {}
        for employee_code in population_codes:
            employee_profiles[employee_code] = (
                self._resolve_employee_performance_profile(
                    employee_code,
                    agg=performance_agg.get(employee_code, {}),
                    input_score_by_employee=input_score_by_employee,
                    pending_input_employee_codes=pending_input_employee_codes,
                    assigned_codes=assigned_codes,
                    controlled_mode=controlled_mode,
                    controlled_result=controlled_results.get(employee_code),
                    attendance_adjustment_by_employee=attendance_adjustment_by_employee,
                    manual_adjustment_by_employee=manual_adjustment_by_employee,
                )
            )

        # 员工结算系数（按店铺销售额加权）+ 每店系数拆解，供审计与页面复用。
        employee_settlement_coefficient: Dict[str, float] = {}
        employee_settlement_details: Dict[str, Dict[str, Any]] = {}

        for employee_code, rec in commission_agg.items():
            if employee_code in blocked_commission_codes:
                continue
            sales_amount = rec["sales_amount"]
            profile = employee_profiles.get(employee_code, {})
            employee_score_coefficient = profile.get("score_coefficient")
            commission_amount = 0.0
            coefficient_num = 0.0
            coefficient_den = 0.0
            shop_coefficients: list[Dict[str, Any]] = []
            for row in assignments:
                if (row.employee_code or "").strip() != employee_code:
                    continue
                ratio, _ratio_source = self._resolve_commission_ratio(
                    row,
                    employee_code=employee_code,
                    default_commission_ratio_by_employee=default_commission_ratio_by_employee,
                )
                if ratio <= 0:
                    continue
                shop_key = self._shop_key(row.platform_code, row.shop_id)
                metric = metrics_by_shop.get(shop_key, {})
                monthly_sales = self._to_float(metric.get("monthly_sales"), 0.0)
                sales_share = monthly_sales * ratio

                # 结算系数 = min(店铺结算系数, 个人分数档位系数)
                # 店铺结算系数 = min(该店排名档位, 该店分数档位)，由店铺绩效模块写入。
                shop_coefficient = self._to_float(
                    performance_by_shop.get(shop_key, {}).get(
                        "performance_coefficient"
                    ),
                    1.0,
                )
                settlement = describe_settlement_coefficient(
                    shop_coefficient=shop_coefficient,
                    score_coefficient=employee_score_coefficient,
                )
                settlement_coefficient = settlement["settlement_coefficient"]

                profit_basis_amount = self._to_float(
                    profit_basis_by_shop.get(shop_key, {}).get("profit_basis_amount"),
                    0.0,
                )
                # 可分配率缺省口径必须与聚合段、统计接口、前端一致：未配置 = 0。
                alloc_rate = self._to_float(
                    allocatable_by_shop.get(shop_key, 0.0),
                    0.0,
                )
                allocation_amount = (
                    max(profit_basis_amount, 0.0)
                    * alloc_rate
                    * ratio
                    * settlement_coefficient
                )
                commission_amount += allocation_amount
                coefficient_num += settlement_coefficient * sales_share
                coefficient_den += sales_share
                shop_coefficients.append(
                    {
                        "shop_key": shop_key,
                        "commission_ratio": round(ratio, 6),
                        "allocatable_profit_rate": round(alloc_rate, 6),
                        "profit_basis_amount": round(profit_basis_amount, 2),
                        "commission_amount": round(allocation_amount, 2),
                        **settlement,
                    }
                )
                commission_allocations.append(
                    {
                        "employee_code": employee_code,
                        "platform_code": str(row.platform_code or "").lower(),
                        "shop_id": row.shop_id,
                        "commission_amount": allocation_amount,
                        "settlement_coefficient": round(settlement_coefficient, 6),
                    }
                )

            if sales_amount > 0:
                commission_rate = commission_amount / sales_amount
            else:
                commission_rate = 0.0

            # 尾差吸收：提成**总额**是「各店未舍入金额累加后统一舍入一次」，
            # 而逐店明细各自舍入后再相加，可能差 1 分
            # （例：黄嘉矩 9.22 + 144.67 = 153.89，但实发总额是 153.88）。
            # 把这笔尾差并到金额最大的那家店，保证
            # 「页面上的逐店明细加起来 == 页面上的提成总额 == 工资单实发」。
            _absorb_commission_rounding_residue(shop_coefficients, commission_amount)

            employee_settlement_coefficient[employee_code] = (
                coefficient_num / coefficient_den
                if coefficient_den > 0
                else calculate_settlement_coefficient(employee_score_coefficient)
            )
            employee_settlement_details[employee_code] = {
                "settlement_coefficient": round(
                    employee_settlement_coefficient[employee_code], 6
                ),
                "score_coefficient": employee_score_coefficient,
                "shops": shop_coefficients,
            }

            refreshed_payroll = refreshed_draft_payrolls.get(employee_code)
            if refreshed_payroll is not None:
                refreshed_payroll.commission = commission_amount
                PayrollGenerationService.recalculate_record_totals(refreshed_payroll)

            ratio_sources = sorted(
                str(item) for item in (rec.get("ratio_sources") or ())
            )
            has_ratio = bool(rec.get("has_positive_ratio"))
            calculation_status = "calculated" if has_ratio else "no_ratio"
            calculation_details: Dict[str, Any] = {
                "ratio_sources": ratio_sources,
                "commission_rate": round(commission_rate, 6),
                "sales_amount": round(sales_amount, 2),
                "inherited_coefficient": round(
                    employee_settlement_coefficient[employee_code], 6
                ),
                "settlement_coefficient": round(
                    employee_settlement_coefficient[employee_code], 6
                ),
                "score_coefficient": employee_score_coefficient,
                "shop_coefficients": shop_coefficients,
                "allocation_count": len(shop_coefficients),
            }
            if not has_ratio:
                # 以前这里会直接跳过 ⇒ 连一行记录都不留，
                # 工资单提成恒 0，界面上却看不出「他压根没配提成比例」。
                # 现在照样落一行（金额 0）+ 明确状态，并把原因写进审计字段。
                calculation_details["reason"] = (
                    "no commission ratio configured; set "
                    "employee_shop_assignments.commission_ratio or "
                    "salary_structures.commission_ratio"
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
                comm.calculation_status = calculation_status
                comm.calculation_details = calculation_details
                comm.calculated_at = datetime.now(timezone.utc)
            else:
                self.db.add(
                    EmployeeCommission(
                        employee_code=employee_code,
                        year_month=year_month,
                        sales_amount=sales_amount,
                        commission_amount=commission_amount,
                        commission_rate=commission_rate,
                        calculation_status=calculation_status,
                        calculation_details=calculation_details,
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
            # 绩效画像已经在提成循环之前解析好了，这里直接复用，
            # 保证「绩效工资」和「提成」用的是同一个系数口径。
            profile = employee_profiles.get(employee_code, {})
            performance_score = profile.get("performance_score")
            calculation_status = str(
                profile.get("calculation_status") or "pending_store_performance"
            )
            performance_source_type = str(
                profile.get("performance_source_type") or "shop_inherited"
            )
            if performance_score is not None and calculation_status == "complete":
                formal_employee_codes.add(employee_code)

            settlement_coefficient = None
            if calculation_status == "complete" and performance_score is not None:
                settlement_coefficient = employee_settlement_coefficient.get(
                    employee_code
                )
                if settlement_coefficient is None:
                    settlement_coefficient = calculate_settlement_coefficient(
                        profile.get("score_coefficient")
                    )

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
                perf.performance_coefficient = settlement_coefficient
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
                        performance_coefficient=settlement_coefficient,
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
                controlled_settlement_coefficient = None
                if (
                    result.get("calculation_status") == "complete"
                    and result.get("performance_score") is not None
                ):
                    controlled_settlement_coefficient = (
                        employee_settlement_coefficient.get(employee_code)
                    )
                    if controlled_settlement_coefficient is None:
                        controlled_settlement_coefficient = (
                            calculate_settlement_coefficient(
                                (employee_profiles.get(employee_code) or {}).get(
                                    "score_coefficient"
                                )
                            )
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
                        performance_coefficient=controlled_settlement_coefficient,
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
                    perf.performance_coefficient = controlled_settlement_coefficient
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
            "settlement_coefficients": employee_settlement_details,
            "source": (
                "controlled_targets_v1"
                if controlled_context is not None
                else "employee_shop_assignments + employee_performance_inputs + performance_scores + shop_profit_basis"
            ),
        }
