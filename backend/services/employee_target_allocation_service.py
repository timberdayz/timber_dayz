from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics

from modules.core.db import (
    DimShop,
    Employee,
    EmployeeShopAssignment,
    SalesTarget,
    TargetBreakdown,
    ShopAccount,
)


def _number(value: Any) -> float:
    return float(value or 0)


def _achievement_rate(actual: float, target: float) -> float:
    return actual / target if target else 0.0


def _shop_key(platform_code: str | None, shop_id: str | None) -> tuple[str, str]:
    return ((platform_code or "").lower(), str(shop_id or ""))


def build_employee_target_summary(
    *,
    employee_code: str,
    employee_name: str | None,
    assignments: list[Any],
    shop_targets: dict[tuple[str, str], dict[str, Any]],
    shop_actuals: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    shops: list[dict[str, Any]] = []
    for assignment in assignments:
        key = _shop_key(
            getattr(assignment, "platform_code", None),
            getattr(assignment, "shop_id", None),
        )
        source = shop_targets.get(key, {})
        actuals = shop_actuals.get(key, {})
        sales_target = _number(source.get("sales_target"))
        sales_actual = _number(actuals.get("monthly_sales"))
        gross_profit_target = _number(source.get("gross_profit_target"))
        gross_profit_actual = _number(actuals.get("monthly_profit"))
        shops.append(
            {
                "platform_code": key[0],
                "shop_id": key[1],
                "shop_name": source.get("shop_name") or key[1],
                "responsibility_mode": "shared_shop_target",
                "sales_target": sales_target,
                "sales_actual": sales_actual,
                "sales_achievement_rate": _achievement_rate(sales_actual, sales_target),
                "gross_profit_target": gross_profit_target,
                "gross_profit_actual": gross_profit_actual,
                "gross_profit_achievement_rate": _achievement_rate(
                    gross_profit_actual, gross_profit_target
                ),
            }
        )

    sales_target = sum(row["sales_target"] for row in shops)
    sales_actual = sum(row["sales_actual"] for row in shops)
    gross_profit_target = sum(row["gross_profit_target"] for row in shops)
    gross_profit_actual = sum(row["gross_profit_actual"] for row in shops)
    return {
        "employee_code": employee_code,
        "employee_name": employee_name,
        "sales_target": sales_target,
        "sales_actual": sales_actual,
        "sales_achievement_rate": _achievement_rate(sales_actual, sales_target),
        "gross_profit_target": gross_profit_target,
        "gross_profit_actual": gross_profit_actual,
        "gross_profit_achievement_rate": _achievement_rate(
            gross_profit_actual, gross_profit_target
        ),
        "shops": shops,
    }


class EmployeeTargetAllocationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_summaries(
        self,
        *,
        year_month: str,
        employee_code: str | None = None,
    ) -> list[dict[str, Any]]:
        assignments = (
            await self.db.execute(
                select(EmployeeShopAssignment)
                .join(
                    ShopAccount,
                    and_(
                        func.lower(ShopAccount.platform) == func.lower(EmployeeShopAssignment.platform_code),
                        ShopAccount.enabled == True,
                        ShopAccount.business_role == "operating_store",
                        or_(
                            ShopAccount.platform_shop_id == EmployeeShopAssignment.shop_id,
                            ShopAccount.shop_account_id == EmployeeShopAssignment.shop_id,
                        ),
                    ),
                )
                .where(
                    EmployeeShopAssignment.year_month == year_month,
                    EmployeeShopAssignment.status == "active",
                )
            )
        ).scalars().all()
        selected_assignments = [
            row for row in assignments if employee_code is None or row.employee_code == employee_code
        ]
        if not selected_assignments:
            return []

        employee_codes = {row.employee_code for row in selected_assignments}
        employees = (
            await self.db.execute(
                select(Employee).where(Employee.employee_code.in_(employee_codes))
            )
        ).scalars().all()
        employee_names = {row.employee_code: row.name for row in employees}
        shop_targets = await self._load_shop_targets(year_month)
        metrics_by_shop = await load_shop_monthly_metrics(self.db, year_month)
        shop_actuals = {}
        for key, metrics in metrics_by_shop.items():
            platform_code, shop_id = key.split("|", maxsplit=1)
            shop_actuals[_shop_key(platform_code, shop_id)] = metrics

        by_employee: dict[str, list[Any]] = {}
        for assignment in selected_assignments:
            by_employee.setdefault(assignment.employee_code, []).append(assignment)
        return [
            build_employee_target_summary(
                employee_code=code,
                employee_name=employee_names.get(code),
                assignments=employee_assignments,
                shop_targets=shop_targets,
                shop_actuals=shop_actuals,
            )
            for code, employee_assignments in sorted(by_employee.items())
        ]


    async def _load_shop_targets(self, year_month: str) -> dict[tuple[str, str], dict[str, Any]]:
        year, month = (int(part) for part in year_month.split("-"))
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        targets = (
            await self.db.execute(
                select(SalesTarget)
                .where(
                    SalesTarget.target_type == "shop",
                    SalesTarget.status == "active",
                    SalesTarget.period_start <= month_end,
                    SalesTarget.period_end >= month_start,
                )
                .order_by(SalesTarget.created_at.desc(), SalesTarget.id.desc())
            )
        ).scalars().all()
        if not targets:
            return {}
        target_ids = [target.id for target in targets]
        breakdowns = (
            await self.db.execute(
                select(TargetBreakdown).where(
                    and_(
                        TargetBreakdown.target_id.in_(target_ids),
                        TargetBreakdown.breakdown_type == "shop",
                    )
                )
            )
        ).scalars().all()
        shop_keys = {
            _shop_key(row.platform_code, row.shop_id)
            for row in breakdowns
            if row.platform_code and row.shop_id
        }
        shops = (
            await self.db.execute(
                select(DimShop).where(
                    tuple_(DimShop.platform_code, DimShop.shop_id).in_(shop_keys)
                )
            )
        ).scalars().all() if shop_keys else []
        shop_names = {
            _shop_key(shop.platform_code, shop.shop_id): shop.shop_name for shop in shops
        }
        priority = {target.id: index for index, target in enumerate(targets)}
        shop_targets: dict[tuple[str, str], dict[str, Any]] = {}
        for breakdown in sorted(breakdowns, key=lambda row: priority[row.target_id]):
            key = _shop_key(breakdown.platform_code, breakdown.shop_id)
            if key in shop_targets:
                continue
            shop_targets[key] = {
                "shop_name": shop_names.get(key),
                "sales_target": _number(breakdown.target_amount),
                "gross_profit_target": _number(breakdown.target_profit_amount),
            }
        return shop_targets
