"""工资单确认服务：单人确认与整月批量确认共用同一套校验。

为什么要有批量确认
------------------
原先只有「按人确认」一个入口，而工资期是**月份级原子**的：任意一张工资单进入
``confirmed`` 之后，整月就禁止重算绩效与提成。结果是运营同事先确认了一个人，
剩下所有人全部 409，只能「退回草稿」重来。

现在提供整月批量确认：先把全月待确认的工资单一次性校验完，**全部通过才整体提交**，
任何一张不通过就整批不落地，并把「哪个人、缺什么、去哪补」一次性列出来。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from backend.services.performance_readiness_service import (
    PerformanceReadinessError,
    PerformanceReadinessService,
)
from backend.services.profit_basis_service import ProfitBasisService
from modules.core.db import (
    EmployeeLaborCostAllocation,
    EmployeeShopAssignment,
    PayrollRecord,
)


class PayrollConfirmationError(ValueError):
    """工资单确认失败。``detail`` 携带可读原因，``issues`` 携带逐条清单。"""

    def __init__(
        self,
        detail: str,
        *,
        issues: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.issues = issues or []


class PayrollConfirmationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _shop_key(platform_code: Any, shop_id: Any) -> tuple[str, str]:
        return (
            str(platform_code or "").strip().lower(),
            str(shop_id or "").strip(),
        )

    async def _load_assignments(self, year_month: str, employee_code: str) -> List[Any]:
        rows = (
            (
                await self.db.execute(
                    select(EmployeeShopAssignment).where(
                        EmployeeShopAssignment.year_month == year_month,
                        EmployeeShopAssignment.employee_code == employee_code,
                        EmployeeShopAssignment.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _load_allocations(self, year_month: str, employee_code: str) -> List[Any]:
        rows = (
            (
                await self.db.execute(
                    select(EmployeeLaborCostAllocation).where(
                        EmployeeLaborCostAllocation.period_month == year_month,
                        EmployeeLaborCostAllocation.employee_code == employee_code,
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _check_ratio_limit(self, year_month: str, assignments: List[Any]) -> None:
        """同店同月 Σ提成比例 ≤ 100%（按该员工负责的店，统计全月归属）。"""
        assigned_shop_keys = {
            self._shop_key(a.platform_code, a.shop_id) for a in assignments
        }
        if not assigned_shop_keys:
            return
        month_assignments = (
            (
                await self.db.execute(
                    select(EmployeeShopAssignment).where(
                        EmployeeShopAssignment.year_month == year_month,
                        EmployeeShopAssignment.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        ratio_by_shop: Dict[tuple[str, str], float] = {}
        for assignment in month_assignments:
            shop_key = self._shop_key(assignment.platform_code, assignment.shop_id)
            if shop_key not in assigned_shop_keys:
                continue
            ratio_by_shop[shop_key] = ratio_by_shop.get(shop_key, 0.0) + float(
                getattr(assignment, "commission_ratio", 0) or 0
            )
        over_allocated = next(
            (
                shop_key
                for shop_key, total_ratio in ratio_by_shop.items()
                if total_ratio > 1.000001
            ),
            None,
        )
        if over_allocated is not None:
            raise PayrollConfirmationError(
                f"店铺 {over_allocated[1]} 的员工提成比例总和不能超过 100%"
            )

    async def _precheck_record(self, record: Any) -> tuple[List[Any], List[Any]]:
        """确认前的一次性校验。失败时抛 PayrollConfirmationError。

        返回 ``(assignments, allocations)``，避免调用方重复查询。
        """
        allocations = await self._load_allocations(
            record.year_month, record.employee_code
        )
        if not allocations:
            raise PayrollConfirmationError(
                "请先刷新当月工资和人力成本分摊，再确认工资单"
            )
        try:
            await PerformanceReadinessService(self.db).assert_month_performance_ready(
                record.year_month,
                employee_codes={record.employee_code},
            )
        except PerformanceReadinessError as exc:
            raise PayrollConfirmationError(str(exc)) from exc
        assignments = await self._load_assignments(
            record.year_month, record.employee_code
        )
        await self._check_ratio_limit(record.year_month, assignments)
        return assignments, allocations

    async def confirm_record(self, record_id: int) -> PayrollRecord:
        """确认单张工资单。返回已确认的记录对象。"""
        record = (
            await self.db.execute(
                select(PayrollRecord).where(PayrollRecord.id == record_id)
            )
        ).scalar_one_or_none()
        if record is None:
            raise PayrollConfirmationError("工资单不存在")
        if record.status == "paid":
            raise PayrollConfirmationError("已发放工资单不可再次确认")
        if record.status != "draft":
            raise PayrollConfirmationError("仅草稿工资单可以确认")

        period_lock = PayrollPeriodLockService(self.db)
        await period_lock.acquire_month_transaction_lock(year_month=record.year_month)
        await self.db.refresh(record)
        if record.status != "draft":
            raise PayrollConfirmationError("工资单状态已变更，请刷新后重试")

        assignments, allocations = await self._precheck_record(record)
        basis_version = await LaborCostPolicyService(self.db).get_profit_basis_version(
            record.year_month
        )
        await ProfitBasisService(self.db).lock_profit_basis_snapshots_for_assignments(
            year_month=record.year_month,
            assignments=assignments,
            basis_version=basis_version,
            commit=False,
        )
        if (
            getattr(
                getattr(getattr(self.db, "bind", None), "dialect", None), "name", None
            )
            == "postgresql"
        ):
            await period_lock.assert_month_mutable(year_month=record.year_month)

        record.status = "confirmed"
        locked_at = datetime.now(timezone.utc)
        for allocation in allocations:
            allocation.source_payroll_status = "confirmed"
            allocation.calculation_status = "confirmed"
            allocation.pre_commission_locked_at = locked_at
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def confirm_month(self, year_month: str) -> Dict[str, Any]:
        """整月批量确认：全部校验通过才整体提交。"""
        records = (
            (
                await self.db.execute(
                    select(PayrollRecord)
                    .where(
                        PayrollRecord.year_month == year_month,
                        PayrollRecord.status == "draft",
                    )
                    .order_by(PayrollRecord.employee_code)
                )
            )
            .scalars()
            .all()
        )
        if not records:
            raise PayrollConfirmationError(f"{year_month} 没有待确认的草稿工资单")

        period_lock = PayrollPeriodLockService(self.db)
        await period_lock.acquire_month_transaction_lock(year_month=year_month)

        issues: List[Dict[str, Any]] = []
        prepared: Dict[int, tuple[List[Any], List[Any]]] = {}
        for record in records:
            try:
                prepared[record.id] = await self._precheck_record(record)
            except PayrollConfirmationError as exc:
                issues.append(
                    {
                        "employee_code": record.employee_code,
                        "record_id": record.id,
                        "reason": exc.detail,
                    }
                )
        if issues:
            detail = "；".join(
                f"{item['employee_code']}:{item['reason']}" for item in issues
            )
            raise PayrollConfirmationError(
                f"{year_month} 有 {len(issues)} 张工资单未通过确认校验，整批未提交：{detail}",
                issues=issues,
            )

        confirmed: List[Dict[str, Any]] = []
        for record in records:
            assignments, allocations = prepared[record.id]
            basis_version = await LaborCostPolicyService(
                self.db
            ).get_profit_basis_version(record.year_month)
            await ProfitBasisService(
                self.db
            ).lock_profit_basis_snapshots_for_assignments(
                year_month=record.year_month,
                assignments=assignments,
                basis_version=basis_version,
                commit=False,
            )
            record.status = "confirmed"
            locked_at = datetime.now(timezone.utc)
            for allocation in allocations:
                allocation.source_payroll_status = "confirmed"
                allocation.calculation_status = "confirmed"
                allocation.pre_commission_locked_at = locked_at
            confirmed.append(
                {
                    "employee_code": record.employee_code,
                    "record_id": record.id,
                    "status": record.status,
                }
            )
        await self.db.commit()
        return {
            "year_month": year_month,
            "confirmed_count": len(confirmed),
            "confirmed": confirmed,
        }
