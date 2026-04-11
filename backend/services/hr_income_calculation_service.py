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

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    AttendanceRecord,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceAdjustment,
    EmployeeShopAssignment,
    PerformanceScore,
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
    def _score_details_field(details: Dict[str, Any] | None, *keys: str) -> Any:
        current: Any = details or {}
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
        return current

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

        rows = (
            await self.db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_code.in_(employee_codes),
                    AttendanceRecord.attendance_date >= period_start,
                    AttendanceRecord.attendance_date < next_month,
                )
            )
        ).scalars().all()

        adjustment_by_employee: Dict[str, float] = {}
        for row in rows:
            employee_code = (getattr(row, "employee_code", None) or "").strip()
            if not employee_code:
                continue
            status = (getattr(row, "status", None) or "").strip().lower()
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

    async def calculate_month(self, year_month: str) -> Dict[str, Any]:
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("year_month format must be YYYY-MM") from exc

        assignments = (
            await self.db.execute(
                select(EmployeeShopAssignment)
                .where(EmployeeShopAssignment.status == "active")
                .where(EmployeeShopAssignment.year_month == year_month)
            )
        ).scalars().all()
        if not assignments:
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
                "source": "employee_shop_assignments + shop_commission_config + profit_basis_amount",
            }

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

            store_weight = self._to_float(score.get("sales_target"), 0.0)
            if store_weight <= 0:
                store_weight = monthly_sales if monthly_sales > 0 else 1.0
            if score:
                store_score = self._to_float(score.get("total_score"), 0.0)
            else:
                store_score = min(max(achievement_rate, 0.0), 1.0) * 100.0
            perf_rec["weighted_score_num"] += store_score * store_weight
            perf_rec["weighted_score_den"] += store_weight

            # Commission aggregation: still based on commission ratio.
            ratio = self._to_float(row.commission_ratio, 0.0)
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
            commission_amount = rec["commission_amount"]
            if sales_amount > 0:
                commission_rate = commission_amount / sales_amount
            else:
                commission_rate = 0.0

            try:
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
            except Exception:
                await self.db.rollback()
                logger.warning(
                    "employee_commissions ORM upsert failed, fallback to CN column SQL"
                )
                upd = await self.db.execute(
                    text(
                        """
                        update c_class.employee_commissions
                        set "销售额" = :sales_amount,
                            "提成金额" = :commission_amount,
                            "提成比例" = :commission_rate,
                            "计算时间" = :calculated_at
                        where "员工编号" = :employee_code
                          and "年月" = :year_month
                        """
                    ),
                    {
                        "sales_amount": sales_amount,
                        "commission_amount": commission_amount,
                        "commission_rate": commission_rate,
                        "calculated_at": datetime.now(timezone.utc),
                        "employee_code": employee_code,
                        "year_month": year_month,
                    },
                )
                if (upd.rowcount or 0) == 0:
                    await self.db.execute(
                        text(
                            """
                            insert into c_class.employee_commissions
                              ("员工编号", "年月", "销售额", "提成金额", "提成比例", "计算时间")
                            values
                              (:employee_code, :year_month, :sales_amount, :commission_amount, :commission_rate, :calculated_at)
                            """
                        ),
                        {
                            "employee_code": employee_code,
                            "year_month": year_month,
                            "sales_amount": sales_amount,
                            "commission_amount": commission_amount,
                            "commission_rate": commission_rate,
                            "calculated_at": datetime.now(timezone.utc),
                        },
                    )
            commission_upserts += 1

        for employee_code, rec in performance_agg.items():
            sales_amount = rec["sales_amount"]
            if rec["weighted_rate_den"] > 0:
                achievement_rate = rec["weighted_rate_num"] / rec["weighted_rate_den"]
            else:
                achievement_rate = 0.0
            if rec["weighted_score_den"] > 0:
                performance_score = (
                    rec["weighted_score_num"] / rec["weighted_score_den"]
                )
            else:
                performance_score = min(max(achievement_rate, 0.0), 1.0) * 100.0
            performance_score += self._to_float(
                attendance_adjustment_by_employee.get(employee_code),
                0.0,
            )
            performance_score += self._to_float(
                manual_adjustment_by_employee.get(employee_code),
                0.0,
            )
            performance_score = min(max(performance_score, 0.0), 100.0)

            try:
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
            except Exception:
                await self.db.rollback()
                logger.warning(
                    "employee_performance ORM upsert failed, fallback to CN column SQL"
                )
                upd = await self.db.execute(
                    text(
                        """
                        update c_class.employee_performance
                        set "实际销售额" = :actual_sales,
                            "达成率" = :achievement_rate,
                            "绩效得分" = :performance_score,
                            "计算时间" = :calculated_at
                        where "员工编号" = :employee_code
                          and "年月" = :year_month
                        """
                    ),
                    {
                        "actual_sales": sales_amount,
                        "achievement_rate": achievement_rate,
                        "performance_score": performance_score,
                        "calculated_at": datetime.now(timezone.utc),
                        "employee_code": employee_code,
                        "year_month": year_month,
                    },
                )
                if (upd.rowcount or 0) == 0:
                    await self.db.execute(
                        text(
                            """
                            insert into c_class.employee_performance
                              ("员工编号", "年月", "实际销售额", "达成率", "绩效得分", "计算时间")
                            values
                              (:employee_code, :year_month, :actual_sales, :achievement_rate, :performance_score, :calculated_at)
                            """
                        ),
                        {
                            "employee_code": employee_code,
                            "year_month": year_month,
                            "actual_sales": sales_amount,
                            "achievement_rate": achievement_rate,
                            "performance_score": performance_score,
                            "calculated_at": datetime.now(timezone.utc),
                        },
                    )
            performance_upserts += 1

        await self.db.commit()
        return {
            "year_month": year_month,
            "employee_count": len(performance_agg),
            "commission_upserts": commission_upserts,
            "performance_upserts": performance_upserts,
            "source": "employee_shop_assignments + performance_scores + shop_profit_basis",
        }
