from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.inventory.inbound_layer_service import InventoryInboundLayerService
from backend.schemas.inventory import InventoryGrnPostResponse
from modules.core.db import GRNHeader, GRNLine, InventoryLedger, OpeningBalance


def build_receipt_ledger_entry(
    platform_code: str,
    shop_id: str,
    platform_sku: str,
    qty_before: int,
    avg_cost_before: float,
    qty_received: int,
    unit_cost: float,
    grn_id: str,
) -> dict:
    qty_after = qty_before + qty_received
    if qty_after <= 0:
        avg_cost_after = 0.0
    elif qty_before <= 0:
        avg_cost_after = float(unit_cost)
    else:
        avg_cost_after = (
            (qty_before * avg_cost_before) + (qty_received * unit_cost)
        ) / qty_after

    ext_value = qty_received * unit_cost
    return {
        "platform_code": platform_code,
        "shop_id": shop_id,
        "platform_sku": platform_sku,
        "movement_type": "receipt",
        "qty_in": qty_received,
        "qty_out": 0,
        "qty_before": qty_before,
        "qty_after": qty_after,
        "avg_cost_before": float(avg_cost_before),
        "avg_cost_after": float(avg_cost_after),
        "unit_cost_wac": float(avg_cost_after),
        "ext_value": float(ext_value),
        "base_ext_value": float(ext_value),
        "link_grn_id": grn_id,
    }


class InventoryGrnService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_grns(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[GRNHeader]:
        stmt = select(GRNHeader).order_by(GRNHeader.receipt_date.desc(), GRNHeader.grn_id.desc())
        if status:
            stmt = stmt.where(GRNHeader.status == status)
        stmt = stmt.limit(limit)
        return (await self.db.execute(stmt)).scalars().all()

    async def post_grn(
        self,
        grn_id: str,
        platform_code: str,
        shop_id: str,
        created_by: str = "system",
    ) -> InventoryGrnPostResponse:
        header = (
            await self.db.execute(
                select(GRNHeader).where(GRNHeader.grn_id == grn_id)
            )
        ).scalars().one_or_none()
        if not header:
            raise ValueError(f"GRN not found: {grn_id}")
        if header.status == "completed":
            raise ValueError(f"GRN already posted: {grn_id}")

        existing_ledger = (
            await self.db.execute(
                select(InventoryLedger.ledger_id).where(InventoryLedger.link_grn_id == grn_id)
            )
        ).first()
        if existing_ledger:
            raise ValueError(f"GRN already linked in ledger: {grn_id}")

        lines = (
            await self.db.execute(
                select(GRNLine).where(GRNLine.grn_id == grn_id).order_by(GRNLine.grn_line_id.asc())
            )
        ).scalars().all()
        if not lines:
            raise ValueError(f"GRN has no lines: {grn_id}")

        created = 0
        for line in lines:
            latest_ledger = (
                await self.db.execute(
                    select(InventoryLedger)
                    .where(
                        InventoryLedger.platform_code == platform_code,
                        InventoryLedger.shop_id == shop_id,
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
                            OpeningBalance.platform_code == platform_code,
                            OpeningBalance.shop_id == shop_id,
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

            entry = build_receipt_ledger_entry(
                platform_code=platform_code,
                shop_id=shop_id,
                platform_sku=line.platform_sku,
                qty_before=qty_before,
                avg_cost_before=avg_cost_before,
                qty_received=int(line.qty_received or 0),
                unit_cost=float(line.unit_cost or 0.0),
                grn_id=grn_id,
            )

            self.db.add(
                InventoryLedger(
                    platform_code=entry["platform_code"],
                    shop_id=entry["shop_id"],
                    platform_sku=entry["platform_sku"],
                    transaction_date=header.receipt_date,
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
                    link_grn_id=entry["link_grn_id"],
                    created_by=created_by,
                )
            )
            await InventoryInboundLayerService(self.db).create_grn_line_layer(
                header=header,
                line=line,
                platform_code=platform_code,
                shop_id=shop_id,
                created_by=created_by,
            )
            created += 1

        header.status = "completed"
        await self.db.commit()

        return InventoryGrnPostResponse(
            grn_id=grn_id,
            status=header.status,
            posted_entries=created,
        )
