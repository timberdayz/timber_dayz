from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.postgresql_shop_metrics_service import load_shop_monthly_metrics
from modules.core.db import DimFiscalCalendar, ShopProfitBasis


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

    async def ensure_fiscal_period_exists(self, year_month: str) -> None:
        existing_period = (
            await self.db.execute(
                select(DimFiscalCalendar).where(DimFiscalCalendar.period_code == year_month)
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
                SELECT COALESCE(SUM("成本合计"), 0) AS a_class_cost_amount
                FROM a_class.operating_costs
                WHERE "年月" = :year_month
                  AND "删除时间" IS NULL
                  AND LOWER(COALESCE(platform_code, '')) = LOWER(:platform_code)
                  AND "店铺ID" = :shop_id
                """
            ),
            {
                "year_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
            },
        )
        fallback_row = fallback_result.mappings().first()
        return _to_float(fallback_row.get("a_class_cost_amount") if fallback_row else 0.0)

    async def build_profit_basis(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
        basis_version: str = "A_ONLY_V1",
    ) -> dict[str, Any]:
        orders_profit_amount = await self._load_orders_profit_amount(year_month, platform_code, shop_id)
        a_class_cost_amount = await self._load_a_class_cost_amount(year_month, platform_code, shop_id)
        b_class_cost_amount = 0.0
        profit_basis_amount = orders_profit_amount - a_class_cost_amount

        return {
            "period_month": year_month,
            "platform_code": (platform_code or "").lower(),
            "shop_id": shop_id,
            "orders_profit_amount": orders_profit_amount,
            "a_class_cost_amount": a_class_cost_amount,
            "b_class_cost_amount": b_class_cost_amount,
            "profit_basis_amount": profit_basis_amount,
            "basis_version": basis_version,
        }

    async def upsert_profit_basis_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.ensure_fiscal_period_exists(payload["period_month"])

        record = (
            await self.db.execute(
                select(ShopProfitBasis).where(
                    ShopProfitBasis.period_month == payload["period_month"],
                    ShopProfitBasis.platform_code == payload["platform_code"],
                    ShopProfitBasis.shop_id == payload["shop_id"],
                    ShopProfitBasis.basis_version == payload["basis_version"],
                )
            )
        ).scalar_one_or_none()

        if record is None:
            record = ShopProfitBasis(**payload)
            self.db.add(record)
        else:
            record.orders_profit_amount = payload["orders_profit_amount"]
            record.a_class_cost_amount = payload["a_class_cost_amount"]
            record.b_class_cost_amount = payload["b_class_cost_amount"]
            record.profit_basis_amount = payload["profit_basis_amount"]

        await self.db.commit()
        return payload

    @staticmethod
    def calculate_distributable_amount(
        profit_basis_amount: float,
        distribution_ratio: float,
    ) -> float:
        if profit_basis_amount <= 0:
            return 0.0
        return round(profit_basis_amount * distribution_ratio, 2)
