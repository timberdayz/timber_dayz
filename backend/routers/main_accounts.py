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
from backend.services.encryption_service import get_encryption_service
from modules.core.db import MainAccount


router = APIRouter(prefix="/main-accounts", tags=["主账号管理"])


async def _get_main_account_or_404(db: AsyncSession, main_account_id: str) -> MainAccount:
    result = await db.execute(
        select(MainAccount).where(MainAccount.main_account_id == main_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"主账号ID '{main_account_id}' 不存在")
    return record


@router.get("", response_model=List[MainAccountResponse])
async def list_main_accounts(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(MainAccount).order_by(MainAccount.platform, MainAccount.main_account_id)
    )
    return result.scalars().all()


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
        raise HTTPException(status_code=400, detail=f"主账号ID '{payload.main_account_id}' 已存在")

    encryption_service = get_encryption_service()
    record = MainAccount(
        platform=payload.platform,
        main_account_id=payload.main_account_id,
        username=payload.username,
        password_encrypted=encryption_service.encrypt_password(payload.password),
        login_url=payload.login_url,
        enabled=payload.enabled,
        notes=payload.notes,
        created_by="system",
        updated_by="system",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/{main_account_id}", response_model=MainAccountResponse)
async def update_main_account(
    main_account_id: str,
    payload: MainAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_main_account_or_404(db, main_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    password = update_data.pop("password", None)
    if password:
        encryption_service = get_encryption_service()
        record.password_encrypted = encryption_service.encrypt_password(password)
    for field, value in update_data.items():
        setattr(record, field, value)
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{main_account_id}")
async def delete_main_account(
    main_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_main_account_or_404(db, main_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"主账号ID '{main_account_id}' 已删除"}
