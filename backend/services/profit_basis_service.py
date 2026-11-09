from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics
from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.labor_cost_projection_service import (
    LABOR_COST_CALCULATION_VERSION,
)
from modules.core.db import (
    DimFiscalCalendar,
    EmployeeLaborCostAllocation,
    EmployeeShopAssignment,
    ShopProfitBasis,
)


def _shop_key(platform_code: Any, shop_id: Any) -> str:
    return f"{(platform_code or '').lower()}|{str(shop_id or '').lower()}"


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _month_bounds(year_month: str) -> tuple[date, date]:
    period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
    next_month = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return period_start, next_month


class ProfitBasisService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_fiscal_period_exists(
        self, year_month: str, *, commit: bool = True
    ) -> None:
        existing_period = (
            await self.db.execute(
                select(DimFiscalCalendar).where(
                    DimFiscalCalendar.period_code == year_month
                )
            )
        ).scalar_one_or_none()
        if existing_period is not None:
            return

        period_start, next_month = _month_bounds(year_month)
        period = DimFiscalCalendar(
            period_year=period_start.year,
            period_month=period_start.month,
            period_code=year_month,
            start_date=period_start,
            end_date=next_month - timedelta(days=1),
            status="open",
        )
        self.db.add(period)
        if commit:
            await self.db.commit()

    async def _load_orders_profit_amount(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
    ) -> float:
        metrics_by_shop = await load_shop_monthly_metrics(self.db, year_month)
        metric = metrics_by_shop.get(_shop_key(platform_code, shop_id), {})
        return _to_float(metric.get("monthly_profit"))

    async def _load_a_class_cost_amount(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
    ) -> float:
        period_start, next_month = _month_bounds(year_month)
        result = await self.db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS allocated_row_count,
                    COALESCE(SUM(allocated_amt), 0) AS a_class_cost_amount
                FROM finance.fact_expenses_allocated_day_shop_sku
                WHERE allocation_date >= :period_start
                  AND allocation_date < :next_month
                  AND LOWER(platform_code) = LOWER(:platform_code)
                  AND shop_id = :shop_id
                """
            ),
            {
                "period_start": period_start,
                "next_month": next_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
            },
        )
        row = result.mappings().first()
        allocated_amount = _to_float(row.get("a_class_cost_amount") if row else 0.0)
        allocated_row_count = row.get("allocated_row_count") if row else 0
        if allocated_row_count is None:
            if allocated_amount != 0:
                return allocated_amount
        elif int(allocated_row_count) > 0:
            return allocated_amount

        fallback_result = await self.db.execute(
            text(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS a_class_cost_amount
                FROM a_class.operating_costs
                WHERE year_month = :year_month
                  AND deleted_at IS NULL
                  AND LOWER(COALESCE(platform_code, '')) = LOWER(:platform_code)
                  AND shop_id = :shop_id
                """
            ),
            {
                "year_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
            },
        )
        fallback_row = fallback_result.mappings().first()
        return _to_float(
            fallback_row.get("a_class_cost_amount") if fallback_row else 0.0
        )

    async def _load_other_a_class_cost_amount(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
    ) -> float:
        """V2 uses stored operating cost minus legacy manual labor only."""
        result = await self.db.execute(
            text(
                """
                SELECT COALESCE(SUM(
                    COALESCE(
                        total_amount,
                        COALESCE(rent_amount, 0)
                        + COALESCE(marketing_amount, 0)
                        + COALESCE(utility_amount, 0)
                        + COALESCE(ai_token_amount, 0)
                        + COALESCE(labor_amount, 0)
                        + COALESCE(other_amount, 0)
                    ) - COALESCE(labor_amount, 0)
                ), 0) AS a_class_cost_amount
                FROM a_class.operating_costs
                WHERE year_month = :year_month
                  AND deleted_at IS NULL
                  AND LOWER(COALESCE(platform_code, '')) = LOWER(:platform_code)
                  AND shop_id = :shop_id
                """
            ),
            {
                "year_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
            },
        )
        row = result.mappings().first()
        return _to_float(row.get("a_class_cost_amount") if row else 0.0)

    async def _load_pre_commission_labor_amount(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
    ) -> tuple[float, bool]:
        """取这家店当月承担的人力成本。

        两部分：

        1. **直接分摊**：该店自己的 ``allocation_scope='shop'`` 分摊行。
        2. **无归属成本二次分摊**：没有店铺归属的员工（总部、仓库、客服…）
           产生的公司级人力成本，以前**从来没有进过任何一家店的成本** ——
           钱既没消失也没落到谁头上，等于让所有店的利润虚高、提成虚高。
           现在按「各店直接人力成本占比」把它二次分摊到各店。

        分摊比例用「直接人力成本占比」而不是销售额：
        直接人力成本就在这张表里，一次查询算完，不引入额外依赖，
        也不会因为某个月销售额缺失而整月分摊不出来。
        """
        result = await self.db.execute(
            text(
                """
                WITH shop_rows AS (
                    SELECT LOWER(COALESCE(platform_code, '')) AS platform_code,
                           shop_id,
                           SUM(COALESCE(pre_commission_amount, 0)) AS direct_amount
                    FROM finance.employee_labor_cost_allocations
                    WHERE period_month = :year_month
                      AND allocation_scope = 'shop'
                      AND calculation_version = :calculation_version
                    GROUP BY 1, 2
                ),
                company_pool AS (
                    SELECT COALESCE(SUM(COALESCE(pre_commission_amount, 0)), 0) AS pool
                    FROM finance.employee_labor_cost_allocations
                    WHERE period_month = :year_month
                      AND allocation_scope = 'company'
                      AND calculation_version = :calculation_version
                ),
                totals AS (
                    SELECT COALESCE(SUM(direct_amount), 0) AS direct_total,
                           COUNT(*) AS shop_count
                    FROM shop_rows
                )
                SELECT
                    COALESCE((
                        SELECT SUM(direct_amount) FROM shop_rows
                        WHERE platform_code = LOWER(:platform_code)
                          AND shop_id = :shop_id
                    ), 0) AS direct_labor_cost,
                    (SELECT COUNT(*) FROM shop_rows
                      WHERE platform_code = LOWER(:platform_code)
                        AND shop_id = :shop_id) AS allocation_row_count,
                    (SELECT pool FROM company_pool) AS company_pool,
                    (SELECT direct_total FROM totals) AS direct_total,
                    (SELECT shop_count FROM totals) AS shop_count
                """
            ),
            {
                "year_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
                "calculation_version": LABOR_COST_CALCULATION_VERSION,
            },
        )
        row = result.mappings().first()
        if not row:
            return 0.0, False
        direct_labor_cost = _to_float(row.get("direct_labor_cost"))
        company_pool = _to_float(row.get("company_pool"))
        direct_total = _to_float(row.get("direct_total"))
        shop_count = int(row.get("shop_count") or 0)
        if company_pool > 0:
            if direct_total > 0:
                shared = company_pool * (direct_labor_cost / direct_total)
            elif shop_count > 0:
                shared = company_pool / shop_count
            else:
                shared = 0.0
        else:
            shared = 0.0
        return (
            direct_labor_cost + shared,
            bool(int(row.get("allocation_row_count") or 0)),
        )

    async def build_profit_basis(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
        basis_version: str | None = None,
    ) -> dict[str, Any]:
        basis_version = basis_version or await LaborCostPolicyService(
            self.db
        ).get_profit_basis_version(year_month)
        # 「仅 A 类成本」是历史口径，只为复现历史快照保留；
        # 新写入的一律走当前口径（A 类成本 + 提成前人力成本）。
        uses_legacy_a_only = LaborCostPolicyService.is_legacy_a_only_basis_version(
            basis_version
        )
        orders_profit_amount = await self._load_orders_profit_amount(
            year_month, platform_code, shop_id
        )
        if uses_legacy_a_only:
            other_a_class_cost_amount = await self._load_a_class_cost_amount(
                year_month, platform_code, shop_id
            )
        else:
            other_a_class_cost_amount = await self._load_other_a_class_cost_amount(
                year_month, platform_code, shop_id
            )
        pre_commission_labor_cost_amount = 0.0
        cost_status = "legacy"
        if not uses_legacy_a_only:
            labor_cost_result = await self._load_pre_commission_labor_amount(
                year_month, platform_code, shop_id
            )
            if isinstance(labor_cost_result, tuple):
                pre_commission_labor_cost_amount, has_labor_allocation = (
                    labor_cost_result
                )
            else:
                pre_commission_labor_cost_amount = _to_float(labor_cost_result)
                has_labor_allocation = True
            cost_status = (
                "projected" if has_labor_allocation else "missing_labor_allocation"
            )
        a_class_cost_amount = (
            other_a_class_cost_amount + pre_commission_labor_cost_amount
        )
        b_class_cost_amount = 0.0
        profit_basis_amount = orders_profit_amount - a_class_cost_amount

        return {
            "period_month": year_month,
            "platform_code": (platform_code or "").lower(),
            "shop_id": shop_id,
            "orders_profit_amount": orders_profit_amount,
            "a_class_cost_amount": a_class_cost_amount,
            "other_a_class_cost_amount": other_a_class_cost_amount,
            "pre_commission_labor_cost_amount": pre_commission_labor_cost_amount,
            "b_class_cost_amount": b_class_cost_amount,
            "profit_basis_amount": profit_basis_amount,
            "basis_version": basis_version,
            "cost_status": cost_status,
        }

    async def upsert_profit_basis_snapshot(
        self,
        payload: dict[str, Any],
        *,
        commit: bool = True,
    ) -> dict[str, Any]:
        await self.ensure_fiscal_period_exists(payload["period_month"], commit=commit)

        # 一个「月份 + 店铺」只有**一条**利润基数快照。
        # 以前唯一键是 (月份, 店, 版本)，口径切换后同一家店会多出一条行，
        # 同一个事实存了两份 —— 读的时候靠「挑一条」来糊弄，正是 SSOT 要消灭的。
        # 版本是这条快照的**属性**，重算时更新，不用来区分行。
        record = (
            (
                await self.db.execute(
                    select(ShopProfitBasis)
                    .where(
                        ShopProfitBasis.period_month == payload["period_month"],
                        ShopProfitBasis.platform_code == payload["platform_code"],
                        ShopProfitBasis.shop_id == payload["shop_id"],
                    )
                    .order_by(ShopProfitBasis.id.desc())
                )
            )
            .scalars()
            .first()
        )

        if record is None:
            record = ShopProfitBasis(**payload)
            self.db.add(record)
        else:
            if bool(getattr(record, "is_locked", False)):
                locked_values = (
                    record.orders_profit_amount,
                    record.a_class_cost_amount,
                    getattr(record, "other_a_class_cost_amount", 0.0),
                    getattr(record, "pre_commission_labor_cost_amount", 0.0),
                    record.b_class_cost_amount,
                    record.profit_basis_amount,
                )
                requested_values = (
                    payload["orders_profit_amount"],
                    payload["a_class_cost_amount"],
                    payload.get("other_a_class_cost_amount", 0.0),
                    payload.get("pre_commission_labor_cost_amount", 0.0),
                    payload["b_class_cost_amount"],
                    payload["profit_basis_amount"],
                )
                if any(
                    round(_to_float(locked), 2) != round(_to_float(requested), 2)
                    for locked, requested in zip(locked_values, requested_values)
                ):
                    raise ValueError(
                        "profit basis is locked; reopen settlement before rebuild"
                    )
                return payload
            record.orders_profit_amount = payload["orders_profit_amount"]
            record.a_class_cost_amount = payload["a_class_cost_amount"]
            record.other_a_class_cost_amount = payload.get(
                "other_a_class_cost_amount", 0.0
            )
            record.pre_commission_labor_cost_amount = payload.get(
                "pre_commission_labor_cost_amount", 0.0
            )
            record.b_class_cost_amount = payload["b_class_cost_amount"]
            record.profit_basis_amount = payload["profit_basis_amount"]
            record.cost_status = payload.get("cost_status", "projected")
            record.basis_version = payload["basis_version"]

        if commit:
            await self.db.commit()
        return payload

    async def rebuild_month_v2(
        self,
        year_month: str,
        *,
        commit: bool = True,
    ) -> dict[str, Any]:
        """Rebuild one V2 snapshot for every active assigned shop in a month."""
        assignments = (
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
        shops = sorted(
            {
                (
                    str(getattr(row, "platform_code", "") or "").lower(),
                    str(getattr(row, "shop_id", "") or ""),
                )
                for row in assignments
                if str(getattr(row, "platform_code", "") or "").strip()
                and str(getattr(row, "shop_id", "") or "").strip()
            }
        )
        for platform_code, shop_id in shops:
            payload = await self.build_profit_basis(
                year_month,
                platform_code,
                shop_id,
                basis_version=LaborCostPolicyService.CURRENT_BASIS_VERSION,
            )
            await self.upsert_profit_basis_snapshot(payload, commit=False)
        if commit:
            await self.db.commit()
        return {"year_month": year_month, "shop_count": len(shops)}

    async def lock_profit_basis_snapshot(
        self,
        *,
        year_month: str,
        platform_code: str,
        shop_id: str,
        basis_version: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        basis_version = basis_version or await LaborCostPolicyService(
            self.db
        ).get_profit_basis_version(year_month)
        record = (
            (
                await self.db.execute(
                    select(ShopProfitBasis)
                    .where(
                        ShopProfitBasis.period_month == year_month,
                        ShopProfitBasis.platform_code == (platform_code or "").lower(),
                        ShopProfitBasis.shop_id == shop_id,
                    )
                    .order_by(ShopProfitBasis.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if record is None:
            raise ValueError("profit basis snapshot not found; rebuild before locking")
        if not LaborCostPolicyService.is_settlement_basis_version(
            getattr(record, "basis_version", "")
        ):
            raise ValueError(
                "profit basis snapshot uses an unknown basis version; rebuild before locking"
            )
        record.is_locked = True
        # 注意：这里**不再**连带把人力成本分摊标记为 locked。
        # 锁定基数时，人力成本金额已经快照进 ``pre_commission_labor_cost_amount``，
        # 基数自带成本快照，不依赖分摊行的锁状态。
        # 旧实现会让「财务锁一次基数」变成「整月人力成本不可再改」，
        # 归属填错或薪资调整后没有任何干净的修正路径。
        # 人力成本分摊的锁定时机统一由「工资单确认」负责。
        if commit:
            await self.db.commit()
        return {
            "period_month": record.period_month,
            "platform_code": record.platform_code,
            "shop_id": record.shop_id,
            "basis_version": record.basis_version,
            "profit_basis_amount": _to_float(record.profit_basis_amount),
            "is_locked": True,
        }

    async def reopen_profit_basis_snapshot(
        self,
        *,
        year_month: str,
        platform_code: str,
        shop_id: str,
        basis_version: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        """重开（解锁）已锁定的利润基数，允许修正后重算。

        这是「锁定有明确边界和撤回路径」的落点：发现归属或成本填错时，
        显式重开，而不是被隐式锁死。
        """
        basis_version = basis_version or await LaborCostPolicyService(
            self.db
        ).get_profit_basis_version(year_month)
        record = (
            await self.db.execute(
                select(ShopProfitBasis).where(
                    ShopProfitBasis.period_month == year_month,
                    ShopProfitBasis.platform_code == (platform_code or "").lower(),
                    ShopProfitBasis.shop_id == shop_id,
                    ShopProfitBasis.basis_version == basis_version,
                )
            )
        ).scalar_one_or_none()
        if record is None:
            raise ValueError("profit basis snapshot not found")
        record.is_locked = False
        if commit:
            await self.db.commit()
        return {
            "period_month": record.period_month,
            "platform_code": record.platform_code,
            "shop_id": record.shop_id,
            "basis_version": record.basis_version,
            "profit_basis_amount": _to_float(record.profit_basis_amount),
            "is_locked": False,
        }

    async def lock_profit_basis_snapshots_for_assignments(
        self,
        *,
        year_month: str,
        assignments: list[Any],
        basis_version: str,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        """Persist and lock one profit-basis snapshot per assigned operating shop."""
        unique_shops: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for assignment in assignments:
            platform_code = str(getattr(assignment, "platform_code", "") or "").lower()
            shop_id = str(getattr(assignment, "shop_id", "") or "")
            if not platform_code or not shop_id or (platform_code, shop_id) in seen:
                continue
            seen.add((platform_code, shop_id))
            unique_shops.append((platform_code, shop_id))

        locked_snapshots: list[dict[str, Any]] = []
        for platform_code, shop_id in unique_shops:
            payload = await self.build_profit_basis(
                year_month,
                platform_code,
                shop_id,
                basis_version=basis_version,
            )
            await self.upsert_profit_basis_snapshot(payload, commit=False)
            locked_snapshots.append(
                await self.lock_profit_basis_snapshot(
                    year_month=year_month,
                    platform_code=platform_code,
                    shop_id=shop_id,
                    basis_version=basis_version,
                    commit=False,
                )
            )
        if commit:
            await self.db.commit()
        return locked_snapshots

    @staticmethod
    def calculate_distributable_amount(
        profit_basis_amount: float,
        distribution_ratio: float,
    ) -> float:
        if profit_basis_amount <= 0:
            return 0.0
        return round(profit_basis_amount * distribution_ratio, 2)
