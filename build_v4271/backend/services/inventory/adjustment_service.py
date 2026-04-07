from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.inventory.inbound_layer_service import InventoryInboundLayerService
from backend.services.inventory.layer_consumption_service import (
    InventoryLayerConsumptionService,
)
from backend.schemas.inventory import (
    InventoryAdjustmentCreateRequest,
    InventoryAdjustmentResponse,
)
from modules.core.db import (
    InventoryAdjustmentHeader,
    InventoryAdjustmentLine,
    InventoryLedger,
    OpeningBalance,
)


def build_adjustment_ledger_entry(
    platform_code: str,
    shop_id: str,
    platform_sku: str,
    qty_before: int,
    avg_cost_before: float,
    qty_delta: int,
    unit_cost: float,
    adjustment_id: str,
) -> dict:
    qty_in = max(qty_delta, 0)
    qty_out = abs(min(qty_delta, 0))
    qty_after = qty_before + qty_delta

    if qty_delta > 0 and qty_after > 0:
        avg_cost_after = (
            (qty_before * avg_cost_before) + (qty_delta * unit_cost)
        ) / qty_after
    else:
        avg_cost_after = avg_cost_before

    ext_value = qty_in * unit_cost
    return {
        "platform_code": platform_code,
        "shop_id": shop_id,
        "platform_sku": platform_sku,
        "movement_type": "adjustment",
        "qty_in": qty_in,
        "qty_out": qty_out,
        "qty_before": qty_before,
        "qty_after": qty_after,
        "avg_cost_before": float(avg_cost_before),
        "avg_cost_after": float(avg_cost_after),
        "unit_cost_wac": float(avg_cost_after if qty_delta > 0 else avg_cost_before),
        "ext_value": float(ext_value),
        "base_ext_value": float(ext_value),
        "link_adjustment_id": adjustment_id,
    }


class InventoryAdjustmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_adjustments(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[InventoryAdjustmentHeader]:
        stmt = select(InventoryAdjustmentHeader).order_by(
            InventoryAdjustmentHeader.adjustment_date.desc(),
            InventoryAdjustmentHeader.adjustment_id.desc(),
        )
        if status:
            stmt = stmt.where(InventoryAdjustmentHeader.status == status)
        stmt = stmt.limit(limit)
        return (await self.db.execute(stmt)).scalars().all()

    async def create_adjustment(
        self,
        payload: InventoryAdjustmentCreateRequest,
        created_by: str = "system",
    ) -> InventoryAdjustmentResponse:
        adjustment_id = f"ADJ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        header = InventoryAdjustmentHeader(
            adjustment_id=adjustment_id,
            adjustment_date=payload.adjustment_date,
            reason=payload.reason,
            notes=payload.notes,
            created_by=created_by,
            status="draft",
        )
        self.db.add(header)
        await self.db.flush()

        lines: list[InventoryAdjustmentLine] = []
        for line in payload.lines:
            line_model = InventoryAdjustmentLine(
                adjustment_id=adjustment_id,
                platform_code=line.platform_code,
                shop_id=line.shop_id,
                platform_sku=line.platform_sku,
                qty_delta=line.qty_delta,
                unit_cost=line.unit_cost,
                notes=line.notes,
            )
            self.db.add(line_model)
            lines.append(line_model)

        await self.db.commit()
        await self.db.refresh(header)
        for line in lines:
            await self.db.refresh(line)

        return InventoryAdjustmentResponse(
            adjustment_id=header.adjustment_id,
            adjustment_date=header.adjustment_date,
            status=header.status,
            reason=header.reason,
            notes=header.notes,
            created_by=header.created_by,
            created_at=header.created_at,
            updated_at=header.updated_at,
            lines=lines,
        )

    async def post_adjustment(
        self,
        adjustment_id: str,
        created_by: str = "system",
    ) -> InventoryAdjustmentResponse:
        header = (
            await self.db.execute(
                select(InventoryAdjustmentHeader).where(
                    InventoryAdjustmentHeader.adjustment_id == adjustment_id
                )
            )
        ).scalars().one_or_none()
        if not header:
            raise ValueError(f"Adjustment not found: {adjustment_id}")
        if header.status == "posted":
            raise ValueError(f"Adjustment already posted: {adjustment_id}")

        lines = (
            await self.db.execute(
                select(InventoryAdjustmentLine)
                .where(InventoryAdjustmentLine.adjustment_id == adjustment_id)
                .order_by(InventoryAdjustmentLine.adjustment_line_id.asc())
            )
        ).scalars().all()
        if not lines:
            raise ValueError(f"Adjustment has no lines: {adjustment_id}")

        for line in lines:
            latest_ledger = (
                await self.db.execute(
                    select(InventoryLedger)
                    .where(
                        InventoryLedger.platform_code == line.platform_code,
                        InventoryLedger.shop_id == line.shop_id,
                        InventoryLedger.platform_sku == line.platform_sku,
                    )
                    .order_by(
                        InventoryLedger.transaction_date.desc(),
                        InventoryLedger.ledger_id.desc(),
                    )
                )
            ).scalars().first()

            opening_balance = None
            if latest_ledger is None:
                opening_balance = (
                    await self.db.execute(
                        select(OpeningBalance)
                        .where(
                            OpeningBalance.platform_code == line.platform_code,
                            OpeningBalance.shop_id == line.shop_id,
                            OpeningBalance.platform_sku == line.platform_sku,
                        )
                        .order_by(OpeningBalance.period.desc())
                    )
                ).scalars().first()

            qty_before = int(latest_ledger.qty_after if latest_ledger else (opening_balance.opening_qty if opening_balance else 0))
            avg_cost_before = float(
                latest_ledger.avg_cost_after
                if latest_ledger
                else (opening_balance.opening_cost if opening_balance else 0.0)
            )

            unit_cost = float(
                line.unit_cost
                if line.unit_cost is not None
                else avg_cost_before
            )
            entry = build_adjustment_ledger_entry(
                platform_code=line.platform_code,
                shop_id=line.shop_id,
                platform_sku=line.platform_sku,
                qty_before=qty_before,
                avg_cost_before=avg_cost_before,
                qty_delta=int(line.qty_delta),
                unit_cost=unit_cost,
                adjustment_id=adjustment_id,
            )

            ledger = InventoryLedger(
                platform_code=entry["platform_code"],
                shop_id=entry["shop_id"],
                platform_sku=entry["platform_sku"],
                transaction_date=header.adjustment_date,
                movement_type=entry["movement_type"],
                qty_in=entry["qty_in"],
                qty_out=entry["qty_out"],
                unit_cost_wac=entry["unit_cost_wac"],
                ext_value=entry["ext_value"],
                base_ext_value=entry["base_ext_value"],
                qty_before=entry["qty_before"],
                avg_cost_before=entry["avg_cost_before"],
                qty_after=entry["qty_after"],
                avg_cost_after=entry["avg_cost_after"],
                created_by=created_by,
            )
            self.db.add(ledger)
            await self.db.flush()
            if int(line.qty_delta or 0) > 0:
                await InventoryInboundLayerService(self.db).create_adjustment_in_layer(
                    header=header,
                    line=line,
                    created_by=created_by,
                )
            elif int(line.qty_delta or 0) < 0:
                await InventoryLayerConsumptionService(self.db).consume_for_outbound_ledger(
                    outbound_ledger_id=ledger.ledger_id,
                    platform_code=line.platform_code,
                    shop_id=line.shop_id,
                    platform_sku=line.platform_sku,
                    requested_qty=abs(int(line.qty_delta or 0)),
                    consumed_at=datetime.combine(
                        header.adjustment_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                )

        header.status = "posted"
        await self.db.commit()
        await self.db.refresh(header)

        return InventoryAdjustmentResponse(
            adjustment_id=header.adjustment_id,
            adjustment_date=header.adjustment_date,
            status=header.status,
            reason=header.reason,
            notes=header.notes,
            created_by=header.created_by,
            created_at=header.created_at,
            updated_at=header.updated_at,
            lines=lines,
        )
