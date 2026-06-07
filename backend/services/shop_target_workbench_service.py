from __future__ import annotations

import inspect
from calendar import monthrange
from datetime import date
from types import SimpleNamespace
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.target import (
    ShopTargetWorkbenchApplyRequest,
    ShopTargetWorkbenchApplyResponse,
    ShopTargetWorkbenchResponse,
    ShopTargetWorkbenchShopResponse,
)
from backend.services.target_sync_service import TargetSyncService
from modules.core.db import SalesTarget, ShopAccount, ShopAccountAlias, TargetBreakdown


class ShopTargetWorkbenchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_workbench(self, year_month: str) -> ShopTargetWorkbenchResponse:
        month_start, month_end = self._month_range(year_month)
        target = await self._find_month_target(month_start, month_end)
        shops = await self._list_active_shops()
        breakdowns = await self._list_breakdowns(target.id) if target else []

        shop_breakdowns = {
            (item.platform_code, item.shop_id): item
            for item in breakdowns
            if item.breakdown_type == "shop"
        }
        daily_counts: dict[tuple[str, str], int] = {}
        for item in breakdowns:
            if item.breakdown_type == "shop_time" and item.platform_code and item.shop_id:
                key = (item.platform_code, item.shop_id)
                daily_counts[key] = daily_counts.get(key, 0) + 1

        total_amount = float(target.target_amount or 0.0) if target else 0.0
        response_shops = []
        for shop in shops:
            key = (shop.platform_code, shop.shop_id)
            breakdown = shop_breakdowns.get(key)
            amount = float(getattr(breakdown, "target_amount", 0.0) or 0.0)
            response_shops.append(
                ShopTargetWorkbenchShopResponse(
                    platform_code=shop.platform_code,
                    shop_id=shop.shop_id,
                    standard_name=shop.standard_name,
                    aliases=shop.aliases,
                    ratio=(amount / total_amount) if total_amount else 0.0,
                    target_amount=amount,
                    target_quantity=int(getattr(breakdown, "target_quantity", 0) or 0),
                    daily_target_count=daily_counts.get(key, 0),
                )
            )

        return ShopTargetWorkbenchResponse(
            year_month=year_month,
            target_id=getattr(target, "id", None),
            company_target_amount=total_amount,
            company_target_quantity=int(getattr(target, "target_quantity", 0) or 0) if target else 0,
            shops=response_shops,
        )

    async def apply(
        self,
        request: ShopTargetWorkbenchApplyRequest,
        username: str | None = None,
    ) -> ShopTargetWorkbenchApplyResponse:
        month_start, month_end = self._month_range(request.year_month)
        target = await self._find_month_target(month_start, month_end)
        if target is None:
            target = SalesTarget(
                target_name=f"{request.year_month} 店铺销售目标",
                target_type="shop",
                scope_type="shop",
                period_start=month_start,
                period_end=month_end,
                status="active",
                created_by=username,
            )
            await self._add(target)

        target.target_amount = request.company_target_amount
        target.target_quantity = request.company_target_quantity
        target.target_profit_amount = getattr(target, "target_profit_amount", 0.0) or 0.0
        target.description = "店铺目标工作台维护"

        await self.db.flush()
        cleanup_result = await self.cleanup_projection(target.id)
        if cleanup_result.get("errors"):
            raise RuntimeError("; ".join(cleanup_result["errors"]))
        await self._replace_breakdowns(target.id, request, month_start, month_end)

        sync_result = await self.sync_projection(target.id)
        if sync_result.get("errors"):
            raise RuntimeError("; ".join(sync_result["errors"]))

        await self.db.commit()
        return ShopTargetWorkbenchApplyResponse(
            year_month=request.year_month,
            target_id=target.id,
            synced=int(sync_result.get("synced", 0) or 0),
            errors=sync_result.get("errors", []),
        )

    async def copy_prev_month(
        self,
        year_month: str,
        username: str | None = None,
    ) -> ShopTargetWorkbenchApplyResponse:
        month_start, _ = self._month_range(year_month)
        prev_year = month_start.year if month_start.month > 1 else month_start.year - 1
        prev_month = month_start.month - 1 if month_start.month > 1 else 12
        previous = await self.get_workbench(f"{prev_year:04d}-{prev_month:02d}")
        request = ShopTargetWorkbenchApplyRequest(
            year_month=year_month,
            company_target_amount=previous.company_target_amount,
            company_target_quantity=previous.company_target_quantity,
            shops=[
                {
                    "platform_code": shop.platform_code,
                    "shop_id": shop.shop_id,
                    "ratio": shop.ratio,
                    "target_amount": shop.target_amount,
                    "target_quantity": shop.target_quantity,
                }
                for shop in previous.shops
                if shop.target_amount or shop.target_quantity
            ],
        )
        return await self.apply(request, username=username)

    async def sync_projection(self, target_id: int):
        return await TargetSyncService(self.db).sync_target_to_a_class(target_id, commit=False)

    async def cleanup_projection(self, target_id: int):
        return await TargetSyncService(self.db).delete_target_from_a_class(target_id, commit=False)

    async def _find_month_target(self, month_start: date, month_end: date):
        result = await self.db.execute(
            select(SalesTarget)
            .where(SalesTarget.target_type == "shop")
            .where(SalesTarget.status == "active")
            .where(SalesTarget.period_start <= month_end)
            .where(SalesTarget.period_end >= month_start)
            .order_by(SalesTarget.created_at.desc(), SalesTarget.id.desc())
        )
        return result.scalar_one_or_none()

    async def _list_active_shops(self):
        result = await self.db.execute(
            select(ShopAccount)
            .where(ShopAccount.enabled.is_(True))
            .order_by(ShopAccount.platform.asc(), ShopAccount.store_name.asc(), ShopAccount.shop_account_id.asc())
        )
        records = result.scalars().all()
        shops = []
        for record in records:
            alias_result = await self.db.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id == record.id,
                    ShopAccountAlias.is_active.is_(True),
                )
            )
            alias_records = alias_result.scalars().all()
            aliases = [alias.alias_value for alias in alias_records if getattr(alias, "alias_value", None)]
            shop_id = (
                str(getattr(record, "platform_shop_id", "") or "").strip()
                or str(getattr(record, "shop_account_id", "") or "").strip()
            )
            shops.append(
                SimpleNamespace(
                    platform_code=str(getattr(record, "platform", "") or "").strip().lower(),
                    shop_id=shop_id,
                    standard_name=str(getattr(record, "store_name", "") or "").strip() or shop_id,
                    aliases=aliases,
                )
            )
        return shops

    async def _list_breakdowns(self, target_id: int):
        result = await self.db.execute(select(TargetBreakdown).where(TargetBreakdown.target_id == target_id))
        return result.scalars().all()

    async def _replace_breakdowns(
        self,
        target_id: int,
        request: ShopTargetWorkbenchApplyRequest,
        month_start: date,
        month_end: date,
    ) -> None:
        await self.db.execute(delete(TargetBreakdown).where(TargetBreakdown.target_id == target_id))
        days = monthrange(month_start.year, month_start.month)[1]
        daily_company_amount = request.company_target_amount / days if days else 0.0
        daily_company_quantity = request.company_target_quantity // days if days else 0

        for day in range(1, days + 1):
            current = date(month_start.year, month_start.month, day)
            await self._add(
                TargetBreakdown(
                    target_id=target_id,
                    breakdown_type="time",
                    period_start=current,
                    period_end=current,
                    period_label=current.isoformat(),
                    target_amount=daily_company_amount,
                    target_quantity=daily_company_quantity,
                )
            )

        for shop in request.shops:
            await self._add(
                TargetBreakdown(
                    target_id=target_id,
                    breakdown_type="shop",
                    platform_code=shop.platform_code,
                    shop_id=shop.shop_id,
                    period_start=month_start,
                    period_end=month_end,
                    period_label=request.year_month,
                    target_amount=shop.target_amount,
                    target_quantity=shop.target_quantity,
                )
            )
            daily_amount = shop.target_amount / days if days else 0.0
            daily_quantity = shop.target_quantity // days if days else 0
            for day in range(1, days + 1):
                current = date(month_start.year, month_start.month, day)
                await self._add(
                    TargetBreakdown(
                        target_id=target_id,
                        breakdown_type="shop_time",
                        platform_code=shop.platform_code,
                        shop_id=shop.shop_id,
                        period_start=current,
                        period_end=current,
                        period_label=current.isoformat(),
                        target_amount=daily_amount,
                        target_quantity=daily_quantity,
                    )
                )

    async def _add(self, obj) -> None:
        result = self.db.add(obj)
        if inspect.isawaitable(result):
            await result

    def _month_range(self, year_month: str) -> tuple[date, date]:
        year, month = [int(part) for part in year_month.split("-")]
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
