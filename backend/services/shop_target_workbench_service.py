from __future__ import annotations

import inspect
from calendar import monthrange
from datetime import date, datetime, timezone
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
from modules.core.db import DimShop, SalesTarget, ShopAccount, ShopAccountAlias, TargetBreakdown


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
            weekday_ratios=getattr(target, "weekday_ratios", None) or self._default_weekday_ratios(),
            shops=response_shops,
        )

    async def apply(
        self,
        request: ShopTargetWorkbenchApplyRequest,
        username: str | None = None,
    ) -> ShopTargetWorkbenchApplyResponse:
        self._validate_request(request)
        month_start, month_end = self._month_range(request.year_month)
        month_targets = await self._list_month_targets(month_start, month_end)
        target = month_targets[0] if month_targets else None
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

        target.status = "active"
        target.target_amount = request.company_target_amount
        target.target_quantity = request.company_target_quantity
        target.target_profit_amount = getattr(target, "target_profit_amount", 0.0) or 0.0
        target.weekday_ratios = self._normalize_weekday_ratios(request.weekday_ratios)
        target.description = "店铺目标工作台维护"
        target.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self._deactivate_older_month_targets(month_targets, target.id)
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
            weekday_ratios=previous.weekday_ratios,
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
        targets = await self._list_month_targets(month_start, month_end)
        return targets[0] if targets else None

    async def _list_month_targets(self, month_start: date, month_end: date):
        result = await self.db.execute(
            select(SalesTarget)
            .where(SalesTarget.target_type == "shop")
            .where(SalesTarget.status == "active")
            .where(SalesTarget.period_start <= month_end)
            .where(SalesTarget.period_end >= month_start)
            .order_by(SalesTarget.updated_at.desc(), SalesTarget.created_at.desc(), SalesTarget.id.desc())
        )
        return result.scalars().all()

    async def _deactivate_older_month_targets(self, month_targets, current_target_id: int) -> None:
        for target in month_targets:
            if getattr(target, "id", None) == current_target_id:
                continue
            target.status = "inactive"
            cleanup_result = await self.cleanup_projection(target.id)
            if cleanup_result.get("errors"):
                raise RuntimeError("; ".join(cleanup_result["errors"]))

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
            shop_id = await self._resolve_shop_target_id(record)
            shops.append(
                SimpleNamespace(
                    platform_code=str(getattr(record, "platform", "") or "").strip().lower(),
                    shop_id=shop_id,
                    standard_name=str(getattr(record, "store_name", "") or "").strip() or shop_id,
                    aliases=aliases,
                )
            )
        return shops

    async def _resolve_shop_target_id(self, record: ShopAccount) -> str:
        platform_code = str(getattr(record, "platform", "") or "").strip().lower()
        store_name = str(getattr(record, "store_name", "") or "").strip()
        candidates = [
            str(getattr(record, "platform_shop_id", "") or "").strip(),
            str(getattr(record, "shop_account_id", "") or "").strip(),
        ]
        candidates = [candidate for candidate in candidates if candidate]

        for candidate in candidates:
            matched = await self.db.execute(
                select(DimShop.shop_id).where(
                    DimShop.platform_code == platform_code,
                    DimShop.shop_id == candidate,
                )
            )
            shop_id = matched.scalar_one_or_none()
            if shop_id:
                return str(shop_id)

        if store_name:
            matched = await self.db.execute(
                select(DimShop.shop_id).where(
                    DimShop.platform_code == platform_code,
                    DimShop.shop_name == store_name,
                )
            )
            shop_id = matched.scalar_one_or_none()
            if shop_id:
                return str(shop_id)

        return candidates[0] if candidates else store_name

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
        day_weights = self._month_day_weights(month_start, days, request.weekday_ratios)
        total_weight = sum(weight for _, weight in day_weights) or 1.0

        company_daily_amounts = self._split_amount_by_weights(request.company_target_amount, day_weights, total_weight)
        company_daily_quantities = self._split_quantity_by_weights(request.company_target_quantity, day_weights, total_weight)
        for idx, (current, _) in enumerate(day_weights):
            await self._add(
                TargetBreakdown(
                    target_id=target_id,
                    breakdown_type="time",
                    period_start=current,
                    period_end=current,
                    period_label=current.isoformat(),
                    target_amount=company_daily_amounts[idx],
                    target_quantity=company_daily_quantities[idx],
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
            shop_daily_amounts = self._split_amount_by_weights(shop.target_amount, day_weights, total_weight)
            shop_daily_quantities = self._split_quantity_by_weights(shop.target_quantity, day_weights, total_weight)
            for idx, (current, _) in enumerate(day_weights):
                await self._add(
                    TargetBreakdown(
                        target_id=target_id,
                        breakdown_type="shop_time",
                        platform_code=shop.platform_code,
                        shop_id=shop.shop_id,
                        period_start=current,
                        period_end=current,
                        period_label=current.isoformat(),
                        target_amount=shop_daily_amounts[idx],
                        target_quantity=shop_daily_quantities[idx],
                    )
                )

    async def _add(self, obj) -> None:
        result = self.db.add(obj)
        if inspect.isawaitable(result):
            await result

    def _month_range(self, year_month: str) -> tuple[date, date]:
        year, month = [int(part) for part in year_month.split("-")]
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])

    def _validate_request(self, request: ShopTargetWorkbenchApplyRequest) -> None:
        ratio_total = sum(float(shop.ratio or 0.0) for shop in request.shops)
        amount_total = round(sum(float(shop.target_amount or 0.0) for shop in request.shops), 2)
        quantity_total = sum(int(shop.target_quantity or 0) for shop in request.shops)
        if abs(ratio_total - 1.0) > 0.0001:
            raise ValueError("店铺拆分比例合计必须等于100%")
        if abs(amount_total - round(float(request.company_target_amount or 0.0), 2)) > 0.01:
            raise ValueError("店铺目标销售额合计必须等于公司总销售额")
        if quantity_total != int(request.company_target_quantity or 0):
            raise ValueError("店铺订单目标合计必须等于公司订单目标")

    def _default_weekday_ratios(self) -> dict[str, float]:
        return {str(day): 1 / 7 for day in range(1, 8)}

    def _normalize_weekday_ratios(self, ratios: dict[str, float] | None) -> dict[str, float]:
        source = ratios or self._default_weekday_ratios()
        normalized = {str(day): max(float(source.get(str(day), 0.0) or 0.0), 0.0) for day in range(1, 8)}
        total = sum(normalized.values())
        if total <= 0:
            return self._default_weekday_ratios()
        return {key: value / total for key, value in normalized.items()}

    def _month_day_weights(
        self,
        month_start: date,
        days: int,
        weekday_ratios: dict[str, float] | None,
    ) -> list[tuple[date, float]]:
        ratios = self._normalize_weekday_ratios(weekday_ratios)
        weights = []
        for day in range(1, days + 1):
            current = date(month_start.year, month_start.month, day)
            weekday_key = str(current.weekday() + 1)
            weights.append((current, ratios.get(weekday_key, 0.0)))
        return weights

    def _split_amount_by_weights(
        self,
        total_amount: float,
        day_weights: list[tuple[date, float]],
        total_weight: float,
    ) -> list[float]:
        values = [round(float(total_amount or 0.0) * weight / total_weight, 2) for _, weight in day_weights]
        if values:
            values[-1] = round(values[-1] + round(float(total_amount or 0.0) - sum(values), 2), 2)
        return values

    def _split_quantity_by_weights(
        self,
        total_quantity: int,
        day_weights: list[tuple[date, float]],
        total_weight: float,
    ) -> list[int]:
        raw_values = [float(total_quantity or 0) * weight / total_weight for _, weight in day_weights]
        values = [int(value) for value in raw_values]
        remainder = int(total_quantity or 0) - sum(values)
        ranked = sorted(range(len(raw_values)), key=lambda idx: raw_values[idx] - values[idx], reverse=True)
        for idx in ranked[:remainder]:
            values[idx] += 1
        return values
