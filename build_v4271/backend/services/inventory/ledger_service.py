from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import InventoryLedger


class InventoryLedgerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_entries(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        movement_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 200,
    ) -> list[InventoryLedger]:
        stmt = select(InventoryLedger).order_by(
            InventoryLedger.transaction_date.desc(),
            InventoryLedger.ledger_id.desc(),
        )

        if platform:
            stmt = stmt.where(InventoryLedger.platform_code == platform)
        if shop_id:
            stmt = stmt.where(InventoryLedger.shop_id == shop_id)
        if platform_sku:
            stmt = stmt.where(InventoryLedger.platform_sku == platform_sku)
        if movement_type:
            stmt = stmt.where(InventoryLedger.movement_type == movement_type)
        if date_from:
            stmt = stmt.where(InventoryLedger.transaction_date >= date_from)
        if date_to:
            stmt = stmt.where(InventoryLedger.transaction_date <= date_to)

        stmt = stmt.limit(limit)
        return (await self.db.execute(stmt)).scalars().all()
