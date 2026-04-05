from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.main_account import (
    MainAccountCreate,
    MainAccountResponse,
    MainAccountUpdate,
)
from backend.schemas.shop_discovery import (
    ShopDiscoveryRunRequest,
    ShopDiscoveryRunResponse,
)
from backend.services.encryption_service import get_encryption_service
from backend.services.platform_login_entry_service import normalize_main_account_login_url
from backend.services.shop_discovery_service import get_shop_discovery_service
from backend.utils.text_normalization import coalesce_human_text, normalize_human_text
from modules.core.db import MainAccount


router = APIRouter(prefix="/main-accounts", tags=["main account management"])


async def _get_main_account_or_404(db: AsyncSession, main_account_id: str) -> MainAccount:
    result = await db.execute(
        select(MainAccount).where(MainAccount.main_account_id == main_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"main_account_id '{main_account_id}' not found")
    return record


def _serialize_main_account(record: MainAccount) -> MainAccountResponse:
    return MainAccountResponse(
        id=record.id,
        platform=record.platform,
        main_account_id=record.main_account_id,
        main_account_name=coalesce_human_text(
            record.main_account_name,
            record.notes,
            record.username,
            record.main_account_id,
        ),
        username=record.username,
        login_url=record.login_url,
        enabled=record.enabled,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=List[MainAccountResponse])
async def list_main_accounts(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(MainAccount).order_by(MainAccount.platform, MainAccount.main_account_id)
    )
    return [_serialize_main_account(record) for record in result.scalars().all()]


@router.post("", response_model=MainAccountResponse)
async def create_main_account(
    payload: MainAccountCreate,
    db: AsyncSession = Depends(get_async_db),
):
    existing = await db.execute(
        select(MainAccount).where(
            MainAccount.platform == payload.platform,
            MainAccount.main_account_id == payload.main_account_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail=f"main_account_id '{payload.main_account_id}' already exists",
        )

    encryption_service = get_encryption_service()
    record = MainAccount(
        platform=payload.platform,
        main_account_id=payload.main_account_id,
        main_account_name=normalize_human_text(payload.main_account_name),
        username=payload.username,
        password_encrypted=encryption_service.encrypt_password(payload.password),
        login_url=normalize_main_account_login_url(payload.platform, payload.login_url),
        enabled=payload.enabled,
        notes=payload.notes,
        created_by="system",
        updated_by="system",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_main_account(record)


@router.put("/{main_account_id}", response_model=MainAccountResponse)
async def update_main_account(
    main_account_id: str,
    payload: MainAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_main_account_or_404(db, main_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    password = update_data.pop("password", None)
    if "main_account_name" in update_data:
        update_data["main_account_name"] = normalize_human_text(update_data["main_account_name"])
    if password:
        encryption_service = get_encryption_service()
        record.password_encrypted = encryption_service.encrypt_password(password)
    if "login_url" in update_data:
        update_data["login_url"] = normalize_main_account_login_url(record.platform, update_data.get("login_url"))
    for field, value in update_data.items():
        setattr(record, field, value)
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    await db.commit()
    await db.refresh(record)
    return _serialize_main_account(record)


@router.delete("/{main_account_id}")
async def delete_main_account(
    main_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_main_account_or_404(db, main_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"main_account_id '{main_account_id}' deleted"}


@router.post("/{main_account_id}/shop-discovery/current", response_model=ShopDiscoveryRunResponse)
async def run_current_shop_discovery(
    main_account_id: str,
    payload: ShopDiscoveryRunRequest,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_main_account_or_404(db, main_account_id)
    service = get_shop_discovery_service()
    return await service.run_current_discovery(
        db,
        platform=record.platform,
        main_account_id=record.main_account_id,
        request=payload,
    )
