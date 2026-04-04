from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    InventoryAgingBucketResponse,
    InventoryAgingRowResponse,
    InventoryAgingSummaryResponse,
)
from modules.core.db import InventoryLayer


def bucket_age_days(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    if age_days <= 180:
        return "91-180"
    return "180+"


def compute_weighted_avg_age_days(rows: Iterable[dict]) -> float:
    total_qty = 0
    weighted_total = 0.0
    for row in rows:
        qty = int(row.get("remaining_qty", 0) or 0)
        age_days = float(row.get("age_days", 0) or 0)
        total_qty += qty
        weighted_total += qty * age_days
    if total_qty == 0:
        return 0.0
    return weighted_total / total_qty


class InventoryAgingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_open_layers(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        as_of_date: Optional[date] = None,
    ) -> list[dict]:
        if as_of_date is None:
            as_of_date = date.today()

        stmt = select(InventoryLayer).where(InventoryLayer.remaining_qty > 0)
        if platform:
            stmt = stmt.where(InventoryLayer.platform_code == platform)
        if shop_id:
            stmt = stmt.where(InventoryLayer.shop_id == shop_id)
        if platform_sku:
            stmt = stmt.where(InventoryLayer.platform_sku == platform_sku)
        stmt = stmt.order_by(
            InventoryLayer.platform_code.asc(),
            InventoryLayer.shop_id.asc(),
            InventoryLayer.platform_sku.asc(),
            InventoryLayer.received_date.asc(),
            InventoryLayer.layer_id.asc(),
        )

        layers = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "layer_id": layer.layer_id,
                "platform_code": layer.platform_code,
                "shop_id": layer.shop_id,
                "platform_sku": layer.platform_sku,
                "remaining_qty": int(layer.remaining_qty or 0),
                "remaining_value": float((layer.remaining_qty or 0) * (layer.base_unit_cost or layer.unit_cost or 0.0)),
                "age_days": max((as_of_date - layer.received_date).days, 0),
            }
            for layer in layers
        ]

    async def list_aging_rows(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        as_of_date: Optional[date] = None,
    ) -> list[InventoryAgingRowResponse]:
        rows = await self._load_open_layers(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
            as_of_date=as_of_date,
        )
        grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for row in rows:
            key = (row["platform_code"], row["shop_id"], row["platform_sku"])
            grouped[key].append(row)

        results: list[InventoryAgingRowResponse] = []
        for key, group_rows in grouped.items():
            results.append(
                InventoryAgingRowResponse(
                    platform_code=key[0],
                    shop_id=key[1],
                    platform_sku=key[2],
                    remaining_qty=sum(int(item["remaining_qty"]) for item in group_rows),
                    oldest_age_days=max(int(item["age_days"]) for item in group_rows),
                    youngest_age_days=min(int(item["age_days"]) for item in group_rows),
                    weighted_avg_age_days=compute_weighted_avg_age_days(group_rows),
                    remaining_value=sum(float(item["remaining_value"]) for item in group_rows),
                )
            )
        return results

    async def get_aging_summary(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
        as_of_date: Optional[date] = None,
    ) -> InventoryAgingSummaryResponse:
        open_rows = await self._load_open_layers(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
            as_of_date=as_of_date,
        )
        aging_rows = await self.list_aging_rows(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
            as_of_date=as_of_date,
        )

        buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"quantity": 0, "inventory_value": 0.0, "sku_keys": set()}
        )
        for row in open_rows:
            bucket = bucket_age_days(int(row["age_days"]))
            buckets[bucket]["quantity"] += int(row["remaining_qty"])
            buckets[bucket]["inventory_value"] += float(row["remaining_value"])
            buckets[bucket]["sku_keys"].add(
                (row["platform_code"], row["shop_id"], row["platform_sku"])
            )

        bucket_rows = [
            InventoryAgingBucketResponse(
                bucket=bucket,
                quantity=int(data["quantity"]),
                inventory_value=float(data["inventory_value"]),
                sku_count=len(data["sku_keys"]),
            )
            for bucket, data in sorted(buckets.items())
        ]

        return InventoryAgingSummaryResponse(
            rows=aging_rows,
            buckets=bucket_rows,
            total_quantity=sum(row.remaining_qty for row in aging_rows),
            total_value=sum(row.remaining_value for row in aging_rows),
        )
