from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.platform_shop_discovery import (
    PlatformShopDiscoveryConfirmRequest,
    PlatformShopDiscoveryCreateShopAccountRequest,
    PlatformShopDiscoveryResponse,
)
from backend.services.platform_shop_discovery_service import (
    PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES,
    get_platform_shop_discovery_service,
)
from modules.core.db import PlatformShopDiscovery


router = APIRouter(
    prefix="/platform-shop-discoveries",
    tags=["platform shop discoveries"],
    dependencies=[Depends(require_admin)],
)


def _parse_statuses(raw: Optional[str]) -> list[str]:
    """把 ``?status=a,b,c`` 解析成状态列表(忽略空串)。"""
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


@router.get("/issues/summary")
async def summarize_platform_shop_discovery_issues(
    platform: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
):
    """采集期身份异常的汇总 —— 给「店铺身份未对齐」告警面板用。

    单独一个端点而不是把摘要塞进列表返回体: 列表返回的是**数组**,
    塞元数据会破坏既有前端契约。
    """
    service = get_platform_shop_discovery_service()
    return await service.summarize_platform_shop_discovery_issues(db, platform=platform)


@router.get("/statuses")
async def list_platform_shop_discovery_statuses():
    """状态字典 —— 让前端/排查脚本知道有哪些状态、哪些算问题态。"""
    return {
        "issue_statuses": sorted(PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES),
    }


@router.get("", response_model=list[PlatformShopDiscoveryResponse])
async def list_platform_shop_discoveries(
    status: Optional[str] = Query(
        default=None,
        description="按状态过滤, 多个用逗号分隔(如 stale_url,conflict_detected)",
    ),
    only_issues: bool = Query(
        default=False,
        description="只返回采集期就发现身份对不上的记录",
    ),
    db: AsyncSession = Depends(get_async_db),
):
    service = get_platform_shop_discovery_service()
    records = await service.list_platform_shop_discoveries(
        db,
        statuses=_parse_statuses(status),
        only_issues=only_issues,
    )
    return records


@router.post("/{discovery_id}/confirm", response_model=PlatformShopDiscoveryResponse)
async def confirm_platform_shop_discovery(
    discovery_id: int,
    payload: PlatformShopDiscoveryConfirmRequest,
    db: AsyncSession = Depends(get_async_db),
):
    service = get_platform_shop_discovery_service()
    try:
        return await service.confirm_discovery(
            db, discovery_id, payload.shop_account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{discovery_id}/create-shop-account", response_model=PlatformShopDiscoveryResponse
)
async def create_shop_account_from_discovery(
    discovery_id: int,
    payload: PlatformShopDiscoveryCreateShopAccountRequest,
    db: AsyncSession = Depends(get_async_db),
):
    service = get_platform_shop_discovery_service()
    try:
        return await service.create_shop_account_from_discovery(
            db, discovery_id, payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
