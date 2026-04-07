from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user, require_admin
from backend.models.database import get_async_db
from backend.schemas.inventory import (
    InventoryAdjustmentCreateRequest,
    InventoryAdjustmentResponse,
    InventoryAlertResponse,
    InventoryAgingBucketResponse,
    InventoryAgingRowResponse,
    InventoryAgingSummaryResponse,
    InventoryBalanceDetailResponse,
    InventoryBalanceSummaryResponse,
    InventoryGrnPostResponse,
    InventoryGrnResponse,
    InventoryLedgerRowResponse,
    InventoryOpeningBalanceCreateRequest,
    InventoryOpeningBalanceResponse,
    InventoryReconciliationResponse,
)
from backend.services.inventory import (
    InventoryAdjustmentService,
    InventoryAgingService,
    InventoryBalanceService,
    InventoryGrnService,
    InventoryLedgerService,
    InventoryOpeningBalanceService,
    InventoryReconciliationService,
)

router = APIRouter(
    prefix="/api/inventory",
    tags=["库存管理"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/balances", response_model=List[InventoryBalanceSummaryResponse])
async def list_inventory_balances(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryBalanceService(db)
    return await service.list_balances(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )


@router.get(
    "/balances/{platform}/{shop_id}/{platform_sku}",
    response_model=InventoryBalanceDetailResponse,
)
async def get_inventory_balance_detail(
    platform: str,
    shop_id: str,
    platform_sku: str,
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryBalanceService(db)
    return await service.get_balance_detail(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )


@router.get("/ledger", response_model=List[InventoryLedgerRowResponse])
async def list_inventory_ledger(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    movement_type: Optional[str] = Query(None, description="流水类型"),
    date_from: Optional[date] = Query(None, description="开始日期"),
    date_to: Optional[date] = Query(None, description="结束日期"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数上限"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryLedgerService(db)
    return await service.list_entries(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/grns", response_model=List[InventoryGrnResponse])
async def list_inventory_grns(
    status: Optional[str] = Query(None, description="GRN状态"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryGrnService(db)
    grns = await service.list_grns(status=status, limit=limit)
    return [
        InventoryGrnResponse(
            grn_id=grn.grn_id,
            po_id=grn.po_id,
            receipt_date=grn.receipt_date,
            warehouse=grn.warehouse,
            status=grn.status,
            created_by=grn.created_by,
            created_at=grn.created_at,
            lines=[],
        )
        for grn in grns
    ]


@router.post("/grns/{grn_id}/post", response_model=InventoryGrnPostResponse)
async def post_inventory_grn(
    grn_id: str,
    platform_code: str = Query(..., description="过账所属平台编码"),
    shop_id: str = Query(..., description="过账所属店铺ID"),
    created_by: str = Query("system", description="操作人"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = InventoryGrnService(db)
    return await service.post_grn(
        grn_id=grn_id,
        platform_code=platform_code,
        shop_id=shop_id,
        created_by=created_by,
    )


@router.get("/adjustments", response_model=List[InventoryAdjustmentResponse])
async def list_inventory_adjustments(
    status: Optional[str] = Query(None, description="调整单状态"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryAdjustmentService(db)
    adjustments = await service.list_adjustments(status=status, limit=limit)
    return [
        InventoryAdjustmentResponse(
            adjustment_id=item.adjustment_id,
            adjustment_date=item.adjustment_date,
            status=item.status,
            reason=item.reason,
            notes=item.notes,
            created_by=item.created_by,
            created_at=item.created_at,
            updated_at=item.updated_at,
            lines=[],
        )
        for item in adjustments
    ]


@router.post("/adjustments", response_model=InventoryAdjustmentResponse)
async def create_inventory_adjustment(
    payload: InventoryAdjustmentCreateRequest,
    created_by: str = Query("system", description="操作人"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = InventoryAdjustmentService(db)
    return await service.create_adjustment(payload=payload, created_by=created_by)


@router.post(
    "/adjustments/{adjustment_id}/post",
    response_model=InventoryAdjustmentResponse,
)
async def post_inventory_adjustment(
    adjustment_id: str,
    created_by: str = Query("system", description="操作人"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = InventoryAdjustmentService(db)
    return await service.post_adjustment(
        adjustment_id=adjustment_id,
        created_by=created_by,
    )


@router.get("/alerts", response_model=List[InventoryAlertResponse])
async def list_inventory_alerts(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    safety_stock: int = Query(10, ge=0, description="安全库存阈值"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryReconciliationService(db)
    return await service.list_alerts(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
        safety_stock=safety_stock,
    )


@router.get(
    "/reconciliation",
    response_model=List[InventoryReconciliationResponse],
)
async def list_inventory_reconciliation(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryReconciliationService(db)
    return await service.list_reconciliation(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )


@router.get(
    "/opening-balances",
    response_model=List[InventoryOpeningBalanceResponse],
)
async def list_inventory_opening_balances(
    period: Optional[str] = Query(None, description="期初期间"),
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数上限"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryOpeningBalanceService(db)
    records = await service.list_opening_balances(
        period=period,
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
        limit=limit,
    )
    return [InventoryOpeningBalanceResponse.model_validate(item) for item in records]


@router.post(
    "/opening-balances",
    response_model=InventoryOpeningBalanceResponse,
)
async def create_inventory_opening_balance(
    payload: InventoryOpeningBalanceCreateRequest,
    created_by: str = Query("system", description="操作人"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin),
):
    service = InventoryOpeningBalanceService(db)
    return await service.create_opening_balance(
        payload=payload,
        created_by=created_by,
    )


@router.get(
    "/aging",
    response_model=List[InventoryAgingRowResponse],
)
async def list_inventory_aging(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryAgingService(db)
    return await service.list_aging_rows(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )


@router.get(
    "/aging/buckets",
    response_model=InventoryAgingSummaryResponse,
)
async def get_inventory_aging_buckets(
    platform: Optional[str] = Query(None, description="平台编码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    platform_sku: Optional[str] = Query(None, description="平台SKU"),
    db: AsyncSession = Depends(get_async_db),
):
    service = InventoryAgingService(db)
    return await service.get_aging_summary(
        platform=platform,
        shop_id=shop_id,
        platform_sku=platform_sku,
    )
