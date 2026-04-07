from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    InventoryAlertResponse,
    InventoryReconciliationResponse,
)
from backend.services.inventory.balance_service import InventoryBalanceService
from modules.core.db import FactProductMetric


def compute_snapshot_delta(internal_qty: int, external_qty: int) -> dict:
    delta_qty = int(internal_qty) - int(external_qty)
    return {
        "delta_qty": delta_qty,
        "status": "match" if delta_qty == 0 else "mismatch",
    }


def classify_inventory_alert(current_qty: int, safety_stock: int) -> str:
    if current_qty <= 0:
        return "out_of_stock"
    if current_qty < safety_stock:
        return "low_stock"
    return "healthy"


class InventoryReconciliationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.balance_service = InventoryBalanceService(db)

    async def list_alerts(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        safety_stock: int = 10,
    ) -> list[InventoryAlertResponse]:
        balances = await self.balance_service.list_balances(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
        )

        alerts: list[InventoryAlertResponse] = []
        for balance in balances:
            alert_type = classify_inventory_alert(
                current_qty=balance.current_qty,
                safety_stock=safety_stock,
            )
            if alert_type == "healthy":
                continue
            alerts.append(
                InventoryAlertResponse(
                    platform_code=balance.platform_code,
                    shop_id=balance.shop_id,
                    platform_sku=balance.platform_sku,
                    current_qty=balance.current_qty,
                    safety_stock=safety_stock,
                    alert_type=alert_type,
                    delta_qty=safety_stock - balance.current_qty,
                )
            )
        return alerts

    async def list_reconciliation(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ) -> list[InventoryReconciliationResponse]:
        balances = await self.balance_service.list_balances(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
        )

        snapshot_stmt = select(FactProductMetric).where(
            or_(
                FactProductMetric.data_domain == "inventory",
                FactProductMetric.data_domain.is_(None),
            )
        )
        if platform:
            snapshot_stmt = snapshot_stmt.where(FactProductMetric.platform_code == platform)
        if shop_id:
            snapshot_stmt = snapshot_stmt.where(FactProductMetric.shop_id == shop_id)
        if platform_sku:
            snapshot_stmt = snapshot_stmt.where(FactProductMetric.platform_sku == platform_sku)
        snapshot_stmt = snapshot_stmt.order_by(
            FactProductMetric.metric_date.desc(),
            FactProductMetric.platform_code.asc(),
            FactProductMetric.shop_id.asc(),
            FactProductMetric.platform_sku.asc(),
        )

        snapshot_rows = (await self.db.execute(snapshot_stmt)).scalars().all()
        snapshot_map: dict[tuple[str, str, str], int] = {}
        for row in snapshot_rows:
            key = (row.platform_code, row.shop_id, row.platform_sku)
            if key in snapshot_map:
                continue
            external_qty = (
                row.available_stock
                if row.available_stock is not None
                else (row.total_stock if row.total_stock is not None else (row.stock or 0))
            )
            snapshot_map[key] = int(external_qty or 0)

        reconciliation_rows: list[InventoryReconciliationResponse] = []
        for balance in balances:
            key = (balance.platform_code, balance.shop_id, balance.platform_sku)
            external_qty = snapshot_map.get(key, 0)
            delta = compute_snapshot_delta(
                internal_qty=balance.current_qty,
                external_qty=external_qty,
            )
            reconciliation_rows.append(
                InventoryReconciliationResponse(
                    platform_code=balance.platform_code,
                    shop_id=balance.shop_id,
                    platform_sku=balance.platform_sku,
                    internal_qty=balance.current_qty,
                    external_qty=external_qty,
                    delta_qty=delta["delta_qty"],
                    status=delta["status"],
                )
            )
        return reconciliation_rows
