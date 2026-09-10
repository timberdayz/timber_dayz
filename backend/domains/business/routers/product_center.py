from __future__ import annotations

import asyncio
from datetime import date
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import extract_role_codes, get_current_user
from backend.models.database import get_async_db
from backend.schemas.product_center import (
    CostAssumptionCreateRequest,
    CostAssumptionUpdateRequest,
    FeishuProjectionInitializeRequest,
    LogisticsBillCreateRequest,
    LogisticsBillLinesReplaceRequest,
    LogisticsBillUpdateRequest,
    LogisticsBillVoidRequest,
    ProductCenterBindingResponse,
    ProductCenterItem,
    ProductCenterListResponse,
    SkuCreateRequest,
    SkuUpdateRequest,
    ProfitEstimateCreateRequest,
    ProfitEstimateSaveRequest,
    ProfitPreviewRequest,
    SpuCreateRequest,
    SpuSkuBindingRequest,
    SpuUpdateRequest,
)
from modules.core.db import (
    BridgeSpuSku,
    DimErpSku,
    DimSpu,
    ProductCostAssumptionProfile,
    SkuProfitEstimate,
    LogisticsBill,
    LogisticsBillLine,
)
from backend.services.product_finance_service import BillTotalMismatchError, ProductFinanceService
from backend.services.feishu_projection_client import FeishuProjectionClient
from backend.services.feishu_projection_service import FeishuProjectionService, trigger_pending_projection_delivery

router = APIRouter(tags=["商品中心"], dependencies=[Depends(get_current_user)])
_EDITOR_ROLES = {"admin", "manager", "finance"}


def _require_editor(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False):
        return current_user
    if extract_role_codes(current_user) & _EDITOR_ROLES:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


def _require_projection_admin(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False) or "admin" in extract_role_codes(current_user):
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


async def _enqueue_spu_projection(db: AsyncSession, row: DimSpu) -> None:
    await FeishuProjectionService(db).enqueue(
        "spu",
        row.spu,
        {
            "spu": row.spu,
            "spu_name": row.spu_name,
            "category_l1": row.category_l1,
            "category_l2": row.category_l2,
            "biz_status": row.biz_status,
            "owner_user_id": row.owner_user_id,
        },
    )


async def _enqueue_sku_projection(db: AsyncSession, row: DimErpSku) -> None:
    await FeishuProjectionService(db).enqueue(
        "sku",
        str(row.sku_id),
        {
            "sku_id": row.sku_id,
            "sku_key": row.sku_key,
            "sku_name": row.sku_name,
            "specification": row.specification,
            "weight_kg": row.weight_kg,
            "package_length_cm": row.package_length_cm,
            "package_width_cm": row.package_width_cm,
            "package_height_cm": row.package_height_cm,
            "units_per_carton": row.units_per_carton,
            "default_purchase_cost": row.default_purchase_cost,
            "purchase_cost_source": row.purchase_cost_source,
            "purchase_cost_confidence": row.purchase_cost_confidence,
        },
    )


