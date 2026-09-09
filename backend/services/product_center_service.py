from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import BridgeErpSkuKey, DimErpSku


def advance_inventory_age(
    *,
    snapshot_date: date,
    current_qty: int,
    previous_qty: int | None,
    previous_anchor_date: date | None,
) -> dict[str, object]:
    """Advance snapshot-derived backlog age without claiming physical stock age."""
    if current_qty <= 0:
        return {"age_anchor_date": snapshot_date, "age_days": 0, "reset_reason": "out_of_stock"}
    if previous_qty is None or previous_anchor_date is None:
        return {"age_anchor_date": snapshot_date, "age_days": 0, "reset_reason": "first_snapshot"}
    if current_qty > previous_qty:
        return {"age_anchor_date": snapshot_date, "age_days": 0, "reset_reason": "restocked"}
    return {
        "age_anchor_date": previous_anchor_date,
        "age_days": max((snapshot_date - previous_anchor_date).days, 0),
        "reset_reason": "no_restock",
    }


def canonical_sku_key(row: dict) -> str | None:
    for key in ("platform_sku", "product_sku", "sku_id", "product_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


async def sync_inventory_skus(
    db: AsyncSession,
    *,
    source_file_id: int | None = None,
) -> int:
    """Upsert canonical SKU identities from the normalized inventory layer."""
    result = await db.execute(
        text(
            """
            SELECT DISTINCT ON (platform_code, sku_key)
                platform_code, sku_key, product_name, sku_id, product_sku, product_id
            FROM mart.inventory_snapshot_company_daily
            WHERE sku_key IS NOT NULL
            ORDER BY platform_code, sku_key, last_ingest_timestamp DESC
            """
        )
    )
    rows = result.mappings().all()
    synced = 0
    today = date.today()
    now = datetime.now(timezone.utc)
    for row in rows:
        sku_key = str(row["sku_key"])
        existing = (
            await db.execute(select(DimErpSku).where(DimErpSku.sku_key == sku_key))
        ).scalar_one_or_none()
        if existing is None:
            existing = DimErpSku(
                sku_key=sku_key,
                sku_name=row.get("product_name"),
                erp_record_id=row.get("product_id") or row.get("sku_id"),
                source_file_id=source_file_id,
                last_seen_at=now,
            )
            db.add(existing)
            await db.flush()
        else:
            if row.get("product_name"):
                existing.sku_name = row["product_name"]
            if source_file_id is not None:
                existing.source_file_id = source_file_id
            existing.last_seen_at = now

        aliases = [("platform_sku", row.get("platform_sku")), ("product_sku", row.get("product_sku")), ("sku_id", row.get("sku_id")), ("product_id", row.get("product_id"))]
        for key_type, source_key in aliases:
            if source_key in (None, ""):
                continue
            alias = (
                await db.execute(
                    select(BridgeErpSkuKey).where(
                        BridgeErpSkuKey.source_system == "miaoshou",
                        BridgeErpSkuKey.source_platform == row.get("platform_code"),
                        BridgeErpSkuKey.source_key_type == key_type,
                        BridgeErpSkuKey.source_key == str(source_key),
                        BridgeErpSkuKey.effective_to.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if alias is None:
                db.add(
                    BridgeErpSkuKey(
                        source_system="miaoshou",
                        source_platform=row.get("platform_code"),
                        source_key_type=key_type,
                        source_key=str(source_key),
                        sku_id=existing.sku_id,
                        effective_from=today,
                        source_file_id=source_file_id,
                    )
                )
        synced += 1
    await db.commit()
    return synced
