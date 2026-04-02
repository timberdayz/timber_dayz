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
from modules.core.db import MainAccount, ShopAccount


router = APIRouter(prefix="/shop-accounts", tags=["店铺账号管理"])


async def _get_shop_account_or_404(db: AsyncSession, shop_account_id: str) -> ShopAccount:
    result = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"店铺账号ID '{shop_account_id}' 不存在")
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
        raise HTTPException(status_code=400, detail=f"主账号ID '{main_account_id}' 不存在")


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
    return result.scalars().all()


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
        raise HTTPException(status_code=400, detail=f"店铺账号ID '{payload.shop_account_id}' 已存在")
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
    return record


@router.post("/batch", response_model=List[ShopAccountResponse])
async def batch_create_shop_accounts(
    payloads: List[ShopAccountCreate],
    db: AsyncSession = Depends(get_async_db),
):
    created: List[ShopAccount] = []
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
        created.append(record)
    await db.commit()
    for record in created:
        await db.refresh(record)
    return created


@router.put("/{shop_account_id}", response_model=ShopAccountResponse)
async def update_shop_account(
    shop_account_id: str,
    payload: ShopAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{shop_account_id}")
async def delete_shop_account(
    shop_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"店铺账号ID '{shop_account_id}' 已删除"}
