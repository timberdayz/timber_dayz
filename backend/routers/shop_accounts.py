from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.shop_account import (
    ShopAccountCreate,
    ShopAccountResponse,
    ShopAccountUpdate,
)
from backend.utils.text_normalization import normalize_alias_text
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


router = APIRouter(prefix="/shop-accounts", tags=["shop account management"])


def _default_capabilities_for(shop_type: str | None) -> dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
    }
    if shop_type == "global":
        defaults["services"] = False
    return defaults


async def _load_capabilities(
    db: AsyncSession,
    shop_account_db_id: int,
    shop_type: str | None,
) -> dict[str, bool]:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account_db_id
        )
    )
    rows = capability_result.scalars().all()
    if rows:
        return {
            row.data_domain: bool(row.enabled)
            for row in rows
        }
    return _default_capabilities_for(shop_type)


async def _ensure_capability_rows(
    db: AsyncSession,
    shop_account: ShopAccount,
    *,
    shop_type: str | None = None,
    capabilities: dict[str, bool] | None = None,
) -> None:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account.id
        )
    )
    existing = capability_result.scalars().all()
    existing_map = {
        row.data_domain: row
        for row in existing
    }
    target_capabilities = (
        capabilities
        if capabilities is not None
        else _default_capabilities_for(shop_type or shop_account.shop_type)
    )

    for domain, enabled in target_capabilities.items():
        capability_row = existing_map.get(domain)
        if capability_row is not None:
            capability_row.enabled = bool(enabled)
            continue
        db.add(
            ShopAccountCapability(
                shop_account_id=shop_account.id,
                data_domain=str(domain),
                enabled=bool(enabled),
            )
        )


async def _serialize_shop_account(
    db: AsyncSession,
    record: ShopAccount,
) -> ShopAccountResponse:
    alias_result = await db.execute(
        select(ShopAccountAlias).where(
            ShopAccountAlias.shop_account_id == record.id,
            ShopAccountAlias.is_active == True,
        )
    )
    aliases = alias_result.scalars().all()
    primary_alias = next((alias.alias_value for alias in aliases if alias.is_primary), None)
    if primary_alias is None:
        primary_alias = next((alias.alias_value for alias in aliases), None)
    capabilities = await _load_capabilities(db, record.id, record.shop_type)
    return ShopAccountResponse(
        id=record.id,
        platform=record.platform,
        shop_account_id=record.shop_account_id,
        main_account_id=record.main_account_id,
        account_alias=normalize_alias_text(primary_alias),
        alias_count=len(aliases),
        capabilities=capabilities,
        store_name=record.store_name,
        platform_shop_id=record.platform_shop_id,
        platform_shop_id_status=record.platform_shop_id_status,
        shop_region=record.shop_region,
        shop_type=record.shop_type,
        enabled=record.enabled,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _get_shop_account_or_404(db: AsyncSession, shop_account_id: str) -> ShopAccount:
    result = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"shop_account_id '{shop_account_id}' not found")
    return record


async def _assert_main_account_exists(
    db: AsyncSession, platform: str, main_account_id: str
) -> None:
    result = await db.execute(
        select(MainAccount).where(
            MainAccount.platform == platform,
            MainAccount.main_account_id == main_account_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail=f"main_account_id '{main_account_id}' not found")


@router.get("", response_model=List[ShopAccountResponse])
async def list_shop_accounts(
    platform: Optional[str] = Query(None),
    main_account_id: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ShopAccount).order_by(ShopAccount.platform, ShopAccount.shop_account_id)
    if platform:
        stmt = stmt.where(ShopAccount.platform == platform)
    if main_account_id:
        stmt = stmt.where(ShopAccount.main_account_id == main_account_id)
    if enabled is not None:
        stmt = stmt.where(ShopAccount.enabled == enabled)
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [await _serialize_shop_account(db, record) for record in records]


@router.post("", response_model=ShopAccountResponse)
async def create_shop_account(
    payload: ShopAccountCreate,
    db: AsyncSession = Depends(get_async_db),
):
    await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
    existing = await db.execute(
        select(ShopAccount).where(
            ShopAccount.platform == payload.platform,
            ShopAccount.shop_account_id == payload.shop_account_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"shop_account_id '{payload.shop_account_id}' already exists")

    record = ShopAccount(
        platform=payload.platform,
        shop_account_id=payload.shop_account_id,
        main_account_id=payload.main_account_id,
        store_name=payload.store_name,
        platform_shop_id=payload.platform_shop_id,
        platform_shop_id_status="manual_confirmed" if payload.platform_shop_id else "missing",
        shop_region=payload.shop_region,
        shop_type=payload.shop_type,
        enabled=payload.enabled,
        notes=payload.notes,
        created_by="system",
        updated_by="system",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await _ensure_capability_rows(
        db,
        record,
        shop_type=payload.shop_type,
        capabilities=payload.capabilities,
    )
    await db.commit()
    return await _serialize_shop_account(db, record)


@router.post("/batch", response_model=List[ShopAccountResponse])
async def batch_create_shop_accounts(
    payloads: List[ShopAccountCreate],
    db: AsyncSession = Depends(get_async_db),
):
    created: List[tuple[ShopAccount, ShopAccountCreate]] = []
    for payload in payloads:
        await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
        existing = await db.execute(
            select(ShopAccount).where(
                ShopAccount.platform == payload.platform,
                ShopAccount.shop_account_id == payload.shop_account_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        record = ShopAccount(
            platform=payload.platform,
            shop_account_id=payload.shop_account_id,
            main_account_id=payload.main_account_id,
            store_name=payload.store_name,
            platform_shop_id=payload.platform_shop_id,
            platform_shop_id_status="manual_confirmed" if payload.platform_shop_id else "missing",
            shop_region=payload.shop_region,
            shop_type=payload.shop_type,
            enabled=payload.enabled,
            notes=payload.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(record)
        created.append((record, payload))
    await db.commit()
    for record, payload in created:
        await db.refresh(record)
        await _ensure_capability_rows(
            db,
            record,
            shop_type=record.shop_type,
            capabilities=payload.capabilities,
        )
    await db.commit()
    return [await _serialize_shop_account(db, record) for record, _ in created]


@router.put("/{shop_account_id}", response_model=ShopAccountResponse)
async def update_shop_account(
    shop_account_id: str,
    payload: ShopAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    capabilities = update_data.pop("capabilities", None)
    for field, value in update_data.items():
        setattr(record, field, value)
    await _ensure_capability_rows(
        db,
        record,
        shop_type=update_data.get("shop_type", record.shop_type),
        capabilities=capabilities,
    )
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    await db.commit()
    await db.refresh(record)
    return await _serialize_shop_account(db, record)


@router.delete("/{shop_account_id}")
async def delete_shop_account(
    shop_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"shop_account_id '{shop_account_id}' deleted"}
