from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory import (
    InventoryAgingBucketResponse,
    InventoryAgingHistoryPointResponse,
    InventoryAgingRowResponse,
    InventoryAgingSummaryResponse,
)

BUCKET_ORDER = {
    "0-30": 0,
    "31-60": 1,
    "61-90": 2,
    "91-180": 3,
    "180+": 4,
}


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


def _bucket_sort_key(bucket: str) -> tuple[int, str]:
    return (BUCKET_ORDER.get(bucket, 999), bucket)


class InventoryAgingService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    async def list_aging_rows(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ) -> list[InventoryAgingRowResponse]:
        del shop_id
        if self.db is None:
            return []

        filters: list[str] = []
        params: dict[str, str] = {}
        if platform:
            filters.append("platform_code = :platform")
            params["platform"] = platform
        if platform_sku:
            filters.append(
                """
                (
                    sku_key = :platform_sku
                    OR platform_sku = :platform_sku
                    OR product_sku = :platform_sku
                )
                """
            )
            params["platform_sku"] = platform_sku

        where_clause = ""
        if filters:
            where_clause = "\nWHERE " + "\n  AND ".join(filters)

        result = await self.db.execute(
            text(
                f"""
                SELECT
                    snapshot_date,
                    platform_code,
                    sku_key,
                    platform_sku,
                    product_sku,
                    product_name,
                    current_qty,
                    previous_qty,
                    qty_delta,
                    age_anchor_date,
                    age_days,
                    bucket,
                    reset_reason,
                    inventory_value
                FROM api.inventory_age_list_module
                {where_clause}
                ORDER BY
                    age_days DESC,
                    inventory_value DESC,
                    platform_code ASC,
                    sku_key ASC
                """
            ),
            params,
        )

        rows = []
        for row in result.mappings().all():
            rows.append(
                InventoryAgingRowResponse(
                    snapshot_date=row["snapshot_date"],
                    platform_code=row["platform_code"],
                    sku_key=row["sku_key"],
                    platform_sku=row.get("platform_sku"),
                    product_sku=row.get("product_sku"),
                    product_name=row.get("product_name"),
                    current_qty=int(row.get("current_qty", 0) or 0),
                    previous_qty=(
                        int(row["previous_qty"])
                        if row.get("previous_qty") is not None
                        else None
                    ),
                    qty_delta=(
                        int(row["qty_delta"])
                        if row.get("qty_delta") is not None
                        else None
                    ),
                    age_anchor_date=row.get("age_anchor_date"),
                    age_days=int(row.get("age_days", 0) or 0),
                    reset_reason=row.get("reset_reason") or "continued",
                    inventory_value=float(row.get("inventory_value", 0.0) or 0.0),
                    bucket=row.get("bucket")
                    or bucket_age_days(int(row.get("age_days", 0) or 0)),
                )
            )
        return rows

    async def list_aging_history(
        self,
        platform: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ) -> list[InventoryAgingHistoryPointResponse]:
        if self.db is None:
            return []

        filters: list[str] = []
        params: dict[str, str] = {}
        if platform:
            filters.append("platform_code = :platform")
            params["platform"] = platform
        if platform_sku:
            filters.append(
                """
                (
                    sku_key = :platform_sku
                    OR platform_sku = :platform_sku
                    OR product_sku = :platform_sku
                )
                """
            )
            params["platform_sku"] = platform_sku

        where_clause = ""
        if filters:
            where_clause = "\nWHERE " + "\n  AND ".join(filters)

        result = await self.db.execute(
            text(
                f"""
                SELECT
                    snapshot_date,
                    platform_code,
                    sku_key,
                    platform_sku,
                    product_sku,
                    product_name,
                    current_qty,
                    previous_qty,
                    qty_delta,
                    age_anchor_date,
                    age_days,
                    bucket,
                    reset_reason,
                    inventory_value
                FROM mart.inventory_age_history
                {where_clause}
                ORDER BY snapshot_date ASC, sku_key ASC
                """
            ),
            params,
        )

        return [
            InventoryAgingHistoryPointResponse(
                snapshot_date=row["snapshot_date"],
                platform_code=row["platform_code"],
                sku_key=row["sku_key"],
                platform_sku=row.get("platform_sku"),
                product_sku=row.get("product_sku"),
                product_name=row.get("product_name"),
                current_qty=int(row.get("current_qty", 0) or 0),
                previous_qty=(
                    int(row["previous_qty"])
                    if row.get("previous_qty") is not None
                    else None
                ),
                qty_delta=(
                    int(row["qty_delta"])
                    if row.get("qty_delta") is not None
                    else None
                ),
                age_anchor_date=row.get("age_anchor_date"),
                age_days=(
                    int(row["age_days"]) if row.get("age_days") is not None else None
                ),
                reset_reason=row.get("reset_reason") or "continued",
                inventory_value=float(row.get("inventory_value", 0.0) or 0.0),
                bucket=row.get("bucket"),
            )
            for row in result.mappings().all()
        ]

    async def get_aging_summary(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ) -> InventoryAgingSummaryResponse:
        rows = await self.list_aging_rows(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
        )

        buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"quantity": 0, "inventory_value": 0.0, "sku_count": 0}
        )
        for row in rows:
            bucket = row.bucket or bucket_age_days(row.age_days)
            buckets[bucket]["quantity"] += int(row.current_qty or 0)
            buckets[bucket]["inventory_value"] += float(row.inventory_value or 0.0)
            buckets[bucket]["sku_count"] += 1

        bucket_rows = [
            InventoryAgingBucketResponse(
                bucket=bucket,
                quantity=int(data["quantity"]),
                inventory_value=float(data["inventory_value"]),
                sku_count=int(data["sku_count"]),
            )
            for bucket, data in sorted(
                buckets.items(),
                key=lambda item: _bucket_sort_key(item[0]),
            )
        ]

        return InventoryAgingSummaryResponse(
            rows=rows,
            buckets=bucket_rows,
            total_sku_count=len(rows),
            total_quantity=sum(int(row.current_qty or 0) for row in rows),
            total_value=sum(float(row.inventory_value or 0.0) for row in rows),
        )
