from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    InventoryBalanceDetailResponse,
    InventoryBalanceSummaryResponse,
)
from modules.core.db import InventoryLedger, OpeningBalance


def compute_balance_summary(opening_qty: int, ledger_rows: Iterable[dict]) -> dict:
    qty_in = sum(int(row.get("qty_in", 0) or 0) for row in ledger_rows)
    qty_out = sum(int(row.get("qty_out", 0) or 0) for row in ledger_rows)
    return {
        "opening_qty": int(opening_qty or 0),
        "qty_in": qty_in,
        "qty_out": qty_out,
        "current_qty": int(opening_qty or 0) + qty_in - qty_out,
    }


class InventoryBalanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_balances(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ) -> list[InventoryBalanceSummaryResponse]:
        ledger_stmt = (
            select(
                InventoryLedger.platform_code,
                InventoryLedger.shop_id,
                InventoryLedger.platform_sku,
                func.coalesce(func.sum(InventoryLedger.qty_in), 0).label("qty_in"),
                func.coalesce(func.sum(InventoryLedger.qty_out), 0).label("qty_out"),
            )
            .group_by(
                InventoryLedger.platform_code,
                InventoryLedger.shop_id,
                InventoryLedger.platform_sku,
            )
            .order_by(
                InventoryLedger.platform_code,
                InventoryLedger.shop_id,
                InventoryLedger.platform_sku,
            )
        )

        opening_stmt = (
            select(
                OpeningBalance.platform_code,
                OpeningBalance.shop_id,
                OpeningBalance.platform_sku,
                OpeningBalance.opening_qty,
            )
            .order_by(
                OpeningBalance.platform_code,
                OpeningBalance.shop_id,
                OpeningBalance.platform_sku,
                OpeningBalance.period.desc(),
            )
        )

        if platform:
            ledger_stmt = ledger_stmt.where(InventoryLedger.platform_code == platform)
            opening_stmt = opening_stmt.where(OpeningBalance.platform_code == platform)
        if shop_id:
            ledger_stmt = ledger_stmt.where(InventoryLedger.shop_id == shop_id)
            opening_stmt = opening_stmt.where(OpeningBalance.shop_id == shop_id)
        if platform_sku:
            ledger_stmt = ledger_stmt.where(InventoryLedger.platform_sku == platform_sku)
            opening_stmt = opening_stmt.where(OpeningBalance.platform_sku == platform_sku)

        ledger_rows = (await self.db.execute(ledger_stmt)).all()
        opening_rows = (await self.db.execute(opening_stmt)).all()

        opening_map: Dict[Tuple[str, str, str], int] = {}
        for row in opening_rows:
            key = (row.platform_code, row.shop_id, row.platform_sku)
            if key not in opening_map:
                opening_map[key] = int(row.opening_qty or 0)

        summaries: list[InventoryBalanceSummaryResponse] = []
        seen_keys: set[Tuple[str, str, str]] = set()

        for row in ledger_rows:
            key = (row.platform_code, row.shop_id, row.platform_sku)
            seen_keys.add(key)
            summary = compute_balance_summary(
                opening_qty=opening_map.get(key, 0),
                ledger_rows=[{"qty_in": row.qty_in, "qty_out": row.qty_out}],
            )
            summaries.append(
                InventoryBalanceSummaryResponse(
                    platform_code=row.platform_code,
                    shop_id=row.shop_id,
                    platform_sku=row.platform_sku,
                    **summary,
                )
            )

        for key, opening_qty in opening_map.items():
            if key in seen_keys:
                continue
            summaries.append(
                InventoryBalanceSummaryResponse(
                    platform_code=key[0],
                    shop_id=key[1],
                    platform_sku=key[2],
                    opening_qty=opening_qty,
                    qty_in=0,
                    qty_out=0,
                    current_qty=opening_qty,
                )
            )

        return summaries

    async def get_balance_detail(
        self,
        platform: str,
        shop_id: str,
        platform_sku: str,
    ) -> InventoryBalanceDetailResponse:
        opening_stmt = (
            select(OpeningBalance)
            .where(
                OpeningBalance.platform_code == platform,
                OpeningBalance.shop_id == shop_id,
                OpeningBalance.platform_sku == platform_sku,
            )
            .order_by(OpeningBalance.period.desc())
        )
        opening_row = (await self.db.execute(opening_stmt)).scalars().first()

        ledger_stmt = (
            select(InventoryLedger)
            .where(
                InventoryLedger.platform_code == platform,
                InventoryLedger.shop_id == shop_id,
                InventoryLedger.platform_sku == platform_sku,
            )
            .order_by(InventoryLedger.transaction_date.asc(), InventoryLedger.ledger_id.asc())
        )
        ledger_rows = (await self.db.execute(ledger_stmt)).scalars().all()

        summary = compute_balance_summary(
            opening_qty=int(opening_row.opening_qty if opening_row else 0),
            ledger_rows=[
                {"qty_in": row.qty_in, "qty_out": row.qty_out}
                for row in ledger_rows
            ],
        )

        average_cost = (
            float(ledger_rows[-1].avg_cost_after)
            if ledger_rows
            else float(opening_row.opening_cost if opening_row else 0.0)
        )

        return InventoryBalanceDetailResponse(
            platform_code=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
            opening_qty=summary["opening_qty"],
            qty_in=summary["qty_in"],
            qty_out=summary["qty_out"],
            current_qty=summary["current_qty"],
            opening_cost=float(opening_row.opening_cost if opening_row else 0.0),
            average_cost=average_cost,
            current_value=summary["current_qty"] * average_cost,
        )
