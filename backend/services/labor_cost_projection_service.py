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
from backend.services.payroll_period_lock_service import PAYROLL_LOCKED_STATUSES


MONEY_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.000001")

#: 人力成本分摊口径的**当前**标识，写入
#: ``finance.employee_labor_cost_allocations.calculation_version``。
#:
#: 以前叫 ``LABOR_COST_V2`` —— 那是上线期的过渡叫法，和历史遗留的
#: ``LABOR_COST_V1`` 行并存，看起来像「两个版本在同时跑」，其实业务上
#: 早就只有一个口径（责任比例加权 + 公司级无归属成本二次分摊）。
#: 名字带着序号只会让人以为还有第二个口径，所以改成中性名
#: ``LABOR_COST_ALLOC_V1``（与利润基数的 ``SETTLEMENT_BASIS_V1`` 同一风格：
#: 「V1」表示「这是收敛后的唯一一版口径」，不是「还有一个 V2」）。
#:
#: 历史 ``LABOR_COST_V1`` 行**保留原值不改写** —— 那一行是旧算法算出来的，
#: 改名字等于伪造历史；读端只认当前口径（按本常量过滤），
#: 所以它们不会参与任何当期计算。
LABOR_COST_CALCULATION_VERSION = "LABOR_COST_ALLOC_V1"

#: 历史口径值，仅用于识别旧行（不改写、不参与当期计算）。
LEGACY_LABOR_COST_CALCULATION_VERSIONS = ("LABOR_COST_V1",)


