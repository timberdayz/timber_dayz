from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.inventory import InventoryReconciliationResponse
from backend.schemas.inventory_overview import (
    InventoryOverviewAlertResponse,
    InventoryOverviewProductItemResponse,
    InventoryOverviewProductListResponse,
    InventoryOverviewSummaryResponse,
)
from backend.services.inventory.overview_service import InventoryOverviewService

router = APIRouter(
    prefix="/api/inventory-overview",
    tags=["库存总览"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary", response_model=InventoryOverviewSummaryResponse)
async def get_inventory_overview_summary(
    platform: Optional[str] = Query(None, description="平台编码"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    return await service.get_summary(platform=platform)


@router.get("/products", response_model=InventoryOverviewProductListResponse)
async def get_inventory_overview_products(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    keyword: Optional[str] = Query(None, description="SKU或商品名搜索"),
    low_stock: Optional[bool] = Query(None, description="仅显示低库存"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    return await service.get_products(
        page=page,
        page_size=page_size,
        platform=platform,
        shop_id=shop_id,
        keyword=keyword,
        low_stock=low_stock,
    )


@router.get("/products/{sku}", response_model=InventoryOverviewProductItemResponse)
async def get_inventory_overview_product_detail(
    sku: str,
    platform: str = Query(..., description="平台编码"),
    shop_id: str = Query(..., description="店铺ID"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    try:
        return await service.get_product_detail(
            sku=sku,
            platform=platform,
            shop_id=shop_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/platform-breakdown",
    response_model=InventoryOverviewSummaryResponse,
)
async def get_inventory_overview_platform_breakdown(
    platform: Optional[str] = Query(None, description="平台编码"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    return await service.get_summary(platform=platform)


@router.get("/alerts", response_model=List[InventoryOverviewAlertResponse])
async def get_inventory_overview_alerts(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    low_stock_threshold: int = Query(10, ge=0, description="低库存阈值"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    return await service.get_alerts(
        platform=platform,
        shop_id=shop_id,
        low_stock_threshold=low_stock_threshold,
    )


@router.get(
    "/reconciliation-snapshot",
    response_model=List[InventoryReconciliationResponse],
)
async def get_inventory_overview_reconciliation_snapshot(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOverviewService(db)
    return await service.get_reconciliation_snapshot(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )
