from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.platform_shop_discovery import PlatformShopDiscoveryResponse
from backend.services.platform_shop_discovery_service import (
    get_platform_shop_discovery_service,
)
from modules.core.db import PlatformShopDiscovery


router = APIRouter(prefix="/platform-shop-discoveries", tags=["平台店铺ID发现"])


class PlatformShopDiscoveryConfirmRequest(BaseModel):
    shop_account_id: str = Field(..., description="确认归属的店铺账号ID")


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
