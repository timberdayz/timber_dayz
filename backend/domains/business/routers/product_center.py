from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import extract_role_codes, get_current_user
from backend.models.database import get_async_db
from backend.schemas.product_center import (
    CostAssumptionCreateRequest,
    ProductCenterBindingResponse,
    ProductCenterItem,
    ProductCenterListResponse,
    SkuCreateRequest,
    SkuUpdateRequest,
    ProfitEstimateCreateRequest,
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
)

router = APIRouter(tags=["商品中心"], dependencies=[Depends(get_current_user)])
_EDITOR_ROLES = {"admin", "manager", "finance"}


def _require_editor(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False):
        return current_user
    if extract_role_codes(current_user) & _EDITOR_ROLES:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


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
        await db.commit()
        await db.refresh(row)
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
    await db.commit()
    await db.refresh(row)
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
        await db.commit()
        await db.refresh(row)
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
    await db.commit()
    await db.refresh(row)
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
    await db.execute(
        update(BridgeSpuSku)
        .where(BridgeSpuSku.sku_id == body.sku_id, BridgeSpuSku.effective_to.is_(None), BridgeSpuSku.binding_status == "active")
        .values(effective_to=body.effective_from, binding_status="historical")
    )
    row = BridgeSpuSku(spu=spu, sku_id=body.sku_id, effective_from=body.effective_from, created_by=getattr(current_user, "user_id", None))
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
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
    await db.commit()
    await db.refresh(row)
    return {"profile_id": row.profile_id, "profile_name": row.profile_name, "effective_from": row.effective_from}


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
