from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeeLaborCostAllocation,
    MonthlyProfitAdjustment,
    MonthlyProfitSettlement,
    ShopProfitBasis,
)
from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.labor_cost_projection_service import (
    LABOR_COST_CALCULATION_VERSION,
)
from backend.services.payroll_period_lock_service import PAYROLL_LOCKED_STATUSES
from backend.services.performance_readiness_service import PerformanceReadinessService


class MonthlyProfitSettlementNotFoundError(LookupError):
    pass


class MonthlyProfitSettlementConflictError(ValueError):
    pass


class MonthlyProfitSettlementValidationError(ValueError):
    pass


#: 人工调整项的取值域（与 ``backend/schemas/monthly_profit_settlement.py`` 的枚举一致）
ADJUSTMENT_TYPES = (
    "manual_adjustment",
    "cross_period_expense",
    "one_off_gain_loss",
    "correction",
)


class MonthlyProfitSettlementService:
    """月度利润看板（只读）。

    ⚠️ 本服务**不生产金额**：它只回答三件事 —— 这个月赚了多少、分给员工多少、
    人工调整多少、留下多少。上游（利润基数 → 提成 → 绩效工资 → 工资单）已经闭环，
    月结再自己算一遍人力成本就会重复扣减。

    恒等式
    ------
    ``利润基数 = 店铺经营利润 − (其他经营成本 + 提成前人力成本)``，
    而 ``total_cost = 提成前人力成本 + 绩效工资 + 提成``
    ⇒ 用 ``total_cost`` 当人员成本会重复扣减 ⇒ 这里只取「绩效工资 + 提成」。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_float(value: Any) -> float:
        if value is None:
            return 0.0
        return float(value)

    @staticmethod
    def _get_value(record: Any, key: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(key, default)
        return getattr(record, key, default)

    def build_summary(
        self,
        *,
        period_month: str,
        net_profit_amount: float,
        personnel_actual_amount: float,
        adjustment_amount: float,
        status: str = "draft",
        settlement_id: int | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        """看板台账摘要 —— 只有残差口径，没有预算比例、没有差异算法。

        ⚠️ 预算制（目标比例 / 目标额 / 差异）与审批制已随看板制下线。
        """
        company_retained_amount = (
            net_profit_amount - personnel_actual_amount - adjustment_amount
        )
        allocation_ratio = (
            (personnel_actual_amount + adjustment_amount) / net_profit_amount
            if net_profit_amount
            else 0.0
        )
        return {
            "id": settlement_id,
            "net_profit_amount": round(net_profit_amount, 4),
            "personnel_actual_amount": round(personnel_actual_amount, 4),
            "adjustment_amount": round(adjustment_amount, 4),
            "company_retained_amount": round(company_retained_amount, 4),
            "allocation_ratio": round(allocation_ratio, 8),
            "over_allocation_flag": (
                company_retained_amount < 0 or allocation_ratio > 1
            ),
            "status": status,
            "remark": remark,
        }

    async def _load_shop_profit_basis(
        self, period_month: str
    ) -> dict[tuple[str, str], Any]:
        """按店去重后的利润基数行。

        去重规则沿用既有实现：同店多行时**非 legacy A_ONLY 行优先**
        （``LaborCostPolicyService.is_legacy_a_only_basis_version``）。
        key 与既有实现一致：``(platform_code.lower(), shop_id)``（shop_id 可能为空串）。
        """
        rows = (
            (
                await self.db.execute(
                    select(ShopProfitBasis).where(
                        ShopProfitBasis.period_month == period_month
                    )
                )
            )
            .scalars()
            .all()
        )
        basis_by_shop: dict[tuple[str, str], Any] = {}
        for row in rows:
            key = (
                str(getattr(row, "platform_code", "") or "").lower(),
                str(getattr(row, "shop_id", "") or ""),
            )
            current = basis_by_shop.get(key)
            if current is None or (
                not LaborCostPolicyService.is_legacy_a_only_basis_version(
                    getattr(row, "basis_version", "")
                )
                and LaborCostPolicyService.is_legacy_a_only_basis_version(
                    getattr(current, "basis_version", "")
                )
            ):
                basis_by_shop[key] = row
        return basis_by_shop

    @classmethod
    def _sum_profit_basis(cls, basis_by_shop: dict[tuple[str, str], Any]) -> float:
        """各店利润基数合计（= 净利润）。"""
        return sum(
            cls._to_float(row.profit_basis_amount) for row in basis_by_shop.values()
        )

    async def _load_net_profit_amount(self, period_month: str) -> float:
        """净利润 = Σ 各店利润基数（按既有去重规则）。"""
        # ⚠️ 不再扣公司人力成本池：它已经在各店利润基数里摊派过
        #    （见 backend/services/labor_cost_projection_service.py），
        #    在这里再减一次就是重复扣减。
        basis_by_shop = await self._load_shop_profit_basis(period_month)
        return self._sum_profit_basis(basis_by_shop)

    async def _load_personnel_payload(
        self,
        period_month: str,
        basis_by_shop: dict[tuple[str, str], Any],
    ) -> dict[str, Any]:
        """员工侧分配额 = Σ(绩效工资 + 提成)，并按店给出分布。

        ⚠️ ``pre_commission_amount`` 一律不取：它已在各店利润基数里扣过一次。
        ⚠️ ``company`` scope 的行计入总额（总部员工的绩效工资与提成也是真实分配），
        但不进 ``shop_breakdown``（那是按店的）。
        ⚠️ 每店的 ``profit_basis_amount`` 来自 ``basis_by_shop`` ⇒ 分布里的利润基数
        合计与 ``net_profit_amount`` 对账相等。
        """
        allocation_rows = (
            (
                await self.db.execute(
                    select(EmployeeLaborCostAllocation).where(
                        EmployeeLaborCostAllocation.period_month == period_month,
                        EmployeeLaborCostAllocation.source_payroll_status.in_(
                            PAYROLL_LOCKED_STATUSES
                        ),
                        # 只认当前口径：历史版本行与同月当前版本行并存时会把人力成本算两遍
                        EmployeeLaborCostAllocation.calculation_version
                        == LABOR_COST_CALCULATION_VERSION,
                    )
                )
            )
            .scalars()
            .all()
        )

        details: list[dict[str, Any]] = []
        performance_total = 0.0
        commission_total = 0.0
        shop_breakdown: dict[tuple[str, str], dict[str, Any]] = {}

        # 先按利润基数铺好每店分布 ⇒ 亏损店（利润基数 ≤ 0）也会出现，
        # 且分布里的利润基数合计与 net_profit_amount 对账相等。
        for key, basis_row in basis_by_shop.items():
            shop_breakdown[key] = {
                "platform_code": getattr(basis_row, "platform_code", None),
                "shop_id": getattr(basis_row, "shop_id", None),
                "profit_basis_amount": self._to_float(
                    getattr(basis_row, "profit_basis_amount", 0.0)
                ),
                "performance_amount": 0.0,
                "commission_amount": 0.0,
                "allocation_amount": 0.0,
            }

        for row in allocation_rows:
            performance_amount = self._to_float(getattr(row, "performance_amount", 0))
            commission_amount = self._to_float(getattr(row, "commission_amount", 0))
            performance_total += performance_amount
            commission_total += commission_amount
            amount = performance_amount + commission_amount
            details.append(
                {
                    "detail_type": "post_commission_labor_cost",
                    "amount": amount,
                    "employee_code": getattr(row, "employee_code", None),
                    "platform_code": getattr(row, "platform_code", None),
                    "shop_id": getattr(row, "shop_id", None),
                    "source_module": "employee_labor_cost_allocations",
                    "source_record_id": str(getattr(row, "id", "") or ""),
                    "remark": None,
                }
            )

            # 每店分布只收 shop scope：公司 scope 是总部员工，不落在任何一家店里
            if str(getattr(row, "allocation_scope", "") or "") != "shop":
                continue
            platform_code = getattr(row, "platform_code", None)
            shop_id = getattr(row, "shop_id", None)
            key = (str(platform_code or "").lower(), str(shop_id or ""))
            bucket = shop_breakdown.get(key)
            if bucket is None:
                # 分摊表里有、利润基数里没有的店（利润基数缺失）⇒ 基数按 0 计
                bucket = {
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "profit_basis_amount": 0.0,
                    "performance_amount": 0.0,
                    "commission_amount": 0.0,
                    "allocation_amount": 0.0,
                }
                shop_breakdown[key] = bucket
            bucket["performance_amount"] += performance_amount
            bucket["commission_amount"] += commission_amount
            bucket["allocation_amount"] += amount

        breakdown: list[dict[str, Any]] = []
        for bucket in shop_breakdown.values():
            profit_basis_amount = self._to_float(bucket["profit_basis_amount"])
            allocation_amount = self._to_float(bucket["allocation_amount"])
            breakdown.append(
                {
                    **bucket,
                    # 亏损店（利润基数 ≤ 0）占比取 0，但「分过头」的判定照常按金额比
                    "allocation_ratio": (
                        round(allocation_amount / profit_basis_amount, 8)
                        if profit_basis_amount > 0
                        else 0.0
                    ),
                    "over_allocation_flag": allocation_amount > profit_basis_amount,
                }
            )

        return {
            # 只取提成后金额：pre_commission_amount 已在各店利润基数里扣过一次
            "actual_amount": performance_total + commission_total,
            "performance_salary_amount": performance_total,
            "commission_amount": commission_total,
            "details": details,
            "shop_breakdown": breakdown,
        }

    async def _load_settlement_record(
        self, period_month: str
    ) -> MonthlyProfitSettlement | None:
        return (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(
                    MonthlyProfitSettlement.period_month == period_month
                )
            )
        ).scalar_one_or_none()

    async def _load_adjustments_by_month(
        self, period_month: str
    ) -> list[dict[str, Any]]:
        """按月取人工调整项。

        ⚠️ MonthlyProfitAdjustment 没有 period_month 字段（只有 settlement_id 外键），
        必须 join MonthlyProfitSettlement 的 period_month（唯一键）。
        """
        rows = (
            (
                await self.db.execute(
                    select(MonthlyProfitAdjustment)
                    .join(
                        MonthlyProfitSettlement,
                        MonthlyProfitAdjustment.settlement_id
                        == MonthlyProfitSettlement.id,
                    )
                    .where(MonthlyProfitSettlement.period_month == period_month)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": row.id,
                "adjustment_type": row.adjustment_type,
                "amount": self._to_float(row.amount),
                "reason": row.reason,
                "created_by": row.created_by,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def get_dashboard(self, period_month: str) -> dict[str, Any]:
        """只读聚合：唯一口径实现处。前端不得复刻。"""
        basis_by_shop = await self._load_shop_profit_basis(period_month)
        net_profit = self._sum_profit_basis(basis_by_shop)
        personnel = await self._load_personnel_payload(period_month, basis_by_shop)
        adjustments = await self._load_adjustments_by_month(period_month)
        adjustment_total = sum(a["amount"] for a in adjustments)
        employee_allocation = self._to_float(personnel.get("actual_amount"))
        company_retained = net_profit - employee_allocation - adjustment_total
        allocation_ratio = (
            (employee_allocation + adjustment_total) / net_profit if net_profit else 0.0
        )
        return {
            "period_month": period_month,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "net_profit_amount": net_profit,
            "performance_salary_amount": self._to_float(
                personnel.get("performance_salary_amount")
            ),
            "commission_amount": self._to_float(personnel.get("commission_amount")),
            "employee_allocation_amount": employee_allocation,
            "manual_adjustment_amount": adjustment_total,
            "manual_adjustment_count": len(adjustments),
            "company_retained_amount": company_retained,
            "allocation_ratio": allocation_ratio,
            "over_allocation_flag": company_retained < 0 or allocation_ratio > 1,
            "shop_breakdown": personnel.get("shop_breakdown", []),
            "adjustments": adjustments,
        }

    async def get_month(self, period_month: str) -> dict[str, Any]:
        """兼容入口：与看板同源（旧信封 + 快照视图已下线）。"""
        return await self.get_dashboard(period_month)

    async def _upsert_settlement(
        self, period_month: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        record = await self._load_settlement_record(period_month)
        if record is None:
            record = MonthlyProfitSettlement(period_month=period_month)
            self.db.add(record)
            await self.db.flush()

        # ⚠️ 字段白名单只保留看板口径的 5 项：目标比例 / 目标额 / 差异 / 跟投实际额
        #    这些列随预算制与跟投下线一起废弃，不再由月结写入。
        for field in [
            "net_profit_amount",
            "personnel_actual_amount",
            "adjustment_amount",
            "status",
            "remark",
        ]:
            setattr(record, field, payload[field])

        record.locked_at = (
            datetime.now(timezone.utc) if payload["status"] == "approved" else None
        )
        record.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        payload["id"] = record.id
        return payload

    async def rebuild_month(
        self,
        *,
        period_month: str,
        adjustment_amount: float = 0.0,
        adjustment_reason: str | None = None,
    ) -> dict[str, Any]:
        """确保该月台账行存在，并把该月的人工调整项整体替换为给定金额。

        ⚠️ 不再重算人员成本、不再写跟投明细 —— 看板金额一律由 ``get_dashboard`` 现场聚合。
        """
        await PerformanceReadinessService(self.db).assert_month_performance_ready(
            period_month
        )
        record = await self._load_settlement_record(period_month)
        if record is None:
            record = MonthlyProfitSettlement(period_month=period_month)
            self.db.add(record)
            await self.db.flush()

        summary = self.build_summary(
            period_month=period_month,
            net_profit_amount=self._to_float(getattr(record, "net_profit_amount", 0.0)),
            personnel_actual_amount=self._to_float(
                getattr(record, "personnel_actual_amount", 0.0)
            ),
            adjustment_amount=self._to_float(adjustment_amount),
            status="draft",
            settlement_id=int(record.id),
            remark=getattr(record, "remark", None),
        )
        summary = await self._upsert_settlement(period_month, summary)
        settlement_id = int(summary["id"])

        await self.db.execute(
            delete(MonthlyProfitAdjustment).where(
                MonthlyProfitAdjustment.settlement_id == settlement_id
            )
        )
        await self.db.flush()

        if adjustment_amount:
            self.db.add(
                MonthlyProfitAdjustment(
                    settlement_id=settlement_id,
                    adjustment_type="manual_adjustment",
                    amount=self._to_float(adjustment_amount),
                    reason=adjustment_reason or "monthly settlement adjustment",
                    created_by="system",
                )
            )

        await self.db.commit()
        return {
            "summary": summary,
            "personnel_details": [],
            "follow_details": [],
            "adjustments": (
                [
                    {
                        "adjustment_type": "manual_adjustment",
                        "amount": self._to_float(adjustment_amount),
                        "reason": adjustment_reason or "monthly settlement adjustment",
                        "created_by": "system",
                    }
                ]
                if adjustment_amount
                else []
            ),
        }

    async def add_adjustment(
        self,
        *,
        period_month: str,
        adjustment_type: str,
        amount: float,
        reason: str,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """新增一条人工调整项。

        ⚠️ 写调整项前先按 ``period_month`` upsert 台账主记录（其余字段用默认值 0），
        保证 ``adjustments.settlement_id`` 外键有指向。
        """
        if not str(reason or "").strip():
            raise MonthlyProfitSettlementValidationError(
                "adjustment reason is required"
            )
        if adjustment_type not in ADJUSTMENT_TYPES:
            raise MonthlyProfitSettlementValidationError(
                f"unsupported adjustment type: {adjustment_type}"
            )

        record = await self._load_settlement_record(period_month)
        if record is None:
            record = MonthlyProfitSettlement(period_month=period_month)
            self.db.add(record)
            await self.db.flush()

        clean_reason = str(reason).strip()
        row = MonthlyProfitAdjustment(
            settlement_id=int(record.id),
            adjustment_type=adjustment_type,
            amount=self._to_float(amount),
            reason=clean_reason,
            created_by=created_by,
        )
        self.db.add(row)
        record.adjustment_amount = self._to_float(
            getattr(record, "adjustment_amount", 0.0)
        ) + self._to_float(amount)
        record.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.commit()

        return {
            "id": row.id,
            "period_month": period_month,
            "settlement_id": int(record.id),
            "adjustment_type": adjustment_type,
            "amount": self._to_float(amount),
            "reason": clean_reason,
            "created_by": created_by,
        }

    async def remove_adjustment(self, adjustment_id: int) -> dict[str, Any]:
        """删除一条人工调整项。"""
        row = (
            await self.db.execute(
                select(MonthlyProfitAdjustment).where(
                    MonthlyProfitAdjustment.id == adjustment_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise MonthlyProfitSettlementNotFoundError("adjustment not found")

        settlement_id = int(row.settlement_id)
        await self.db.delete(row)
        await self.db.flush()

        record = (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(
                    MonthlyProfitSettlement.id == settlement_id
                )
            )
        ).scalar_one_or_none()
        if record is not None:
            remaining = (
                (
                    await self.db.execute(
                        select(MonthlyProfitAdjustment).where(
                            MonthlyProfitAdjustment.settlement_id == settlement_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            record.adjustment_amount = sum(
                self._to_float(item.amount) for item in remaining
            )
            record.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        return {
            "id": int(adjustment_id),
            "deleted": True,
            "settlement_id": settlement_id,
        }