@router.get("/api/spus", response_model=ProductCenterListResponse)
async def list_spus(
    keyword: str | None = Query(None),
    biz_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if keyword:
        pattern = f"%{keyword}%"
        filters.append((DimSpu.spu.ilike(pattern)) | (DimSpu.spu_name.ilike(pattern)))
    if biz_status:
        filters.append(DimSpu.biz_status == biz_status)
    total = int((await db.execute(select(func.count()).select_from(DimSpu).where(*filters))).scalar() or 0)
    rows = (await db.execute(select(DimSpu).where(*filters).order_by(DimSpu.spu).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = [ProductCenterItem.model_validate(row) for row in rows]
    return ProductCenterListResponse(data=items, page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size)


@router.post("/api/spus", response_model=ProductCenterItem, status_code=201)
async def create_spu(body: SpuCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = DimSpu(**body.model_dump())
    db.add(row)
    try:
        await db.flush()
        await _enqueue_spu_projection(db, row)
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SPU already exists") from exc
    return ProductCenterItem.model_validate(row)


@router.patch("/api/spus/{spu}", response_model=ProductCenterItem)
async def update_spu(spu: str, body: SpuUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(DimSpu, spu)
    if row is None:
        raise HTTPException(status_code=404, detail="SPU not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await _enqueue_spu_projection(db, row)
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return ProductCenterItem.model_validate(row)


@router.get("/api/skus", response_model=ProductCenterListResponse)
async def list_skus(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if keyword:
        pattern = f"%{keyword}%"
        filters.append((DimErpSku.sku_key.ilike(pattern)) | (DimErpSku.sku_name.ilike(pattern)))
    total = int((await db.execute(select(func.count()).select_from(DimErpSku).where(*filters))).scalar() or 0)
    rows = (await db.execute(select(DimErpSku).where(*filters).order_by(DimErpSku.sku_key).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = [ProductCenterItem.model_validate(row) for row in rows]
    return ProductCenterListResponse(data=items, page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size)


@router.post("/api/skus", response_model=ProductCenterItem, status_code=201)
async def create_sku(body: SkuCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = DimErpSku(**body.model_dump())
    db.add(row)
    try:
        await db.flush()
        await _enqueue_sku_projection(db, row)
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from exc
    return ProductCenterItem.model_validate(row)


@router.patch("/api/skus/{sku_id}", response_model=ProductCenterItem)
async def update_sku(sku_id: int, body: SkuUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(DimErpSku, sku_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await _enqueue_sku_projection(db, row)
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return ProductCenterItem.model_validate(row)


@router.get("/api/spus/{spu}/skus", response_model=list[ProductCenterBindingResponse])
async def list_spu_skus(spu: str, db: AsyncSession = Depends(get_async_db)):
    rows = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.spu == spu).order_by(BridgeSpuSku.effective_from.desc()))).scalars().all()
    return [ProductCenterBindingResponse.model_validate(row) for row in rows]


@router.post("/api/spus/{spu}/skus", response_model=ProductCenterBindingResponse, status_code=201)
async def bind_spu_sku(spu: str, body: SpuSkuBindingRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    if await db.get(DimSpu, spu) is None:
        raise HTTPException(status_code=404, detail="SPU not found")
    if await db.get(DimErpSku, body.sku_id) is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    current_binding = (
        await db.execute(
            select(BridgeSpuSku).where(
                BridgeSpuSku.sku_id == body.sku_id,
                BridgeSpuSku.effective_to.is_(None),
                BridgeSpuSku.binding_status == "active",
            )
        )
    ).scalars().first()
    if current_binding is not None and body.effective_from <= current_binding.effective_from:
        raise HTTPException(status_code=422, detail="effective_from must be later than the current binding")
    await db.execute(
        update(BridgeSpuSku)
        .where(BridgeSpuSku.sku_id == body.sku_id, BridgeSpuSku.effective_to.is_(None), BridgeSpuSku.binding_status == "active")
        .values(effective_to=body.effective_from, binding_status="historical")
    )
    row = BridgeSpuSku(spu=spu, sku_id=body.sku_id, effective_from=body.effective_from, created_by=getattr(current_user, "user_id", None))
    db.add(row)
    try:
        await _enqueue_spu_projection(db, await db.get(DimSpu, spu))
        await _enqueue_sku_projection(db, await db.get(DimErpSku, body.sku_id))
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SKU binding conflicts with an active assignment") from exc
    return ProductCenterBindingResponse.model_validate(row)


@router.get("/api/cost-assumption-profiles")
async def list_cost_assumptions(db: AsyncSession = Depends(get_async_db)):
    rows = (await db.execute(select(ProductCostAssumptionProfile).where(ProductCostAssumptionProfile.active.is_(True)).order_by(ProductCostAssumptionProfile.effective_from.desc()))).scalars().all()
    return [
        {
            "profile_id": row.profile_id,
            "profile_name": row.profile_name,
            "destination": row.destination,
            "transport_type": row.transport_type,
            "billing_basis": row.billing_basis,
            "freight_unit_rate": float(row.freight_unit_rate) if row.freight_unit_rate is not None else None,
            "storage_unit_rate": float(row.storage_unit_rate) if row.storage_unit_rate is not None else None,
            "platform_fee_rate": float(row.platform_fee_rate) if row.platform_fee_rate is not None else None,
            "return_rate": float(row.return_rate) if row.return_rate is not None else None,
            "damage_rate": float(row.damage_rate) if row.damage_rate is not None else None,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "assumption_source": row.assumption_source,
            "confidence_level": row.confidence_level,
        }
        for row in rows
    ]


@router.post("/api/cost-assumption-profiles", status_code=201)
async def create_cost_assumption(body: CostAssumptionCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = ProductCostAssumptionProfile(**body.model_dump())
    db.add(row)
    await db.flush()
    await FeishuProjectionService(db).enqueue_full_refresh("cost_assumption_created")
    await db.commit()
    asyncio.create_task(trigger_pending_projection_delivery())
    await db.refresh(row)
    return {"profile_id": row.profile_id, "profile_name": row.profile_name, "effective_from": row.effective_from}


@router.patch("/api/cost-assumption-profiles/{profile_id}")
async def update_cost_assumption(profile_id: int, body: CostAssumptionUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(ProductCostAssumptionProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="cost assumption profile not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await FeishuProjectionService(db).enqueue_full_refresh("cost_assumption_changed")
    await db.commit()
    asyncio.create_task(trigger_pending_projection_delivery())
    return {"profile_id": row.profile_id, "active": row.active, "updated_at": row.updated_at}


def _serialize_bill(bill: LogisticsBill, lines: list[LogisticsBillLine] | None = None) -> dict:
    payload = {
        "bill_id": bill.bill_id,
        "bill_no": bill.bill_no,
        "logistics_provider": bill.logistics_provider,
        "bill_date": bill.bill_date,
        "transport_type": bill.transport_type,
        "destination": bill.destination,
        "currency": bill.currency,
        "total_amount": float(bill.total_amount or 0),
        "status": bill.status,
        "notes": bill.notes,
        "confirmed_at": bill.confirmed_at,
        "voided_at": bill.voided_at,
    }
    if lines is not None:
        payload["lines"] = [
            {
                "line_id": line.line_id,
                "sku_id": line.sku_id,
                "shipped_qty": float(line.shipped_qty or 0),
                "calculated_total_weight_kg": float(line.calculated_total_weight_kg or 0),
                "calculated_total_volume_cbm": float(line.calculated_total_volume_cbm or 0),
                "actual_total_weight_kg": float(line.actual_total_weight_kg) if line.actual_total_weight_kg is not None else None,
                "actual_total_volume_cbm": float(line.actual_total_volume_cbm) if line.actual_total_volume_cbm is not None else None,
                "headhaul_cost": float(line.headhaul_cost or 0),
                "handling_cost": float(line.handling_cost or 0),
                "last_mile_cost": float(line.last_mile_cost or 0),
                "line_total_amount": float(line.line_total_amount or 0),
                "unit_headhaul_cost": float(line.unit_headhaul_cost or 0),
                "unit_handling_cost": float(line.unit_handling_cost or 0),
                "unit_last_mile_cost": float(line.unit_last_mile_cost or 0),
                "notes": line.notes,
            }
            for line in lines
        ]
    return payload


@router.get("/api/logistics-bills")
async def list_logistics_bills(status: str | None = Query(None), db: AsyncSession = Depends(get_async_db)):
    statement = select(LogisticsBill).order_by(LogisticsBill.bill_date.desc(), LogisticsBill.bill_id.desc())
    if status:
        statement = statement.where(LogisticsBill.status == status)
    rows = (await db.execute(statement)).scalars().all()
    return [_serialize_bill(row) for row in rows]


@router.post("/api/logistics-bills", status_code=201)
async def create_logistics_bill(body: LogisticsBillCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = LogisticsBill(**body.model_dump(), status="draft")
    db.add(row)
    try:
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="logistics bill number already exists") from exc
    return _serialize_bill(row, [])


@router.get("/api/logistics-bills/{bill_id}")
async def get_logistics_bill(bill_id: int, db: AsyncSession = Depends(get_async_db)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lines = (await db.execute(select(LogisticsBillLine).where(LogisticsBillLine.bill_id == bill_id).order_by(LogisticsBillLine.line_no))).scalars().all()
    return _serialize_bill(bill, lines)


@router.patch("/api/logistics-bills/{bill_id}")
async def update_logistics_bill(bill_id: int, body: LogisticsBillUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if bill.status != "draft":
        raise HTTPException(status_code=409, detail="only draft logistics bills can be edited")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(bill, key, value)
    await db.commit()
    return _serialize_bill(bill)


@router.put("/api/logistics-bills/{bill_id}/lines")
async def replace_logistics_bill_lines(bill_id: int, body: LogisticsBillLinesReplaceRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        lines = await service.replace_bill_lines(bill, [line.model_dump() for line in body.lines])
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill, lines)


@router.post("/api/logistics-bills/{bill_id}/confirm")
async def confirm_logistics_bill(bill_id: int, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.confirm_bill(bill=await service.get_bill_or_raise(bill_id), user_id=getattr(current_user, "user_id", None))
        await FeishuProjectionService(db).enqueue_full_refresh("logistics_bill_confirmed")
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except BillTotalMismatchError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill)


@router.post("/api/logistics-bills/{bill_id}/void")
async def void_logistics_bill(bill_id: int, body: LogisticsBillVoidRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        sku_ids = [sku_id for sku_id, in (await db.execute(select(LogisticsBillLine.sku_id).where(LogisticsBillLine.bill_id == bill_id, LogisticsBillLine.sku_id.is_not(None)))).all()]
        bill = await service.void_bill(bill, getattr(current_user, "user_id", None), body.reason)
        for sku_id in sku_ids:
            sku = await db.get(DimErpSku, sku_id)
            if sku is not None:
                await _enqueue_sku_projection(db, sku)
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill)


@router.get("/api/product-profit-estimates")
async def list_profit_estimates(
    sku_id: int | None = Query(None, gt=0),
    scenario: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if sku_id is not None:
        filters.append(SkuProfitEstimate.sku_id == sku_id)
    if scenario:
        filters.append(SkuProfitEstimate.scenario == scenario)
    rows = (await db.execute(select(SkuProfitEstimate).where(*filters).order_by(SkuProfitEstimate.estimate_as_of.desc()).limit(limit))).scalars().all()
    return [
        {
            "estimate_id": row.estimate_id,
            "sku_id": row.sku_id,
            "estimate_as_of": row.estimate_as_of,
            "assumption_version": row.assumption_version,
            "scenario": row.scenario,
            "selling_price": float(row.selling_price) if row.selling_price is not None else None,
            "coupon_amount": float(row.coupon_amount) if row.coupon_amount is not None else None,
            "estimated_contribution_profit": float(row.estimated_contribution_profit) if row.estimated_contribution_profit is not None else None,
            "estimated_margin_rate": float(row.estimated_margin_rate) if row.estimated_margin_rate is not None else None,
            "cost_completeness": row.cost_completeness,
            "confidence_level": row.confidence_level,
        }
        for row in rows
    ]


@router.post("/api/product-profit-estimates", status_code=201)
async def create_profit_estimate(body: ProfitEstimateCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    if await db.get(DimErpSku, body.sku_id) is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    values = body.model_dump()
    revenue = (values.get("selling_price") or 0) - (values.get("coupon_amount") or 0)
    costs = sum(values.get(key) or 0 for key in ("purchase_cost", "logistics_cost", "storage_cost", "platform_fee", "expected_return_loss", "expected_damage_loss"))
    values["estimated_contribution_profit"] = revenue - costs
    values["estimated_margin_rate"] = (revenue - costs) / revenue if revenue > 0 else None
    row = SkuProfitEstimate(**values)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"estimate_id": row.estimate_id, "sku_id": row.sku_id, "estimated_contribution_profit": float(row.estimated_contribution_profit), "estimated_margin_rate": float(row.estimated_margin_rate) if row.estimated_margin_rate is not None else None}


@router.post("/api/product-profit-estimates/preview")
async def preview_product_profit(body: ProfitPreviewRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    try:
        result = await ProductFinanceService(db).preview_profit(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {key: float(value) if hasattr(value, "as_tuple") else value for key, value in result.items()}


@router.post("/api/product-profit-estimates/baseline", status_code=201)
async def save_baseline_product_profit(body: ProfitEstimateSaveRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    try:
        row = await ProductFinanceService(db).save_profit_estimate(body.model_dump())
        await FeishuProjectionService(db).enqueue("sku", str(row.sku_id), {"sku_id": row.sku_id, "reason": "baseline_profit_saved", "estimate_id": row.estimate_id})
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"estimate_id": row.estimate_id, "sku_id": row.sku_id, "scenario": row.scenario}


@router.post("/api/feishu-projection/initialize")
async def initialize_feishu_projection(body: FeishuProjectionInitializeRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_projection_admin)):
    spu_table_id = body.spu_table_id or os.getenv("FEISHU_PRODUCT_SPU_TABLE_ID")
    sku_table_id = body.sku_table_id or os.getenv("FEISHU_PRODUCT_SKU_TABLE_ID")
    client = FeishuProjectionClient()
    try:
        config = await FeishuProjectionService(db).initialize_tables(client, spu_table_id, sku_table_id)
        await db.commit()
    except RuntimeError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": config.status, "spu_table_id": config.spu_table_id, "sku_table_id": config.sku_table_id}


@router.get("/api/feishu-projection/status")
async def get_feishu_projection_status(db: AsyncSession = Depends(get_async_db)):
    return await FeishuProjectionService(db).status()


@router.post("/api/feishu-projection/retry-failed")
async def retry_failed_feishu_projection(db: AsyncSession = Depends(get_async_db), _user=Depends(_require_projection_admin)):
    retried = await FeishuProjectionService(db).retry_failed()
    await db.commit()
    return {"retried": retried}


@router.get("/api/spu-operating")
async def list_spu_operating(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    where = ""
    params: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if keyword:
        where = "WHERE spu ILIKE :keyword OR spu_name ILIKE :keyword"
        params["keyword"] = f"%{keyword}%"
    rows = (
        await db.execute(
            text(
                f"SELECT * FROM mart.spu_operating_current {where} ORDER BY spu LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]
