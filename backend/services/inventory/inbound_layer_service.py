from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    GRNHeader,
    GRNLine,
    InventoryAdjustmentHeader,
    InventoryAdjustmentLine,
    InventoryLayer,
    OpeningBalance,
)


def build_layer_record(
    source_type: str,
    source_id: str,
    source_line_id: Optional[str],
    platform_code: str,
    shop_id: str,
    platform_sku: str,
    warehouse: Optional[str],
    received_date: date,
    qty: int,
    unit_cost: float,
    created_by: str,
) -> dict:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "source_line_id": source_line_id,
        "platform_code": platform_code,
        "shop_id": shop_id,
        "platform_sku": platform_sku,
        "warehouse": warehouse,
        "received_date": received_date,
        "original_qty": int(qty),
        "remaining_qty": int(qty),
        "unit_cost": float(unit_cost or 0.0),
        "base_unit_cost": float(unit_cost or 0.0),
        "created_by": created_by,
    }


class InventoryInboundLayerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _resolve_opening_received_date(self, record: OpeningBalance) -> date:
        if record.received_date:
            return record.received_date
        period_start = datetime.strptime(f"{record.period}-01", "%Y-%m-%d").date()
        if record.opening_age_days is not None:
            return period_start - timedelta(days=int(record.opening_age_days))
        return period_start

    async def upsert_opening_balance_layer(self, record: OpeningBalance) -> InventoryLayer:
        existing = (
            await self.db.execute(
                select(InventoryLayer).where(
                    InventoryLayer.source_type == "opening_balance",
                    InventoryLayer.source_id == str(record.balance_id),
                )
            )
        ).scalars().one_or_none()

        payload = build_layer_record(
            source_type="opening_balance",
            source_id=str(record.balance_id),
            source_line_id=None,
            platform_code=record.platform_code,
            shop_id=record.shop_id,
            platform_sku=record.platform_sku,
            warehouse=None,
            received_date=self._resolve_opening_received_date(record),
            qty=int(record.opening_qty or 0),
            unit_cost=float(record.opening_cost or 0.0),
            created_by=record.created_by or "system",
        )

        if existing is None:
            layer = InventoryLayer(**payload)
            self.db.add(layer)
        else:
            layer = existing
            for key, value in payload.items():
                setattr(layer, key, value)

        await self.db.flush()
        return layer

    async def create_grn_line_layer(
        self,
        header: GRNHeader,
        line: GRNLine,
        platform_code: str,
        shop_id: str,
        created_by: str,
    ) -> InventoryLayer:
        layer = InventoryLayer(
            **build_layer_record(
                source_type="grn",
                source_id=header.grn_id,
                source_line_id=str(line.grn_line_id),
                platform_code=platform_code,
                shop_id=shop_id,
                platform_sku=line.platform_sku,
                warehouse=header.warehouse,
                received_date=header.receipt_date,
                qty=int(line.qty_received or 0),
                unit_cost=float(line.unit_cost or 0.0),
                created_by=created_by,
            )
        )
        self.db.add(layer)
        await self.db.flush()
        return layer

    async def create_adjustment_in_layer(
        self,
        header: InventoryAdjustmentHeader,
        line: InventoryAdjustmentLine,
        created_by: str,
    ) -> Optional[InventoryLayer]:
        qty_delta = int(line.qty_delta or 0)
        if qty_delta <= 0:
            return None

        layer = InventoryLayer(
            **build_layer_record(
                source_type="adjustment_in",
                source_id=header.adjustment_id,
                source_line_id=str(line.adjustment_line_id),
                platform_code=line.platform_code,
                shop_id=line.shop_id,
                platform_sku=line.platform_sku,
                warehouse=None,
                received_date=header.adjustment_date,
                qty=qty_delta,
                unit_cost=float(line.unit_cost or 0.0),
                created_by=created_by,
            )
        )
        self.db.add(layer)
        await self.db.flush()
        return layer
