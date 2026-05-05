from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.platform_shop_discovery import (
    PlatformShopDiscoveryConfirmRequest,
    PlatformShopDiscoveryCreateShopAccountRequest,
    PlatformShopDiscoveryResponse,
)
from backend.services.platform_shop_discovery_service import (
    get_platform_shop_discovery_service,
)
from modules.core.db import PlatformShopDiscovery


router = APIRouter(
    prefix="/platform-shop-discoveries",
    tags=["platform shop discoveries"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[PlatformShopDiscoveryResponse])
async def list_platform_shop_discoveries(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(PlatformShopDiscovery).order_by(PlatformShopDiscovery.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{discovery_id}/confirm", response_model=PlatformShopDiscoveryResponse)
async def confirm_platform_shop_discovery(
    discovery_id: int,
    payload: PlatformShopDiscoveryConfirmRequest,
    db: AsyncSession = Depends(get_async_db),
):
    service = get_platform_shop_discovery_service()
    try:
        return await service.confirm_discovery(db, discovery_id, payload.shop_account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{discovery_id}/create-shop-account", response_model=PlatformShopDiscoveryResponse)
async def create_shop_account_from_discovery(
    discovery_id: int,
    payload: PlatformShopDiscoveryCreateShopAccountRequest,
    db: AsyncSession = Depends(get_async_db),
):
    service = get_platform_shop_discovery_service()
    try:
        return await service.create_shop_account_from_discovery(db, discovery_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
