from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    InventoryOpeningBalanceCreateRequest,
    InventoryOpeningBalanceResponse,
)
from backend.services.inventory.inbound_layer_service import InventoryInboundLayerService
from modules.core.db import OpeningBalance


class InventoryOpeningBalanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_opening_balances(
        self,
        period: Optional[str] = None,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        limit: int = 200,
    ) -> list[OpeningBalance]:
        stmt = select(OpeningBalance).order_by(
            OpeningBalance.period.desc(),
            OpeningBalance.platform_code.asc(),
            OpeningBalance.shop_id.asc(),
            OpeningBalance.platform_sku.asc(),
        )
        if period:
            stmt = stmt.where(OpeningBalance.period == period)
        if platform:
            stmt = stmt.where(OpeningBalance.platform_code == platform)
        if shop_id:
            stmt = stmt.where(OpeningBalance.shop_id == shop_id)
        if platform_sku:
            stmt = stmt.where(OpeningBalance.platform_sku == platform_sku)
        stmt = stmt.limit(limit)
        return (await self.db.execute(stmt)).scalars().all()

    async def create_opening_balance(
        self,
        payload: InventoryOpeningBalanceCreateRequest,
        created_by: str = "system",
    ) -> InventoryOpeningBalanceResponse:
        existing = (
            await self.db.execute(
                select(OpeningBalance).where(
                    OpeningBalance.period == payload.period,
                    OpeningBalance.platform_code == payload.platform_code,
                    OpeningBalance.shop_id == payload.shop_id,
                    OpeningBalance.platform_sku == payload.platform_sku,
                )
            )
        ).scalars().one_or_none()

        opening_value = (
            payload.opening_value
            if payload.opening_value is not None
            else payload.opening_qty * payload.opening_cost
        )

        if existing:
            existing.received_date = payload.received_date
            existing.opening_age_days = payload.opening_age_days
            existing.opening_qty = payload.opening_qty
            existing.opening_cost = payload.opening_cost
            existing.opening_value = opening_value
            existing.source = payload.source
            existing.migration_batch_id = payload.migration_batch_id
            await self.db.flush()
            await InventoryInboundLayerService(self.db).upsert_opening_balance_layer(existing)
            await self.db.commit()
            await self.db.refresh(existing)
            return InventoryOpeningBalanceResponse.model_validate(existing)

        record = OpeningBalance(
            period=payload.period,
            platform_code=payload.platform_code,
            shop_id=payload.shop_id,
            platform_sku=payload.platform_sku,
            received_date=payload.received_date,
            opening_age_days=payload.opening_age_days,
            opening_qty=payload.opening_qty,
            opening_cost=payload.opening_cost,
            opening_value=opening_value,
            source=payload.source,
            migration_batch_id=payload.migration_batch_id,
            created_by=created_by,
        )
        self.db.add(record)
        await self.db.flush()
        await InventoryInboundLayerService(self.db).upsert_opening_balance_layer(record)
        await self.db.commit()
        await self.db.refresh(record)
        return InventoryOpeningBalanceResponse.model_validate(record)
