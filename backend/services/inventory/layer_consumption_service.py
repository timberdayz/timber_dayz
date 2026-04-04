from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import InventoryLayer, InventoryLayerConsumption


def consume_layers_fifo(layers: Iterable[dict], requested_qty: int) -> list[dict]:
    remaining = int(requested_qty)
    consumptions: list[dict] = []

    for layer in layers:
        if remaining <= 0:
            break
        layer_remaining = int(layer.get("remaining_qty", 0) or 0)
        if layer_remaining <= 0:
            continue
        consumed_qty = min(layer_remaining, remaining)
        consumptions.append(
            {
                "layer_id": layer["layer_id"],
                "consumed_qty": consumed_qty,
                "age_days": int(layer.get("age_days", 0) or 0),
            }
        )
        remaining -= consumed_qty

    if remaining > 0:
        raise ValueError("Not enough remaining layer quantity for FIFO consumption")

    return consumptions


class InventoryLayerConsumptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def consume_for_outbound_ledger(
        self,
        outbound_ledger_id: int,
        platform_code: str,
        shop_id: str,
        platform_sku: str,
        requested_qty: int,
        consumed_at: datetime | None = None,
    ) -> list[InventoryLayerConsumption]:
        if requested_qty <= 0:
            return []

        layers = (
            await self.db.execute(
                select(InventoryLayer)
                .where(
                    InventoryLayer.platform_code == platform_code,
                    InventoryLayer.shop_id == shop_id,
                    InventoryLayer.platform_sku == platform_sku,
                    InventoryLayer.remaining_qty > 0,
                )
                .order_by(
                    InventoryLayer.received_date.asc(),
                    InventoryLayer.layer_id.asc(),
                )
            )
        ).scalars().all()

        if consumed_at is None:
            consumed_at = datetime.now(timezone.utc)

        layer_payloads = []
        for layer in layers:
            age_days = max((consumed_at.date() - layer.received_date).days, 0)
            layer_payloads.append(
                {
                    "layer_id": layer.layer_id,
                    "remaining_qty": layer.remaining_qty,
                    "age_days": age_days,
                }
            )

        consumptions = consume_layers_fifo(
            layers=layer_payloads,
            requested_qty=requested_qty,
        )

        layer_by_id = {layer.layer_id: layer for layer in layers}
        created_rows: list[InventoryLayerConsumption] = []
        for item in consumptions:
            layer = layer_by_id[item["layer_id"]]
            layer.remaining_qty = int(layer.remaining_qty) - int(item["consumed_qty"])

            row = InventoryLayerConsumption(
                outbound_ledger_id=outbound_ledger_id,
                layer_id=layer.layer_id,
                platform_code=platform_code,
                shop_id=shop_id,
                platform_sku=platform_sku,
                consumed_qty=int(item["consumed_qty"]),
                consumed_at=consumed_at,
                age_days_at_consumption=int(item["age_days"]),
            )
            self.db.add(row)
            created_rows.append(row)

        await self.db.flush()
        return created_rows
