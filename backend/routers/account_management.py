#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号管理 API。

运行时数据源是数据库中的 `core.platform_accounts`。
历史上的 `local_accounts.py` 仅保留为本地记录文件，不再作为生产运行路径。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.account import (
    AccountCreate,
    AccountResponse,
    AccountStats,
    AccountUpdate,
    BatchCreateRequest,
)
from backend.services.encryption_service import get_encryption_service
from backend.services.shop_sync_service import sync_platform_account_to_dim_shop
from modules.core.db import PlatformAccount
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/accounts", tags=["账号管理"])


def _default_capabilities() -> dict:
    return {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
    }


async def _get_account_or_404(db: AsyncSession, account_id: str) -> PlatformAccount:
    result = await db.execute(
        select(PlatformAccount).where(PlatformAccount.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号 '{account_id}' 不存在")
    return account


@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    db: AsyncSession = Depends(get_async_db),
):
    existing = await db.execute(
        select(PlatformAccount).where(PlatformAccount.account_id == account.account_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"账号ID '{account.account_id}' 已存在")

    encryption_service = get_encryption_service()
    db_account = PlatformAccount(
        account_id=account.account_id,
        parent_account=account.parent_account,
        platform=account.platform,
        account_alias=account.account_alias,
        store_name=account.store_name,
        shop_type=account.shop_type,
        shop_region=account.shop_region,
        username=account.username,
        password_encrypted=encryption_service.encrypt_password(account.password),
        login_url=account.login_url,
        email=account.email,
        phone=account.phone,
        region=account.region,
        currency=account.currency,
        capabilities=account.capabilities.model_dump(),
        enabled=account.enabled,
        proxy_required=account.proxy_required,
        notes=account.notes,
        created_by="system",
        updated_by="system",
    )

    db.add(db_account)
    await db.commit()
    await db.refresh(db_account)

    try:
        await sync_platform_account_to_dim_shop(db, db_account)
        await db.commit()
    except Exception as exc:
        logger.warning(f"[AccountManagement] 同步店铺到 dim_shops 失败: {exc}", exc_info=True)

    logger.info(f"账号创建成功: {account.account_id}")
    return db_account


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="平台筛选"),
    enabled: Optional[bool] = Query(None, description="启用状态筛选"),
    shop_type: Optional[str] = Query(None, description="店铺类型筛选"),
    search: Optional[str] = Query(None, description="搜索(店铺名或账号ID)"),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(PlatformAccount)

    if platform:
        stmt = stmt.where(PlatformAccount.platform.ilike(platform))
    if enabled is not None:
        stmt = stmt.where(PlatformAccount.enabled == enabled)
    if shop_type:
        stmt = stmt.where(PlatformAccount.shop_type == shop_type)
    if search:
        stmt = stmt.where(
            PlatformAccount.store_name.ilike(f"%{search}%")
            | PlatformAccount.account_id.ilike(f"%{search}%")
        )

    stmt = stmt.order_by(PlatformAccount.created_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    logger.info(f"查询账号列表: {len(accounts)} 条记录")
    return accounts


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    return await _get_account_or_404(db, account_id)


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    account_update: AccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    db_account = await _get_account_or_404(db, account_id)
    update_data = account_update.model_dump(exclude_unset=True)

    password = update_data.pop("password", None)
    if password:
        encryption_service = get_encryption_service()
        db_account.password_encrypted = encryption_service.encrypt_password(password)

    capabilities = update_data.get("capabilities")
    if capabilities is not None and hasattr(capabilities, "model_dump"):
        update_data["capabilities"] = capabilities.model_dump()

    for field, value in update_data.items():
        setattr(db_account, field, value)

    db_account.updated_by = "system"
    db_account.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_account)

    try:
        await sync_platform_account_to_dim_shop(db, db_account)
        await db.commit()
    except Exception as exc:
        logger.warning(f"[AccountManagement] 同步店铺到 dim_shops 失败: {exc}", exc_info=True)

    logger.info(f"账号更新成功: {account_id}")
    return db_account


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    db_account = await _get_account_or_404(db, account_id)
    await db.delete(db_account)
    await db.commit()
    logger.info(f"账号删除成功: {account_id}")
    return {"message": f"账号 '{account_id}' 已删除"}


@router.post("/batch", response_model=List[AccountResponse])
async def batch_create_accounts(
    batch_request: BatchCreateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    created_accounts: list[PlatformAccount] = []
    encryption_service = get_encryption_service()
    encrypted_password = encryption_service.encrypt_password(batch_request.password)

    for shop in batch_request.shops:
        account_id = (
            f"{batch_request.platform}_"
            f"{shop.get('shop_region', 'unknown').lower()}_"
            f"{shop.get('store_name', 'shop')}"
        )

        existing = await db.execute(
            select(PlatformAccount).where(PlatformAccount.account_id == account_id)
        )
        if existing.scalar_one_or_none() is not None:
            logger.warning(f"账号 {account_id} 已存在, 跳过")
            continue

        db_account = PlatformAccount(
            account_id=account_id,
            parent_account=batch_request.parent_account,
            platform=batch_request.platform,
            account_alias=shop.get("account_alias"),
            store_name=shop.get("store_name"),
            shop_type=shop.get("shop_type", "local"),
            shop_region=shop.get("shop_region"),
            username=batch_request.username,
            password_encrypted=encrypted_password,
            login_url=shop.get("login_url"),
            region="CN",
            currency=shop.get("currency", "CNY"),
            capabilities={
                **_default_capabilities(),
                "services": shop.get("shop_type") == "local",
            },
            enabled=True,
            created_by="system",
            updated_by="system",
        )
        db.add(db_account)
        created_accounts.append(db_account)

    await db.commit()

    for db_account in created_accounts:
        try:
            await sync_platform_account_to_dim_shop(db, db_account)
        except Exception as exc:
            logger.warning(f"[AccountManagement] 同步店铺失败 {db_account.account_id}: {exc}", exc_info=True)

    await db.commit()
    logger.info(f"批量创建成功: {len(created_accounts)} 个账号")
    return created_accounts


@router.get("/stats/summary", response_model=AccountStats)
async def get_account_stats(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(PlatformAccount))
    all_accounts = result.scalars().all()

    total = len(all_accounts)
    active = sum(1 for account in all_accounts if account.enabled)
    inactive = total - active

    platform_breakdown: dict[str, int] = {}
    for account in all_accounts:
        platform_breakdown[account.platform] = platform_breakdown.get(account.platform, 0) + 1

    return AccountStats(
        total=total,
        active=active,
        inactive=inactive,
        platforms=len(platform_breakdown),
        platform_breakdown=platform_breakdown,
    )
