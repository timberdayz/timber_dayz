"""
HR 员工收入 C 类写入服务

用途:
- 基于 a_class.employee_shop_assignments 与 a_class.shop_commission_config
- 结合 Metabase 问题 hr_shop_monthly_metrics（月度销售/利润/达成率）
- 计算并写入 c_class.employee_commissions 与 c_class.employee_performance
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    EmployeeShopAssignment,
    ShopCommissionConfig,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


class HRIncomeCalculationService:
    """员工收入 C 类数据计算与写入服务。"""

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
        """将达成率统一为 0~1。若输入为 85.5（百分比）则转为 0.855。"""
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
    def _row_val(row: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        lower_map = {str(k).lower(): v for k, v in row.items()}
        for key in keys:
            value = lower_map.get(str(key).lower())
            if value is not None:
                return value
        return None

    async def _load_shop_metrics(self, year_month: str) -> Dict[str, Dict[str, float]]:
        """加载店铺月度指标。"""
        month_date = datetime.strptime(year_month, "%Y-%m").date().replace(day=1)
        svc = self.metabase_service
        if svc is None:
            from backend.services.metabase_question_service import get_metabase_service

            svc = get_metabase_service()

        metrics_by_shop: Dict[str, Dict[str, float]] = {}
        result = await svc.query_question("hr_shop_monthly_metrics", {"month": month_date.isoformat()})
        if not isinstance(result, list):
            return metrics_by_shop

        for row in result:
            if not isinstance(row, dict):
                continue
            platform_code = self._row_val(row, "platform_code", "平台")
            shop_id = self._row_val(row, "shop_id", "店铺ID")
            if not platform_code or shop_id is None:
                continue
            key = self._shop_key(platform_code, shop_id)
            metrics_by_shop[key] = {
                "monthly_sales": self._to_float(self._row_val(row, "monthly_sales", "月销售额", "销售额"), 0.0),
                "monthly_profit": self._to_float(self._row_val(row, "monthly_profit", "月利润", "利润"), 0.0),
                "achievement_rate": self._normalize_achievement_rate(
                    self._row_val(row, "achievement_rate", "达成率")
                ),
            }
        return metrics_by_shop

    async def calculate_month(self, year_month: str) -> Dict[str, Any]:
        """计算并写入指定月份员工提成与绩效。"""
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("year_month 格式应为 YYYY-MM") from exc

        assign_query = (
            select(EmployeeShopAssignment)
            .where(EmployeeShopAssignment.status == "active")
            .where(EmployeeShopAssignment.year_month == year_month)
        )
        assignments = (await self.db.execute(assign_query)).scalars().all()
        if not assignments:
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
                "source": "employee_shop_assignments + shop_commission_config + hr_shop_monthly_metrics",
            }

        cfg_query = select(ShopCommissionConfig).where(ShopCommissionConfig.year_month == year_month)
        cfg_rows = (await self.db.execute(cfg_query)).scalars().all()
        allocatable_by_shop = {
            self._shop_key(row.platform_code, row.shop_id): self._to_float(row.allocatable_profit_rate, 1.0)
            for row in cfg_rows
        }

        metrics_by_shop = await self._load_shop_metrics(year_month)

        # employee_code -> 聚合结果
        agg: Dict[str, Dict[str, float]] = {}
        for row in assignments:
            emp = (row.employee_code or "").strip()
            if not emp:
                continue
            ratio = self._to_float(row.commission_ratio, 0.0)
            if ratio <= 0:
                continue
            shop_key = self._shop_key(row.platform_code, row.shop_id)
            metric = metrics_by_shop.get(shop_key, {})
            monthly_sales = self._to_float(metric.get("monthly_sales"), 0.0)
            monthly_profit = self._to_float(metric.get("monthly_profit"), 0.0)
            achievement_rate = self._normalize_achievement_rate(metric.get("achievement_rate"))
            alloc_rate = self._to_float(allocatable_by_shop.get(shop_key, 1.0), 1.0)
            alloc_profit = monthly_profit * alloc_rate

            rec = agg.setdefault(
                emp,
                {
                    "sales_amount": 0.0,
                    "commission_amount": 0.0,
                    "weighted_rate_num": 0.0,
                    "weighted_rate_den": 0.0,
                },
            )
            sales_share = monthly_sales * ratio
            rec["sales_amount"] += sales_share
            rec["commission_amount"] += alloc_profit * ratio
            rec["weighted_rate_num"] += achievement_rate * sales_share
            rec["weighted_rate_den"] += sales_share

        commission_upserts = 0
        performance_upserts = 0
        for employee_code, rec in agg.items():
            sales_amount = rec["sales_amount"]
            commission_amount = rec["commission_amount"]
            if sales_amount > 0:
                commission_rate = commission_amount / sales_amount
                achievement_rate = rec["weighted_rate_num"] / rec["weighted_rate_den"]
            else:
                commission_rate = 0.0
                achievement_rate = 0.0
            performance_score = min(max(achievement_rate, 0.0), 1.0) * 100.0

            try:
                comm_query = select(EmployeeCommission).where(
                    EmployeeCommission.employee_code == employee_code,
                    EmployeeCommission.year_month == year_month,
                )
                comm = (await self.db.execute(comm_query)).scalar_one_or_none()
                if comm:
                    comm.sales_amount = sales_amount
                    comm.commission_amount = commission_amount
                    comm.commission_rate = commission_rate
                    comm.calculated_at = datetime.utcnow()
                else:
                    self.db.add(
                        EmployeeCommission(
                            employee_code=employee_code,
                            year_month=year_month,
                            sales_amount=sales_amount,
                            commission_amount=commission_amount,
                            commission_rate=commission_rate,
                            calculated_at=datetime.utcnow(),
                        )
                    )
            except Exception:
                # 兼容历史中文列名表结构
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
                        "calculated_at": datetime.utcnow(),
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
                            "calculated_at": datetime.utcnow(),
                        },
                    )
            commission_upserts += 1

            try:
                perf_query = select(EmployeePerformance).where(
                    EmployeePerformance.employee_code == employee_code,
                    EmployeePerformance.year_month == year_month,
                )
                perf = (await self.db.execute(perf_query)).scalar_one_or_none()
                if perf:
                    perf.actual_sales = sales_amount
                    perf.achievement_rate = achievement_rate
                    perf.performance_score = performance_score
                    perf.calculated_at = datetime.utcnow()
                else:
                    self.db.add(
                        EmployeePerformance(
                            employee_code=employee_code,
                            year_month=year_month,
                            actual_sales=sales_amount,
                            achievement_rate=achievement_rate,
                            performance_score=performance_score,
                            calculated_at=datetime.utcnow(),
                        )
                    )
            except Exception:
                # 兼容历史中文列名表结构
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
                        "calculated_at": datetime.utcnow(),
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
                            "calculated_at": datetime.utcnow(),
                        },
                    )
            performance_upserts += 1

        await self.db.commit()
        return {
            "year_month": year_month,
            "employee_count": len(agg),
            "commission_upserts": commission_upserts,
            "performance_upserts": performance_upserts,
            "source": "employee_shop_assignments + shop_commission_config + hr_shop_monthly_metrics",
        }