class LaborCostProjectionService:
    """Build reusable store-level labor-cost allocations from payroll data."""

    #: 「提成前人力成本」包含的工资项。
    #:
    #: **口径决策：绩效工资（performance_salary）和提成本身不在这里。**
    #:
    #: 提成基数是「提成**前**利润」，绩效工资属于提成**之后**的支出；
    #: 把它算进成本基数等于同一笔钱扣两次（先压低基数、再算提成），
    #: 分母越缩越小，金额波动被放大。
    #:
    #: 这条决策由业务确认（2026-11），与
    #: :attr:`LaborCostPolicyService.EXCLUDED_COST_FIELDS` 保持一致。
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
    def _split_by_weight(
        cls, amount: Decimal, weights: list[float]
    ) -> list[Decimal]:
        """按权重把一笔钱拆开，最后一笔吃掉舍入误差。

        权重 = 责任比例（``employee_shop_assignments.commission_ratio``）：
        一个人在 A 店拿 60%、B 店拿 40%，他的工资就应该按 60/40 分到两家店。
        以前是**按人头平均分**，等于让只负责一家的主管和负责三家的主管一样分摊，
        责任越大的人反而越轻 —— 这是分摊口径的实打实的错误。
        """
        if not weights:
            return []
        total = sum(weight for weight in weights if weight > 0)
        if total <= 0:
            # 没配责任比例时退回平均分，避免除零。
            return cls._split_evenly(amount, len(weights))
        values: list[Decimal] = []
        remaining = amount
        for index, weight in enumerate(weights):
            if index == len(weights) - 1:
                values.append(remaining)
                break
            share = (
                amount * Decimal(str(weight)) / Decimal(str(total))
            ).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
            values.append(share)
            remaining -= share
        return values

    @classmethod
    def _allocation_weights(cls, assignments: list[Any]) -> list[float]:
        """每个归属行的责任权重；全为 0 时退化成等权。"""
        weights = []
        for assignment in assignments:
            try:
                weight = float(getattr(assignment, "commission_ratio", 0) or 0)
            except (TypeError, ValueError):
                weight = 0.0
            weights.append(weight if weight > 0 else 0.0)
        if sum(weights) <= 0:
            return [1.0] * len(assignments)
        return weights

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

        分摊口径：**按责任比例加权**（见 :meth:`_split_by_weight`），
        不是按人头平均。
        """
        active_assignments = [
            assignment
            for assignment in assignments
            if str(getattr(assignment, "status", "active") or "active") == "active"
        ]
        pre_commission = sum(
            (
                cls._money(getattr(payroll, field, 0))
                for field in cls.PRE_COMMISSION_FIELDS
            ),
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

        weights = cls._allocation_weights(active_assignments)
        pre_parts = cls._split_by_weight(pre_commission, weights)
        performance_parts = cls._split_by_weight(performance, weights)
        weight_total = sum(weights)
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
                    "allocation_ratio": (
                        (Decimal(str(weights[index])) / Decimal(str(weight_total)))
                        .quantize(RATIO_QUANT, rounding=ROUND_HALF_UP)
                        if weight_total > 0
                        else Decimal("0").quantize(RATIO_QUANT)
                    ),
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
        commission_by_employee_shop: (
            Mapping[str, Mapping[tuple[str, str], Any]] | None
        ) = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        payroll_rows = (
            (
                await self.db.execute(
                    select(PayrollRecord).where(PayrollRecord.year_month == year_month)
                )
            )
            .scalars()
            .all()
        )
        assignment_rows = (
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
        existing_rows = (
            (
                await self.db.execute(
                    select(EmployeeLaborCostAllocation).where(
                        EmployeeLaborCostAllocation.period_month == year_month,
                        EmployeeLaborCostAllocation.calculation_version
                        == LABOR_COST_CALCULATION_VERSION,
                    )
                )
            )
            .scalars()
            .all()
        )

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
                commission_by_employee.setdefault(employee_code, {})[
                    (platform_code, shop_id)
                ] = self._money(getattr(record, "commission_amount", 0))

        for employee_code, values in (commission_by_employee_shop or {}).items():
            commission_by_employee[str(employee_code)] = {
                (str(platform_code or "").lower(), str(shop_id or "")): self._money(
                    amount
                )
                for (platform_code, shop_id), amount in values.items()
            }

        allocation_upserts = 0
        target_keys: set[tuple[str, str, str, str]] = set()
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
                target_keys.add(key)
                record = existing_by_key.get(key)
                if record is not None and getattr(
                    record, "pre_commission_locked_at", None
                ):
                    if (
                        self._money(getattr(record, "pre_commission_amount", 0))
                        != row["pre_commission_amount"]
                    ):
                        raise ValueError(
                            f"pre-commission labor cost is locked for {employee_code}; reopen settlement before refresh"
                        )

                status = (
                    "confirmed"
                    if row["source_payroll_status"] in PAYROLL_LOCKED_STATUSES
                    else "projected"
                )
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

        # ── 清理陈旧分配行 ──
        #
        # 以前这个方法**只 upsert、从不删除** ⇒ 员工换店、归属比例调整、
        # 或者某个月的工资单被删掉之后，他原来那些「已经不成立」的分摊行
        # 会**永久留在表里**，而看板/利润基数是把整张表 SUM 起来用的
        # ⇒ 同一份人力成本被重复计入。
        #
        # 判定标准很简单：这次算出来的 key 集合里没有、但表里有的行 ⇒ 陈旧。
        # 已锁定（pre_commission_locked_at 有值）的行**不删**，直接报错 ——
        # 那行已经被月结引用，删了等于偷偷改已结账的钱，必须人工退回再重算。
        stale_deleted = 0
        stale_locked: list[tuple[str, str, str, str]] = []
        for key, record in existing_by_key.items():
            if key in target_keys:
                continue
            if getattr(record, "pre_commission_locked_at", None):
                stale_locked.append(key)
                continue
            await self.db.delete(record)
            stale_deleted += 1

        if stale_locked:
            raise ValueError(
                "labor cost allocations are locked but no longer produced by the "
                f"current calculation for {year_month}: {stale_locked}; "
                "reopen settlement before refresh"
            )

        if commit:
            await self.db.commit()
        return {
            "year_month": year_month,
            "allocation_upserts": allocation_upserts,
            "allocation_stale_deleted": stale_deleted,
        }
