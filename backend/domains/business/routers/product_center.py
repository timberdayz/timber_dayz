from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
import re

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
    LogisticsBillPurchaseOrdersReplaceRequest,
    PurchaseOrderLineCostSupplementRequest,
    LogisticsProviderRuleCreateRequest,
    LogisticsProviderRuleUpdateRequest,
    LogisticsBillUpdateRequest,
    LogisticsBillVoidRequest,
    ProductCenterBindingResponse,
    BulkMutationResponse,
    ProductCategoryCreateRequest,
    ProductCategoryResponse,
    ProductCategoryUpdateRequest,
    ProductCenterItem,
    ProductCenterListResponse,
    ProductWarehouseCreateRequest,
    ProductWarehouseUpdateRequest,
    PlatformFeeRateUpdateRequest,
    PlatformSkuProfitCandidateResponse,
    PlatformSkuProfitCandidatePageResponse,
    PlatformSkuProfitEstimateRequest,
    PlatformSkuProfitDraftRequest,
    PlatformSkuProfitPreviewRequest,
    WarehouseStorageRuleCreateRequest,
    WarehouseStorageRuleUpdateRequest,
    SkuCreateRequest,
    SkuUpdateRequest,
    SkuOperatingDimensionsResponse,
    SkuOperatingProfitResponse,
    SkuOperatingProfitSaveResponse,
    SkuOperatingProfitHistoryResponse,
    SpuBulkRequest,
    SkuBulkRequest,
    ProfitEstimateCreateRequest,
    ProfitEstimateSaveRequest,
    ProfitPreviewRequest,
    SkuOperatingProfileBulkRequest,
    SkuOperatingProfileCreateRequest,
    SkuOperatingProfileResponse,
    SkuOperatingProfileUpdateRequest,
    SkuOperatingProfitRequest,
    SpuCreateRequest,
    SpuSkuBindingRequest,
    SpuUpdateRequest,
)
from modules.core.db import (
    BridgeSpuSku,
    BridgeErpSkuKey,
    DimErpSku,
    DimSpu,
    ProductCostAssumptionProfile,
    SkuProfitEstimate,
    LogisticsBill,
    LogisticsBillLine,
    LogisticsBillLineAllocation,
    LogisticsBillPurchaseOrder,
    LogisticsProviderRule,
    POHeader,
    POLine,
    GRNHeader,
    DimProductCategory,
    DimPlatform,
    DimWarehouse,
    FactAuditLog,
    SkuOperatingProfile,
    WarehouseStorageRule,
)
from backend.services.product_finance_service import BillTotalMismatchError, ProductFinanceService
from backend.services.product_profit_service import (
    build_platform_profit_preview,
    reference_storage_days,
)
from backend.services.feishu_projection_client import FeishuProjectionClient
from backend.services.feishu_projection_service import FeishuProjectionService, trigger_pending_projection_delivery

router = APIRouter(tags=["商品中心"], dependencies=[Depends(get_current_user)])
_EDITOR_ROLES = {"admin", "manager", "finance", "operator"}


async def _write_product_center_audit(
    db: AsyncSession,
    user,
    *,
    action_type: str,
    resource_type: str,
    resource_id: str,
    changes: dict,
) -> None:
    """Append a best-effort audit entry without relying on optional user fields."""
    user_id = getattr(user, "user_id", None)
    if user_id is None:
        return
    username = (
        getattr(user, "username", None)
        or getattr(user, "email", None)
        or f"user:{user_id}"
    )
    db.add(
        FactAuditLog(
            user_id=user_id,
            username=str(username)[:100],
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action_description=f"product center {action_type}: {resource_type}",
            changes_json=json.dumps(changes, ensure_ascii=False, default=str),
        )
    )


def _decimal_payload(value):
    if hasattr(value, "as_tuple"):
        return float(value)
    if isinstance(value, dict):
        return {key: _decimal_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_payload(item) for item in value]
    return value


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


def _require_platform_fee_editor(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False) or extract_role_codes(current_user) & {"admin", "manager", "finance"}:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("/api/product-categories", response_model=list[ProductCategoryResponse])
async def list_product_categories(
    level: int | None = Query(None, ge=1, le=2),
    parent_category_code: str | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if level is not None:
        filters.append(DimProductCategory.level == level)
    if parent_category_code is not None:
        filters.append(DimProductCategory.parent_category_code == parent_category_code)
    if not include_inactive:
        filters.append(DimProductCategory.status == "active")
        filters.append(DimProductCategory.is_selectable.is_(True))
    rows = (await db.execute(select(DimProductCategory).where(*filters).order_by(DimProductCategory.level, DimProductCategory.category_code))).scalars().all()
    return [ProductCategoryResponse.model_validate(row) for row in rows]


@router.post("/api/product-categories", response_model=ProductCategoryResponse, status_code=201)
async def create_product_category(body: ProductCategoryCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    if body.level == 2:
        parent = (
            await db.execute(
                select(DimProductCategory)
                .where(DimProductCategory.category_code == body.parent_category_code)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if parent is None or parent.level != 1 or (body.status == "active" and parent.status != "active"):
            raise HTTPException(status_code=422, detail="level 2 category must reference an active level 1 category when active")
    row = DimProductCategory(**body.model_dump())
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="product_category",
            resource_id=row.category_code,
            changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="category code already exists") from exc
    return ProductCategoryResponse.model_validate(row)


@router.patch("/api/product-categories/{category_code}", response_model=ProductCategoryResponse)
async def update_product_category(category_code: str, body: ProductCategoryUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = (
        await db.execute(
            select(DimProductCategory)
            .where(DimProductCategory.category_code == category_code)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="category not found")
    values = body.model_dump(exclude_unset=True)
    if values.get("status") == "inactive" and row.level == 1:
        active_children = (
            await db.execute(
                select(DimProductCategory.category_code)
                .where(
                    DimProductCategory.parent_category_code == row.category_code,
                    DimProductCategory.status == "active",
                )
                .with_for_update()
            )
        ).scalars().all()
        if active_children:
            raise HTTPException(status_code=409, detail="cannot deactivate level 1 category with active children")
    if values.get("status") == "active" and row.level == 2:
        parent = (
            await db.execute(
                select(DimProductCategory)
                .where(
                    DimProductCategory.category_code == row.parent_category_code
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if parent is None or parent.status != "active":
            raise HTTPException(status_code=422, detail="cannot activate level 2 category under inactive level 1 parent")
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="product_category",
        resource_id=row.category_code,
        changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return ProductCategoryResponse.model_validate(row)


async def _apply_spu_category(
    db: AsyncSession,
    values: dict,
    *,
    existing_category_l2_code: str | None = None,
) -> dict:
    """Resolve a selected secondary category into its stable parent and display names."""
    category_l2_code = values.get("category_l2_code")
    legacy_category_value = values.get("category_l2")
    if not category_l2_code and isinstance(legacy_category_value, str):
        if re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*", legacy_category_value):
            category_l2_code = legacy_category_value
    category_fields_provided = any(
        key in values
        for key in ("category_l1_code", "category_l1", "category_l2_code", "category_l2")
    )
    if not category_l2_code and category_fields_provided:
        if legacy_category_value == existing_category_l2_code:
            for key in ("category_l1_code", "category_l1", "category_l2_code", "category_l2"):
                values.pop(key, None)
            return values
        if "category_l1_code" in values and "category_l2_code" not in values and "category_l2" not in values:
            raise HTTPException(
                status_code=422,
                detail="category_l1_code cannot be set without category_l2_code",
            )
        raise HTTPException(
            status_code=422,
            detail="category_l2_code must reference a category code",
        )
    if not category_l2_code:
        return values

    category_l2 = await db.get(DimProductCategory, category_l2_code)
    if (
        category_l2 is None
        or category_l2.level != 2
        or category_l2.status != "active"
        or (
            not category_l2.is_selectable
            and category_l2_code != existing_category_l2_code
        )
    ):
        raise HTTPException(status_code=422, detail="category_l2_code must reference an active selectable level 2 category")
    category_l1 = await db.get(DimProductCategory, category_l2.parent_category_code)
    if category_l1 is None or category_l1.level != 1 or category_l1.status != "active":
        raise HTTPException(status_code=422, detail="category_l2_code must have an active level 1 parent")
    requested_l1_code = values.get("category_l1_code")
    if requested_l1_code and requested_l1_code != category_l1.category_code:
        raise HTTPException(status_code=422, detail="category_l1_code must match the selected level 2 category")

    return {
        **values,
        "category_l1_code": category_l1.category_code,
        "category_l2_code": category_l2.category_code,
        "category_l1": category_l1.name_zh,
        "category_l2": category_l2.name_zh,
    }


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


async def _enqueue_platform_sku_profit_projection(db: AsyncSession, row: SkuOperatingProfile) -> None:
    await FeishuProjectionService(db).enqueue(
        "platform_sku_profit",
        str(row.profile_id),
        {
            "profile_id": row.profile_id,
            "reason": "platform_sku_profit_changed",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "selling_price": float(row.selling_price) if row.selling_price is not None else None,
            "expected_logistics_cost": float(row.expected_logistics_cost) if row.expected_logistics_cost is not None else None,
            "expected_storage_cost": float(row.expected_storage_cost) if row.expected_storage_cost is not None else None,
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
    values = body.model_dump()
    if not values.get("category_l2_code") and not values.get("category_l2"):
        raise HTTPException(status_code=422, detail="category_l2_code is required when creating an SPU")
    row = DimSpu(**(await _apply_spu_category(db, values)))
    db.add(row)
    try:
        await db.flush()
        await _enqueue_spu_projection(db, row)
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="spu",
            resource_id=row.spu, changes=values,
        )
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
    values = await _apply_spu_category(
        db,
        body.model_dump(exclude_unset=True),
        existing_category_l2_code=row.category_l2_code or row.category_l2,
    )
    for key, value in values.items():
        setattr(row, key, value)
    await _enqueue_spu_projection(db, row)
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="spu",
        resource_id=row.spu, changes=values,
    )
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return ProductCenterItem.model_validate(row)


@router.post("/api/spus/bulk", response_model=BulkMutationResponse)
async def bulk_save_spus(body: SpuBulkRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    requested_spus = [item.spu for item in body.items]
    if len(requested_spus) != len(set(requested_spus)):
        raise HTTPException(status_code=422, detail="bulk request cannot contain duplicate SPUs")

    created = 0
    updated = 0
    rows: list[DimSpu] = []
    row_actions: list[tuple[DimSpu, str, dict]] = []
    try:
        for item in body.items:
            row = await db.get(DimSpu, item.spu)
            values = await _apply_spu_category(
                db,
                item.model_dump(exclude_unset=True),
                existing_category_l2_code=(row.category_l2_code or row.category_l2) if row else None,
            )
            if row is None:
                if not values.get("spu_name"):
                    raise HTTPException(status_code=422, detail=f"spu_name is required when creating {item.spu}")
                if not values.get("category_l2_code") and not values.get("category_l2"):
                    raise HTTPException(status_code=422, detail=f"category_l2_code is required when creating {item.spu}")
                row = DimSpu(**values)
                db.add(row)
                created += 1
                action_type = "bulk_create"
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                updated += 1
                action_type = "bulk_update"
            rows.append(row)
            row_actions.append((row, action_type, values))
        await db.flush()
        for row in rows:
            await _enqueue_spu_projection(db, row)
        for row, action_type, values in row_actions:
            await _write_product_center_audit(
                db, _user, action_type=action_type, resource_type="spu",
                resource_id=row.spu, changes=values,
            )
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="bulk SPU save conflicts with existing data") from exc
    asyncio.create_task(trigger_pending_projection_delivery())
    return BulkMutationResponse(created=created, updated=updated, items=[ProductCenterItem.model_validate(row) for row in rows])


@router.get("/api/skus", response_model=ProductCenterListResponse)
async def list_skus(
    keyword: str | None = Query(None),
    spu: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if keyword:
        pattern = f"%{keyword}%"
        filters.append((DimErpSku.sku_key.ilike(pattern)) | (DimErpSku.sku_name.ilike(pattern)))
    if spu:
        filters.append(
            DimErpSku.sku_id.in_(
                select(BridgeSpuSku.sku_id).where(
                    BridgeSpuSku.spu == spu,
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        )
    total = int((await db.execute(select(func.count()).select_from(DimErpSku).where(*filters))).scalar() or 0)
    rows = (await db.execute(select(DimErpSku).where(*filters).order_by(DimErpSku.sku_key).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    sku_ids = [row.sku_id for row in rows]
    bindings = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.sku_id.in_(sku_ids), BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None)))).scalars().all() if sku_ids else []
    binding_by_sku = {row.sku_id: row for row in bindings}
    spu_codes = [row.spu for row in bindings]
    spu_rows = (await db.execute(select(DimSpu).where(DimSpu.spu.in_(spu_codes)))).scalars().all() if spu_codes else []
    spu_by_code = {row.spu: row for row in spu_rows}
    allocations = (await db.execute(
        select(LogisticsBillLineAllocation, LogisticsBill.confirmed_at)
        .join(LogisticsBillLine, LogisticsBillLine.line_id == LogisticsBillLineAllocation.bill_line_id)
        .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
        .where(LogisticsBillLineAllocation.sku_id.in_(sku_ids), LogisticsBill.status == "confirmed")
        .order_by(LogisticsBill.confirmed_at.desc())
    )).all() if sku_ids else []
    actual_logistics: dict[int, float] = {}
    for allocation, _confirmed_at in allocations:
        if allocation.sku_id not in actual_logistics and allocation.allocated_quantity:
            actual_logistics[allocation.sku_id] = float(allocation.allocated_amount / allocation.allocated_quantity)
    items = []
    for row in rows:
        payload = ProductCenterItem.model_validate(row).model_dump()
        binding = binding_by_sku.get(row.sku_id)
        linked_spu = spu_by_code.get(binding.spu) if binding else None
        payload.update({
            "spu": binding.spu if binding else None,
            "logistics_damage_rate": linked_spu.logistics_damage_rate if linked_spu else None,
            "return_loss_rate": linked_spu.return_loss_rate if linked_spu else None,
            "actual_logistics_cost": actual_logistics.get(row.sku_id),
            "actual_storage_cost": None,
            "data_completeness": "complete" if all(value is not None for value in (row.default_purchase_cost, row.expected_logistics_cost, row.expected_storage_cost, linked_spu.logistics_damage_rate if linked_spu else None, linked_spu.return_loss_rate if linked_spu else None)) else "partial",
        })
        items.append(ProductCenterItem(**payload))
    return ProductCenterListResponse(data=items, page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size)


@router.post("/api/skus", response_model=ProductCenterItem, status_code=201)
async def create_sku(body: SkuCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = DimErpSku(**body.model_dump())
    db.add(row)
    try:
        await db.flush()
        await _enqueue_sku_projection(db, row)
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="sku",
            resource_id=str(row.sku_id), changes=body.model_dump(mode="json"),
        )
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
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="sku",
        resource_id=str(row.sku_id), changes=body.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return ProductCenterItem.model_validate(row)


async def _apply_bulk_sku_spu_binding(
    db: AsyncSession, sku: DimErpSku, spu: str | None, effective_from: date | None
) -> None:
    if not spu:
        return
    if await db.get(DimSpu, spu) is None:
        raise HTTPException(status_code=422, detail=f"SPU {spu} does not exist")

    binding = (
        await db.execute(
            select(BridgeSpuSku).where(
                BridgeSpuSku.sku_id == sku.sku_id,
                BridgeSpuSku.effective_to.is_(None),
                BridgeSpuSku.binding_status == "active",
            )
        )
    ).scalars().first()
    if binding is not None and binding.spu == spu:
        return

    starts_on = effective_from or date.today()
    if binding is not None:
        if starts_on <= binding.effective_from:
            raise HTTPException(status_code=422, detail="effective_from must be later than the current SPU binding")
        binding.effective_to = starts_on
        binding.binding_status = "historical"
    db.add(BridgeSpuSku(spu=spu, sku_id=sku.sku_id, effective_from=starts_on))


@router.post("/api/skus/bulk", response_model=BulkMutationResponse)
async def bulk_save_skus(body: SkuBulkRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    supplied_ids = [item.sku_id for item in body.items if item.sku_id is not None]
    supplied_keys = [item.sku_key for item in body.items]
    if len(supplied_ids) != len(set(supplied_ids)) or len(supplied_keys) != len(set(supplied_keys)):
        raise HTTPException(status_code=422, detail="bulk request cannot contain duplicate SKU identifiers")

    created = 0
    updated = 0
    rows: list[DimErpSku] = []
    row_actions: list[tuple[DimErpSku, str, dict]] = []
    try:
        for item in body.items:
            values = item.model_dump(exclude_unset=True)
            sku_id = values.pop("sku_id", None)
            spu = values.pop("spu", None)
            effective_from = values.pop("effective_from", None)
            row = await db.get(DimErpSku, sku_id) if sku_id is not None else None
            if sku_id is not None and row is None:
                raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")
            if row is None and sku_id is None:
                row = (
                    await db.execute(select(DimErpSku).where(DimErpSku.sku_key == item.sku_key))
                ).scalars().first()
            if row is None:
                row = DimErpSku(**values)
                db.add(row)
                await db.flush()
                created += 1
                action_type = "bulk_create"
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                updated += 1
                action_type = "bulk_update"
            await _apply_bulk_sku_spu_binding(db, row, spu, effective_from)
            rows.append(row)
            row_actions.append((row, action_type, {**values, **({"spu": spu} if spu else {})}))
        await db.flush()
        for row in rows:
            await _enqueue_sku_projection(db, row)
        for row, action_type, values in row_actions:
            await _write_product_center_audit(
                db, _user, action_type=action_type, resource_type="sku",
                resource_id=str(row.sku_id), changes=values,
            )
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="bulk SKU save conflicts with existing data") from exc
    asyncio.create_task(trigger_pending_projection_delivery())
    return BulkMutationResponse(created=created, updated=updated, items=[ProductCenterItem.model_validate(row) for row in rows])


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
        if current_binding is not None:
            await _write_product_center_audit(
                db,
                current_user,
                action_type="update",
                resource_type="spu_sku_binding",
                resource_id=f"{current_binding.spu}:{current_binding.sku_id}",
                changes={
                    "effective_from": current_binding.effective_from,
                    "effective_to": body.effective_from,
                    "binding_status": "historical",
                },
            )
        await _write_product_center_audit(
            db,
            current_user,
            action_type="create",
            resource_type="spu_sku_binding",
            resource_id=f"{row.spu}:{row.sku_id}",
            changes={
                "effective_from": row.effective_from,
                "effective_to": row.effective_to,
                "binding_status": row.binding_status,
            },
        )
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SKU binding conflicts with an active assignment") from exc
    return ProductCenterBindingResponse.model_validate(row)


@router.get("/api/purchase-orders")
async def list_purchase_orders(status: str | None = Query(None), keyword: str | None = Query(None), db: AsyncSession = Depends(get_async_db)):
    statement = select(POHeader).order_by(POHeader.po_date.desc(), POHeader.po_id.desc())
    if status:
        statement = statement.where(POHeader.status == status)
    if keyword:
        statement = statement.where(POHeader.po_id.ilike(f"%{keyword}%"))
    rows = (await db.execute(statement.limit(500))).scalars().all()
    po_ids = [row.po_id for row in rows]
    if not po_ids:
        return []
    warehouse_rows = (await db.execute(
        select(GRNHeader.po_id, GRNHeader.warehouse)
        .where(GRNHeader.po_id.in_(po_ids), GRNHeader.warehouse.is_not(None))
        .distinct()
    )).all()
    warehouses_by_po: dict[str, list[str]] = {}
    for related_po_id, warehouse in warehouse_rows:
        warehouses_by_po.setdefault(related_po_id, []).append(warehouse)
    line_rows = (await db.execute(
        select(
            POLine.po_id,
            func.count(POLine.po_line_id),
            func.coalesce(func.sum(POLine.qty_ordered), 0),
            func.coalesce(func.sum(POLine.qty_received), 0),
        )
        .where(POLine.po_id.in_(po_ids))
        .group_by(POLine.po_id)
    )).all()
    line_totals = {po_id: (count, ordered, received) for po_id, count, ordered, received in line_rows}
    return [
        {
            "po_id": row.po_id,
            "vendor_code": row.vendor_code,
            "po_date": row.po_date,
            "expected_date": row.expected_date,
            "currency": row.currency,
            "total_amt": row.total_amt,
            "status": row.status,
            "warehouses": warehouses_by_po.get(row.po_id, []),
            "warehouse": ", ".join(warehouses_by_po.get(row.po_id, [])),
            "sku_count": int(line_totals.get(row.po_id, (0, 0, 0))[0] or 0),
            "qty_ordered": float(line_totals.get(row.po_id, (0, 0, 0))[1] or 0),
            "qty_received": float(line_totals.get(row.po_id, (0, 0, 0))[2] or 0),
            "po_no": row.po_id,
            "received_qty": float(line_totals.get(row.po_id, (0, 0, 0))[2] or 0),
        }
        for row in rows
    ]


@router.get("/api/purchase-orders/{po_id}/lines")
async def list_purchase_order_lines(po_id: str, db: AsyncSession = Depends(get_async_db)):
    rows = (await db.execute(select(POLine).where(POLine.po_id == po_id).order_by(POLine.line_number))).scalars().all()
    source_keys = {row.platform_sku for row in rows if row.platform_sku}
    canonical_sku_ids: dict[str, int] = {}
    if source_keys:
        direct_rows = (
            await db.execute(
                select(DimErpSku.sku_key, DimErpSku.sku_id).where(
                    DimErpSku.sku_key.in_(source_keys)
                )
            )
        ).all()
        canonical_sku_ids.update({sku_key: sku_id for sku_key, sku_id in direct_rows})
        alias_rows = (
            await db.execute(
                select(BridgeErpSkuKey.source_key, BridgeErpSkuKey.sku_id).where(
                    BridgeErpSkuKey.source_key.in_(source_keys),
                    BridgeErpSkuKey.active.is_(True),
                    BridgeErpSkuKey.effective_to.is_(None),
                )
            )
        ).all()
        alias_candidates: dict[str, set[int]] = {}
        for source_key, sku_id in alias_rows:
            alias_candidates.setdefault(source_key, set()).add(sku_id)
        for source_key, sku_ids in alias_candidates.items():
            if source_key not in canonical_sku_ids and len(sku_ids) == 1:
                canonical_sku_ids[source_key] = next(iter(sku_ids))
    return [
        {
            "po_line_id": row.po_line_id,
            "po_id": row.po_id,
            "line_number": row.line_number,
            "platform_sku": row.platform_sku,
            "sku_id": canonical_sku_ids.get(row.platform_sku),
            "product_title": row.product_title,
            "qty_ordered": row.qty_ordered,
            "qty_received": row.qty_received,
            "unit_price": row.unit_price,
            "currency": row.currency,
            "line_amt": row.line_amt,
            "purchase_cost_source": row.purchase_cost_source,
            "purchase_cost_confirmed_at": row.purchase_cost_confirmed_at,
        }
        for row in rows
    ]


@router.patch("/api/purchase-orders/{po_id}/lines/{po_line_id}/purchase-cost")
async def supplement_purchase_order_line_cost(po_id: str, po_line_id: int, body: PurchaseOrderLineCostSupplementRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = (await db.execute(select(POLine).where(POLine.po_id == po_id, POLine.po_line_id == po_line_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="purchase order line not found")
    row.unit_price = body.unit_price
    row.line_amt = float(body.unit_price) * float(row.qty_ordered or 0)
    row.currency = "CNY"
    row.purchase_cost_source = body.purchase_cost_source
    row.purchase_cost_confirmed_at = datetime.now(timezone.utc)
    canonical_sku = (
        await db.execute(
            select(DimErpSku)
            .outerjoin(BridgeErpSkuKey, BridgeErpSkuKey.sku_id == DimErpSku.sku_id)
            .where(
                (DimErpSku.sku_key == row.platform_sku)
                | (
                    (BridgeErpSkuKey.source_key == row.platform_sku)
                    & BridgeErpSkuKey.active.is_(True)
                    & BridgeErpSkuKey.effective_to.is_(None)
                )
            )
        )
    ).scalars().first()
    if canonical_sku is not None:
        canonical_sku.default_purchase_cost = body.unit_price
        canonical_sku.purchase_cost_currency = row.currency or canonical_sku.purchase_cost_currency
        canonical_sku.purchase_cost_source = "purchase_order"
        canonical_sku.purchase_cost_confirmed_at = row.purchase_cost_confirmed_at
        await _enqueue_sku_projection(db, canonical_sku)
    await _write_product_center_audit(
        db, _user, action_type="supplement_purchase_cost", resource_type="purchase_order_line",
        resource_id=f"{po_id}:{po_line_id}", changes={
            "po_id": po_id,
            "po_line_id": po_line_id,
            "purchase_cost_source": body.purchase_cost_source,
            "currency": "CNY",
        },
    )
    await db.commit()
    await db.refresh(row)
    return {"po_line_id": row.po_line_id, "unit_price": row.unit_price, "currency": row.currency, "line_amt": row.line_amt, "purchase_cost_source": row.purchase_cost_source, "purchase_cost_confirmed_at": row.purchase_cost_confirmed_at}


@router.get("/api/purchase-orders/{po_id}")
async def get_purchase_order(po_id: str, db: AsyncSession = Depends(get_async_db)):
    row = await db.get(POHeader, po_id)
    if row is None:
        raise HTTPException(status_code=404, detail="purchase order not found")
    return {"po_id": row.po_id, "vendor_code": row.vendor_code, "po_date": row.po_date, "expected_date": row.expected_date, "currency": row.currency, "total_amt": row.total_amt, "status": row.status}


def _serialize_provider_rule(row: LogisticsProviderRule) -> dict:
    return {"rule_id": row.rule_id, "logistics_provider": row.logistics_provider, "warehouse_code": row.warehouse_code, "transport_type": row.transport_type, "cargo_class": row.cargo_class, "is_sensitive": row.is_sensitive, "is_default": row.is_default, "billing_basis": row.billing_basis, "billing_unit": row.billing_unit, "freight_unit_rate": float(row.freight_unit_rate) if row.freight_unit_rate is not None else None, "sensitive_surcharge_mode": row.sensitive_surcharge_mode, "sensitive_surcharge_rate": float(row.sensitive_surcharge_rate) if row.sensitive_surcharge_rate is not None else None, "currency": row.currency, "effective_from": row.effective_from, "effective_to": row.effective_to, "status": row.status, "source": row.source, "version": row.version, "notes": row.notes}


def _same_nullable_scope(column, value):
    return column.is_(None) if value is None else column == value


async def _ensure_unambiguous_default_provider_rule(
    db: AsyncSession,
    values: dict,
    *,
    excluding_rule_id: int | None = None,
) -> None:
    """Reject overlapping active defaults for a tariff scope before persistence."""
    if not values.get("is_default") or values.get("status") != "active":
        return
    new_effective_to = values.get("effective_to") or date.max
    statement = select(LogisticsProviderRule).where(
        LogisticsProviderRule.is_default.is_(True),
        LogisticsProviderRule.status == "active",
        _same_nullable_scope(LogisticsProviderRule.warehouse_code, values.get("warehouse_code")),
        _same_nullable_scope(LogisticsProviderRule.transport_type, values.get("transport_type")),
        _same_nullable_scope(LogisticsProviderRule.cargo_class, values.get("cargo_class")),
        LogisticsProviderRule.is_sensitive == values.get("is_sensitive", False),
    ).with_for_update()
    if excluding_rule_id is not None:
        statement = statement.where(LogisticsProviderRule.rule_id != excluding_rule_id)
    existing_rules = (await db.execute(statement)).scalars().all()
    for existing_rule in existing_rules:
        existing_effective_to = existing_rule.effective_to or date.max
        if (
            existing_rule.effective_from <= new_effective_to
            and values["effective_from"] <= existing_effective_to
        ):
            raise HTTPException(
                status_code=409,
                detail="only one default logistics provider rule may be active for this scope",
            )


@router.get("/api/logistics-provider-rules")
async def list_logistics_provider_rules(provider: str | None = Query(None), warehouse_code: str | None = Query(None), transport_type: str | None = Query(None), as_of: date | None = Query(None), db: AsyncSession = Depends(get_async_db)):
    filters = [LogisticsProviderRule.status == "active"]
    if provider:
        filters.append(LogisticsProviderRule.logistics_provider == provider)
    if warehouse_code:
        filters.append(
            (LogisticsProviderRule.warehouse_code == warehouse_code)
            | LogisticsProviderRule.warehouse_code.is_(None)
        )
    if transport_type:
        filters.append(
            (LogisticsProviderRule.transport_type == transport_type)
            | LogisticsProviderRule.transport_type.is_(None)
        )
    when = as_of or date.today()
    filters.extend([LogisticsProviderRule.effective_from <= when, (LogisticsProviderRule.effective_to.is_(None)) | (LogisticsProviderRule.effective_to >= when)])
    rows = (await db.execute(select(LogisticsProviderRule).where(*filters).order_by(LogisticsProviderRule.effective_from.desc()))).scalars().all()
    return [_serialize_provider_rule(row) for row in rows]


@router.post("/api/logistics-provider-rules", status_code=201)
async def create_logistics_provider_rule(body: LogisticsProviderRuleCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    if body.warehouse_code and await db.get(DimWarehouse, body.warehouse_code) is None:
        raise HTTPException(status_code=422, detail="warehouse not found")
    await _ensure_unambiguous_default_provider_rule(db, body.model_dump())
    row = LogisticsProviderRule(**body.model_dump(), currency="CNY")
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="logistics_provider_rule",
            resource_id=str(row.rule_id), changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="logistics provider rule already exists") from exc
    return _serialize_provider_rule(row)


@router.patch("/api/logistics-provider-rules/{rule_id}")
async def update_logistics_provider_rule(rule_id: int, body: LogisticsProviderRuleUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(LogisticsProviderRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="logistics provider rule not found")
    values = body.model_dump(exclude_unset=True)
    if values.get("warehouse_code") and await db.get(DimWarehouse, values["warehouse_code"]) is None:
        raise HTTPException(status_code=422, detail="warehouse not found")
    candidate = {
        field: getattr(row, field)
        for field in (
            "warehouse_code", "transport_type", "cargo_class", "is_sensitive",
            "is_default", "effective_from", "effective_to", "status",
        )
    }
    candidate.update(values)
    await _ensure_unambiguous_default_provider_rule(
        db, candidate, excluding_rule_id=row.rule_id
    )
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="logistics_provider_rule",
        resource_id=str(row.rule_id), changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return _serialize_provider_rule(row)


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
    await _write_product_center_audit(
        db, _user, action_type="create", resource_type="cost_assumption_profile",
        resource_id=str(row.profile_id), changes=body.model_dump(mode="json"),
    )
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
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="cost_assumption_profile",
        resource_id=str(row.profile_id), changes=body.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    asyncio.create_task(trigger_pending_projection_delivery())
    return {"profile_id": row.profile_id, "active": row.active, "updated_at": row.updated_at}


def _serialize_bill(bill: LogisticsBill, lines: list[LogisticsBillLine] | None = None, purchase_orders: list[LogisticsBillPurchaseOrder] | None = None, allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] | None = None) -> dict:
    payload = {
        "bill_id": bill.bill_id,
        "bill_no": bill.bill_no,
        "logistics_provider": bill.logistics_provider,
        "bill_date": bill.bill_date,
        "transport_type": bill.transport_type,
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
                "po_id": line.po_id,
                "warehouse_code": line.warehouse_code,
                "billing_basis": line.billing_basis,
                "billing_unit": line.billing_unit,
                "billing_unit_rate": float(line.billing_unit_rate) if line.billing_unit_rate is not None else None,
                "is_sensitive": line.is_sensitive,
                "sensitive_surcharge": float(line.sensitive_surcharge or 0),
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
                "allocations": [
                    {
                        "sku_id": allocation.sku_id,
                        "po_id": allocation.po_id,
                        "shipped_qty": float(allocation.allocated_quantity or 0),
                        "allocation_ratio": float(allocation.allocation_ratio or 0),
                        "allocated_amount": float(allocation.allocated_amount or 0),
                        "allocation_basis": allocation.allocation_basis,
                    }
                    for allocation in (allocations_by_line or {}).get(line.line_id, [])
                ],
            }
            for line in lines
        ]
    if purchase_orders is not None:
        payload["purchase_orders"] = [row.po_id for row in purchase_orders]
    return payload


@router.get("/api/product-warehouses")
async def list_product_warehouses(include_inactive: bool = Query(False), db: AsyncSession = Depends(get_async_db)):
    statement = select(DimWarehouse).order_by(DimWarehouse.country_code, DimWarehouse.warehouse_code)
    if not include_inactive:
        statement = statement.where(DimWarehouse.status == "active")
    rows = (await db.execute(statement)).scalars().all()
    return [{"warehouse_code": row.warehouse_code, "warehouse_name": row.warehouse_name, "country_code": row.country_code, "country_name": row.country_name, "region": row.region, "status": row.status} for row in rows]


def _serialize_storage_rule(row: WarehouseStorageRule) -> dict:
    return {"rule_id": row.rule_id, "warehouse_code": row.warehouse_code, "billing_basis": row.billing_basis,
            "billing_unit": row.billing_unit, "unit_rate_cny": float(row.unit_rate_cny),
            "effective_from": row.effective_from,
            "effective_to": row.effective_to, "status": row.status, "source": row.source,
            "version": row.version, "notes": row.notes}


@router.get("/api/warehouse-storage-rules")
async def list_warehouse_storage_rules(warehouse_code: str | None = Query(None), include_inactive: bool = Query(False), db: AsyncSession = Depends(get_async_db)):
    filters = []
    if warehouse_code:
        filters.append(WarehouseStorageRule.warehouse_code == warehouse_code)
    if not include_inactive:
        filters.append(WarehouseStorageRule.status == "active")
    rows = (await db.execute(select(WarehouseStorageRule).where(*filters).order_by(WarehouseStorageRule.warehouse_code, WarehouseStorageRule.effective_from.desc()))).scalars().all()
    return [_serialize_storage_rule(row) for row in rows]


@router.post("/api/warehouse-storage-rules", status_code=201)
async def create_warehouse_storage_rule(body: WarehouseStorageRuleCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_platform_fee_editor)):
    warehouse = (
        await db.execute(
            select(DimWarehouse)
            .where(DimWarehouse.warehouse_code == body.warehouse_code)
            .with_for_update()
        )
    ).scalars().first()
    if warehouse is None:
        raise HTTPException(status_code=422, detail="warehouse not found")
    if body.status == "active":
        active_rules = (
            await db.execute(
                select(WarehouseStorageRule)
                .where(
                    WarehouseStorageRule.warehouse_code == body.warehouse_code,
                    WarehouseStorageRule.status == "active",
                )
                .with_for_update()
            )
        ).scalars().all()
        new_effective_to = body.effective_to or date.max
        for existing_rule in active_rules:
            existing_effective_to = existing_rule.effective_to or date.max
            overlaps = (
                existing_rule.effective_from <= new_effective_to
                and body.effective_from <= existing_effective_to
            )
            if not overlaps:
                continue
            if existing_rule.effective_to is not None:
                raise HTTPException(status_code=409, detail="storage rule effective window overlaps an active historical rule")
            if body.effective_from <= existing_rule.effective_from:
                raise HTTPException(status_code=409, detail="new storage rule effective_from must be later than the current rule")
            current_rule = existing_rule
            current_rule.effective_to = body.effective_from - timedelta(days=1)
    row = WarehouseStorageRule(**body.model_dump(), billing_basis="volume", billing_unit="CNY/CBM/month")
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="warehouse_storage_rule",
            resource_id=str(row.rule_id), changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="active storage rule already exists") from exc
    return _serialize_storage_rule(row)


@router.patch("/api/warehouse-storage-rules/{rule_id}")
async def update_warehouse_storage_rule(rule_id: int, body: WarehouseStorageRuleUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_platform_fee_editor)):
    row = await db.get(WarehouseStorageRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="warehouse storage rule not found")
    values = body.model_dump(exclude_unset=True)
    if values.get("status") == "active" and row.status != "active":
        raise HTTPException(
            status_code=409,
            detail="inactive storage rules cannot be reactivated; create a new storage rule version",
        )
    material_fields = {"unit_rate_cny", "effective_from", "effective_to"}
    if material_fields & values.keys():
        if row.status != "active":
            raise HTTPException(status_code=409, detail="inactive storage rules cannot be versioned; create a new storage rule")
        next_effective_from = values.get("effective_from") or date.today()
        if next_effective_from <= row.effective_from:
            next_effective_from = date.today()
        if next_effective_from <= row.effective_from:
            raise HTTPException(status_code=409, detail="new storage rule effective_from must be later than the current rule")
        row.effective_to = next_effective_from - timedelta(days=1)
        next_rule = WarehouseStorageRule(
            warehouse_code=row.warehouse_code,
            billing_basis="volume",
            billing_unit="CNY/CBM/month",
            unit_rate_cny=values.get("unit_rate_cny", row.unit_rate_cny),
            effective_from=next_effective_from,
            effective_to=values.get("effective_to"),
            status="active",
            source=values.get("source", row.source),
            version=values.get("version") or f"{row.version or 'v1'}-next",
            notes=values.get("notes", row.notes),
        )
        db.add(next_rule)
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="storage_rule_versioned", resource_type="warehouse_storage_rule",
            resource_id=str(next_rule.rule_id), changes={"previous_rule_id": row.rule_id, **values},
        )
        await db.commit()
        await db.refresh(next_rule)
        return _serialize_storage_rule(next_rule)
    for key, value in values.items():
        setattr(row, key, value)
    try:
        await _write_product_center_audit(
            db, _user, action_type="update", resource_type="warehouse_storage_rule",
            resource_id=str(row.rule_id), changes=body.model_dump(mode="json", exclude_unset=True),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="active storage rule already exists") from exc
    return _serialize_storage_rule(row)


@router.post("/api/product-warehouses", status_code=201)
async def create_product_warehouse(body: ProductWarehouseCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = DimWarehouse(**body.model_dump())
    db.add(row)
    try:
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="warehouse",
            resource_id=row.warehouse_code, changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="warehouse code already exists") from exc
    return {"warehouse_code": row.warehouse_code, "warehouse_name": row.warehouse_name, "country_code": row.country_code, "country_name": row.country_name, "region": row.region, "status": row.status}


@router.patch("/api/product-warehouses/{warehouse_code}")
async def update_product_warehouse(warehouse_code: str, body: ProductWarehouseUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(DimWarehouse, warehouse_code)
    if row is None:
        raise HTTPException(status_code=404, detail="warehouse not found")
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="warehouse",
        resource_id=row.warehouse_code, changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return {"warehouse_code": row.warehouse_code, "warehouse_name": row.warehouse_name, "country_code": row.country_code, "country_name": row.country_name, "region": row.region, "status": row.status}


@router.patch("/api/platforms/{platform_code}/fee-rate")
async def update_platform_fee_rate(platform_code: str, body: PlatformFeeRateUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_platform_fee_editor)):
    row = await db.get(DimPlatform, platform_code)
    if row is None:
        raise HTTPException(status_code=404, detail="platform not found")
    if row.platform_role != "sales":
        raise HTTPException(status_code=409, detail="platform fee rates can only be maintained for sales platforms")
    row.default_fee_rate = body.default_fee_rate
    row.fee_rate_effective_from = body.fee_rate_effective_from
    row.fee_rate_source = body.fee_rate_source
    row.fee_rate_version = body.fee_rate_version
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="platform_fee_rate",
        resource_id=row.platform_code, changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return {"platform_code": row.platform_code, "default_fee_rate": row.default_fee_rate, "fee_rate_effective_from": row.fee_rate_effective_from, "fee_rate_source": row.fee_rate_source, "fee_rate_version": row.fee_rate_version}


@router.get("/api/logistics-bills")
async def list_logistics_bills(status: str | None = Query(None), db: AsyncSession = Depends(get_async_db)):
    statement = select(LogisticsBill).order_by(LogisticsBill.bill_date.desc(), LogisticsBill.bill_id.desc())
    if status:
        statement = statement.where(LogisticsBill.status == status)
    rows = (await db.execute(statement)).scalars().all()
    return [_serialize_bill(row) for row in rows]


@router.get("/api/logistics-batches")
async def list_logistics_batches(status: str | None = Query(None), db: AsyncSession = Depends(get_async_db)):
    """Current product-center name for logistics bill batches."""
    return await list_logistics_bills(status=status, db=db)


@router.post("/api/logistics-bills", status_code=201)
async def create_logistics_bill(body: LogisticsBillCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = LogisticsBill(**body.model_dump(), status="draft")
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="logistics_bill",
            resource_id=str(row.bill_id), changes={"bill_no": row.bill_no, "status": row.status},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="logistics bill number already exists") from exc
    return _serialize_bill(row, [])


@router.post("/api/logistics-batches", status_code=201)
async def create_logistics_batch(body: LogisticsBillCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    return await create_logistics_bill(body=body, db=db, _user=_user)


@router.get("/api/logistics-bills/{bill_id}")
async def get_logistics_bill(bill_id: int, db: AsyncSession = Depends(get_async_db)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lines = (await db.execute(select(LogisticsBillLine).where(LogisticsBillLine.bill_id == bill_id).order_by(LogisticsBillLine.line_no))).scalars().all()
    purchase_orders = (await db.execute(select(LogisticsBillPurchaseOrder).where(LogisticsBillPurchaseOrder.bill_id == bill_id))).scalars().all()
    allocations = (await db.execute(select(LogisticsBillLineAllocation).where(LogisticsBillLineAllocation.bill_line_id.in_([line.line_id for line in lines])))).scalars().all() if lines else []
    allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] = {}
    for allocation in allocations:
        allocations_by_line.setdefault(allocation.bill_line_id, []).append(allocation)
    return _serialize_bill(bill, lines, purchase_orders, allocations_by_line)


@router.get("/api/logistics-batches/{bill_id}")
async def get_logistics_batch(bill_id: int, db: AsyncSession = Depends(get_async_db)):
    return await get_logistics_bill(bill_id=bill_id, db=db)


@router.put("/api/logistics-bills/{bill_id}/purchase-orders")
async def replace_logistics_bill_purchase_orders(bill_id: int, body: LogisticsBillPurchaseOrdersReplaceRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        rows = await service.replace_bill_purchase_orders(bill, body.po_ids)
        await _write_product_center_audit(
            db, _user, action_type="replace_purchase_orders", resource_type="logistics_bill",
            resource_id=str(bill_id), changes={"purchase_order_ids": body.po_ids},
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [{"id": row.id, "bill_id": row.bill_id, "po_id": row.po_id} for row in rows]


@router.put("/api/logistics-batches/{bill_id}/purchase-orders")
async def replace_logistics_batch_purchase_orders(bill_id: int, body: LogisticsBillPurchaseOrdersReplaceRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    return await replace_logistics_bill_purchase_orders(bill_id=bill_id, body=body, db=db, _user=_user)


@router.patch("/api/logistics-bills/{bill_id}")
async def update_logistics_bill(bill_id: int, body: LogisticsBillUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if bill.status != "draft":
        raise HTTPException(status_code=409, detail="only draft logistics bills can be edited")
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(bill, key, value)
    await _write_product_center_audit(
        db, _user, action_type="update", resource_type="logistics_bill",
        resource_id=str(bill_id), changes=values,
    )
    await db.commit()
    return _serialize_bill(bill)


@router.patch("/api/logistics-batches/{bill_id}")
async def update_logistics_batch(bill_id: int, body: LogisticsBillUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    return await update_logistics_bill(bill_id=bill_id, body=body, db=db, _user=_user)


@router.put("/api/logistics-bills/{bill_id}/lines")
async def replace_logistics_bill_lines(bill_id: int, body: LogisticsBillLinesReplaceRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        lines = await service.replace_bill_lines(bill, [line.model_dump(exclude_unset=True) for line in body.lines])
        await _write_product_center_audit(
            db, _user, action_type="replace_lines", resource_type="logistics_bill",
            resource_id=str(bill_id), changes={"line_count": len(lines), "line_ids": [line.line_id for line in lines]},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    allocations = (await db.execute(select(LogisticsBillLineAllocation).where(LogisticsBillLineAllocation.bill_line_id.in_([line.line_id for line in lines])))).scalars().all()
    allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] = {}
    for allocation in allocations:
        allocations_by_line.setdefault(allocation.bill_line_id, []).append(allocation)
    return _serialize_bill(bill, lines, allocations_by_line=allocations_by_line)


@router.put("/api/logistics-batches/{bill_id}/lines")
async def replace_logistics_batch_lines(bill_id: int, body: LogisticsBillLinesReplaceRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    return await replace_logistics_bill_lines(bill_id=bill_id, body=body, db=db, _user=_user)


@router.post("/api/logistics-bills/{bill_id}/confirm")
async def confirm_logistics_bill(bill_id: int, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.confirm_bill(bill=await service.get_bill_or_raise(bill_id), user_id=getattr(current_user, "user_id", None))
        await FeishuProjectionService(db).enqueue_full_refresh("logistics_bill_confirmed")
        line_rows = (await db.execute(select(LogisticsBillLine).where(LogisticsBillLine.bill_id == bill_id))).scalars().all()
        platform_sku_ids = {line.sku_id for line in line_rows if line.sku_id is not None}
        allocation_rows = (await db.execute(select(LogisticsBillLineAllocation).where(LogisticsBillLineAllocation.bill_line_id.in_([line.line_id for line in line_rows])))).scalars().all() if line_rows else []
        platform_sku_ids.update(row.sku_id for row in allocation_rows)
        if platform_sku_ids:
            site_profiles = (await db.execute(select(SkuOperatingProfile).where(SkuOperatingProfile.sku_id.in_(platform_sku_ids), SkuOperatingProfile.status == "active", SkuOperatingProfile.effective_to.is_(None)))).scalars().all()
            for profile in site_profiles:
                await _enqueue_platform_sku_profit_projection(db, profile)
        await _write_product_center_audit(
            db, current_user, action_type="confirm", resource_type="logistics_bill",
            resource_id=str(bill_id), changes={"bill_no": bill.bill_no, "status": bill.status},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except BillTotalMismatchError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill)


@router.post("/api/logistics-batches/{bill_id}/confirm")
async def confirm_logistics_batch(bill_id: int, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    return await confirm_logistics_bill(bill_id=bill_id, db=db, current_user=current_user)


@router.post("/api/logistics-bills/{bill_id}/void")
async def void_logistics_bill(bill_id: int, body: LogisticsBillVoidRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        sku_ids = [sku_id for sku_id, in (await db.execute(select(LogisticsBillLine.sku_id).where(LogisticsBillLine.bill_id == bill_id, LogisticsBillLine.sku_id.is_not(None)))).all()]
        sku_ids.extend(sku_id for sku_id, in (await db.execute(select(LogisticsBillLineAllocation.sku_id).join(LogisticsBillLine, LogisticsBillLine.line_id == LogisticsBillLineAllocation.bill_line_id).where(LogisticsBillLine.bill_id == bill_id))).all())
        bill = await service.void_bill(bill, getattr(current_user, "user_id", None), body.reason)
        for sku_id in sku_ids:
            sku = await db.get(DimErpSku, sku_id)
            if sku is not None:
                await _enqueue_sku_projection(db, sku)
        await _write_product_center_audit(
            db, current_user, action_type="void", resource_type="logistics_bill",
            resource_id=str(bill_id), changes={"bill_no": bill.bill_no, "status": bill.status},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill)


@router.post("/api/logistics-batches/{bill_id}/void")
async def void_logistics_batch(bill_id: int, body: LogisticsBillVoidRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(_require_editor)):
    return await void_logistics_bill(bill_id=bill_id, body=body, db=db, current_user=current_user)


def _serialize_operating_profile(row: SkuOperatingProfile, *, sku=None, spu=None, estimate=None) -> dict:
    payload = {
        "profile_id": row.profile_id,
        "sku_id": row.sku_id,
        "platform_code": row.platform_code,
        "warehouse_code": row.warehouse_code,
        "transport_type": row.transport_type,
        "warehouse_name": row.warehouse_name,
        "selling_price": row.selling_price,
        "default_coupon_amount": row.default_coupon_amount,
        "platform_fee_rate": row.platform_fee_rate,
        "expected_logistics_cost": row.expected_logistics_cost,
        "expected_storage_cost": row.expected_storage_cost,
        "status": row.status,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "sku_key": sku.sku_key if sku else None,
        "sku_name": sku.sku_name if sku else None,
        "spu": spu.spu if spu else None,
        "logistics_damage_rate": spu.logistics_damage_rate if spu else None,
        "return_loss_rate": spu.return_loss_rate if spu else None,
        "estimated_contribution_profit": estimate.estimated_contribution_profit if estimate else None,
        "estimated_margin_rate": estimate.estimated_margin_rate if estimate else None,
        "purchase_cost": estimate.purchase_cost if estimate else None,
        "actual_logistics_cost": estimate.logistics_cost if estimate and estimate.logistics_cost_source == "confirmed_logistics_bill" else None,
        "actual_storage_cost": None,
        "cost_completeness": estimate.cost_completeness if estimate else None,
        "confidence_level": estimate.confidence_level if estimate else None,
        "latest_estimate_as_of": estimate.estimate_as_of if estimate else None,
        "latest_estimate_id": estimate.estimate_id if estimate else None,
    }
    return {key: (float(value) if hasattr(value, "as_tuple") else value) for key, value in payload.items()}


@router.get("/api/sku-operating-dimensions", response_model=SkuOperatingDimensionsResponse)
async def list_sku_operating_dimensions(db: AsyncSession = Depends(get_async_db)):
    platforms = (await db.execute(select(DimPlatform).where(DimPlatform.is_active.is_(True), DimPlatform.platform_role == "sales").order_by(DimPlatform.platform_code))).scalars().all()
    warehouses = (await db.execute(select(DimWarehouse).where(DimWarehouse.status == "active").order_by(DimWarehouse.country_code, DimWarehouse.warehouse_code))).scalars().all()
    spus = (await db.execute(select(DimSpu.spu).where(DimSpu.active.is_(True)).order_by(DimSpu.spu))).scalars().all()
    skus = (await db.execute(select(DimErpSku.sku_id, DimErpSku.sku_key, DimErpSku.sku_name).where(DimErpSku.status == "active").order_by(DimErpSku.sku_key))).all()
    sku_ids = [row.sku_id for row in skus]
    bindings = (await db.execute(select(BridgeSpuSku.sku_id, BridgeSpuSku.spu).where(
        BridgeSpuSku.sku_id.in_(sku_ids),
        BridgeSpuSku.binding_status == "active",
        BridgeSpuSku.effective_to.is_(None),
    ))).all() if sku_ids else []
    spu_by_sku = {row.sku_id: row.spu for row in bindings}
    return {
        "platforms": [{"platform_code": row.platform_code, "name": row.name,
                       "default_fee_rate": row.default_fee_rate, "fee_rate_effective_from": row.fee_rate_effective_from,
                       "fee_rate_source": row.fee_rate_source, "fee_rate_version": row.fee_rate_version} for row in platforms],
        "spus": list(spus),
        "skus": [{"sku_id": row.sku_id, "sku_key": row.sku_key, "sku_name": row.sku_name,
                  "spu": spu_by_sku.get(row.sku_id)} for row in skus],
        "warehouses": [{"warehouse_code": row.warehouse_code, "warehouse_name": row.warehouse_name, "country_code": row.country_code, "country_name": row.country_name} for row in warehouses],
    }


@router.get("/api/platform-sku-profit/candidates", response_model=PlatformSkuProfitCandidatePageResponse)
async def list_platform_sku_profit_candidates(
    platform_code: str = Query(..., min_length=1),
    warehouse_code: str = Query(..., min_length=1),
    transport_type: str = Query(..., pattern=r"^(sea|air|rail)$"),
    spu: str | None = Query(None),
    sku_id: int | None = Query(None, gt=0),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    platform = await db.get(DimPlatform, platform_code)
    warehouse = await db.get(DimWarehouse, warehouse_code)
    if platform is None or not platform.is_active or platform.platform_role != "sales":
        raise HTTPException(status_code=422, detail="sales platform not found or inactive")
    if warehouse is None or warehouse.status != "active":
        raise HTTPException(status_code=422, detail="warehouse not found or inactive")
    filters = [DimErpSku.status == "active"]
    if sku_id is not None:
        filters.append(DimErpSku.sku_id == sku_id)
    if keyword:
        token = f"%{keyword}%"
        filters.append((DimErpSku.sku_key.ilike(token)) | (DimErpSku.sku_name.ilike(token)))
    if spu:
        filters.append(DimErpSku.sku_id.in_(select(BridgeSpuSku.sku_id).where(BridgeSpuSku.spu == spu, BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None))))
    total = int((await db.execute(select(func.count()).select_from(DimErpSku).where(*filters))).scalar() or 0)
    sku_rows = (await db.execute(select(DimErpSku).where(*filters).order_by(DimErpSku.sku_key).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    ids = [row.sku_id for row in sku_rows]
    bindings = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.sku_id.in_(ids), BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None)))).scalars().all() if ids else []
    binding_by_sku = {row.sku_id: row.spu for row in bindings}
    spus = (await db.execute(select(DimSpu).where(DimSpu.spu.in_(set(binding_by_sku.values()))))).scalars().all() if binding_by_sku else []
    spu_by_code = {row.spu: row for row in spus}
    profiles = (await db.execute(select(SkuOperatingProfile).where(SkuOperatingProfile.sku_id.in_(ids), SkuOperatingProfile.platform_code == platform_code, SkuOperatingProfile.warehouse_code == warehouse_code, SkuOperatingProfile.status == "active", SkuOperatingProfile.effective_to.is_(None)))).scalars().all() if ids else []
    profile_by_sku = {row.sku_id: row for row in profiles}
    finance = ProductFinanceService(db)
    cost_inputs_by_sku = await finance.prefetch_platform_sku_profit_inputs(
        sku_rows, warehouse_code, transport_type
    )
    items = []
    for row in sku_rows:
        profile = profile_by_sku.get(row.sku_id)
        assigned_spu = binding_by_sku.get(row.sku_id)
        assigned = spu_by_code.get(assigned_spu) if assigned_spu else None
        cost_inputs = cost_inputs_by_sku[row.sku_id]
        purchase_cost = cost_inputs["purchase_cost"] or row.default_purchase_cost
        reference_logistics = cost_inputs["reference_logistics_cost"]
        reference_storage = cost_inputs["reference_storage_cost"]
        actual_logistics = cost_inputs["actual_logistics_cost"]
        expected_selling_price = profile.expected_selling_price if profile else row.reference_selling_price
        seller_coupon_amount = profile.seller_coupon_amount if profile else 0
        expected_ad_rate = profile.expected_ad_rate if profile else 0
        missing_reasons: list[str] = []
        if reference_logistics is None:
            if cost_inputs["reference_logistics_ambiguous"]:
                missing_reasons.append("ambiguous_logistics_rule")
            elif (
                cost_inputs["reference_logistics_rule"] is None
                or cost_inputs["reference_logistics_rule"].freight_unit_rate is None
            ):
                missing_reasons.append("missing_logistics_rule")
            elif cost_inputs["reference_logistics_rule"].billing_basis == "weight" and row.weight_kg is None:
                missing_reasons.append("missing_sku_weight")
            else:
                missing_reasons.append("missing_sku_volume")
        if reference_storage is None:
            if cost_inputs["reference_storage_rule"] is None:
                missing_reasons.append("missing_storage_rule")
            elif row.turnover_class is None:
                missing_reasons.append("missing_turnover_class")
            else:
                missing_reasons.append("missing_sku_volume")
        preview = build_platform_profit_preview(
            expected_selling_price=expected_selling_price,
            competitor_price=profile.competitor_price if profile else None,
            seller_coupon_amount=seller_coupon_amount,
            purchase_cost=purchase_cost,
            expected_logistics_cost=reference_logistics,
            expected_storage_cost=reference_storage,
            actual_logistics_cost=actual_logistics,
            actual_storage_cost=None,
            platform_fee_rate=platform.default_fee_rate,
            expected_ad_rate=expected_ad_rate,
            return_rate=assigned.return_loss_rate if assigned else None,
            damage_rate=assigned.logistics_damage_rate if assigned else None,
        )
        items.append({
            "sku_id": row.sku_id, "sku_key": row.sku_key, "sku_name": row.sku_name, "specification": row.specification,
            "spu": assigned_spu, "reference_selling_price": row.reference_selling_price,
            "purchase_cost": purchase_cost,
            "platform_code": platform_code, "warehouse_code": warehouse_code, "transport_type": transport_type,
            "expected_selling_price": expected_selling_price,
            "competitor_price": profile.competitor_price if profile else None,
            "seller_coupon_amount": seller_coupon_amount,
            "expected_ad_rate": expected_ad_rate,
            "expected_logistics_cost": reference_logistics,
            "expected_storage_cost": reference_storage,
            "actual_logistics_cost": actual_logistics, "actual_storage_cost": None,
            "platform_fee_rate": platform.default_fee_rate,
            "logistics_damage_rate": assigned.logistics_damage_rate if assigned else None,
            "return_loss_rate": assigned.return_loss_rate if assigned else None,
            "configuration_status": "configured" if profile else "unconfigured",
            "turnover_class": row.turnover_class,
            "reference_storage_days": reference_storage_days(row.turnover_class),
            "reference_logistics_cost": reference_logistics,
            "reference_storage_cost": reference_storage,
            "reference_cost_status": "ready" if not missing_reasons else "incomplete",
            "reference_cost_missing_reasons": list(dict.fromkeys(missing_reasons)),
            "reference_logistics_missing_reasons": [reason for reason in missing_reasons if reason in {"missing_logistics_rule", "missing_sku_weight", "ambiguous_logistics_rule"} or (reason == "missing_sku_volume" and reference_logistics is None)],
            "reference_storage_missing_reasons": [reason for reason in missing_reasons if reason in {"missing_storage_rule", "missing_turnover_class"} or (reason == "missing_sku_volume" and reference_storage is None)],
            "preview": _decimal_payload(preview),
        })
    return {"data": items, "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


@router.post("/api/platform-sku-profit/preview")
async def preview_platform_sku_profit(body: PlatformSkuProfitPreviewRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    try:
        result = await ProductFinanceService(db).preview_platform_sku_profit(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _decimal_payload(result)


async def _platform_profit_missing_fields(
    db: AsyncSession, values: dict, preview: dict | None = None
) -> list[str]:
    """Return user-actionable blockers; zero-valued rates remain valid values."""
    sku = await db.get(DimErpSku, values["sku_id"])
    if sku is None:
        return ["ERP SKU"]
    finance = ProductFinanceService(db)
    missing: list[str] = []
    if values.get("expected_selling_price") is None and sku.reference_selling_price is None:
        missing.append("预计售价")
    purchase_cost = await finance.find_latest_purchase_cost(sku)
    if purchase_cost is None and sku.default_purchase_cost is None:
        missing.append("采购成本")
    reference_logistics, logistics_rule = await finance.find_reference_logistics_cost(
        sku, values["warehouse_code"], values["transport_type"]
    )
    if reference_logistics is None:
        if logistics_rule is not None and logistics_rule.billing_basis == "weight" and sku.weight_kg is None:
            missing.append("重量 kg")
        elif (
            logistics_rule is not None
            and logistics_rule.billing_basis == "volume"
            and logistics_rule.freight_unit_rate is not None
        ):
            missing.append("单件体积 m³")
        else:
            missing.append(f"{values['transport_type']}参考物流规则")
    reference_storage, storage_rule = await finance.find_reference_storage_cost(sku, values["warehouse_code"])
    if reference_storage is None:
        if storage_rule is None:
            missing.append("仓储规则")
        elif sku.turnover_class is None:
            missing.append("周转类型")
        else:
            missing.append("单件体积 m³")
    platform = await db.get(DimPlatform, values["platform_code"])
    if platform is None or platform.default_fee_rate is None:
        missing.append("平台费率")
    binding = (await db.execute(select(BridgeSpuSku).where(
        BridgeSpuSku.sku_id == sku.sku_id,
        BridgeSpuSku.binding_status == "active",
        BridgeSpuSku.effective_to.is_(None),
    ))).scalars().first()
    spu = await db.get(DimSpu, binding.spu) if binding else None
    if spu is None or spu.logistics_damage_rate is None or spu.return_loss_rate is None:
        missing.append("SPU货损率和退货损失率")
    if preview is not None and preview.get("expected", {}).get("profit") is None and not missing:
        missing.append("完整预计利润口径")
    return list(dict.fromkeys(missing))


@router.post("/api/platform-sku-profit/drafts", status_code=201)
async def save_platform_sku_profit_draft(body: PlatformSkuProfitDraftRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    values = body.model_dump()
    await _validate_operating_dimensions(db, values)
    profile = (await db.execute(select(SkuOperatingProfile).where(
        SkuOperatingProfile.sku_id == values["sku_id"],
        SkuOperatingProfile.platform_code == values["platform_code"],
        SkuOperatingProfile.warehouse_code == values["warehouse_code"],
        SkuOperatingProfile.status == "active",
        SkuOperatingProfile.effective_to.is_(None),
    ))).scalars().first()
    if profile is None:
        profile = SkuOperatingProfile(
            sku_id=values["sku_id"], platform_code=values["platform_code"],
            warehouse_code=values["warehouse_code"], status="active",
            created_by=getattr(_user, "user_id", None),
        )
        db.add(profile)
    for key in ("transport_type", "competitor_price", "expected_selling_price", "seller_coupon_amount", "expected_ad_rate"):
        setattr(profile, key, values.get(key))
    sku = await db.get(DimErpSku, values["sku_id"])
    platform = await db.get(DimPlatform, values["platform_code"])
    profile.reference_selling_price = sku.reference_selling_price if sku else None
    profile.platform_fee_rate = platform.default_fee_rate if platform else None
    try:
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="save_draft", resource_type="platform_sku_profit_draft",
            resource_id=f"{values['platform_code']}:{values['warehouse_code']}:{values['sku_id']}",
            changes=values,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="platform SKU profit draft conflicts with existing configuration") from exc
    return {"profile_id": profile.profile_id, "status": "draft_saved"}


@router.post("/api/platform-sku-profit/estimates", status_code=201)
async def save_platform_sku_profit_estimates(body: PlatformSkuProfitEstimateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    values = body.model_dump()
    try:
        preview = await ProductFinanceService(db).preview_platform_sku_profit(values)
    except ValueError as exc:
        missing_fields = await _platform_profit_missing_fields(db, values)
        raise HTTPException(status_code=422, detail={"code": "cannot_save_profit_version", "missing_fields": missing_fields or [str(exc)]}) from exc
    missing_fields = await _platform_profit_missing_fields(db, values, preview)
    if missing_fields:
        raise HTTPException(status_code=422, detail={"code": "cannot_save_profit_version", "missing_fields": missing_fields})
    profile = (await db.execute(select(SkuOperatingProfile).where(SkuOperatingProfile.sku_id == values["sku_id"], SkuOperatingProfile.platform_code == values["platform_code"], SkuOperatingProfile.warehouse_code == values["warehouse_code"], SkuOperatingProfile.status == "active", SkuOperatingProfile.effective_to.is_(None)))).scalars().first()
    if profile is None:
        profile = SkuOperatingProfile(sku_id=values["sku_id"], platform_code=values["platform_code"], warehouse_code=values["warehouse_code"], status="active", created_by=getattr(_user, "user_id", None))
        db.add(profile)
    for key in ("transport_type", "competitor_price", "expected_selling_price", "seller_coupon_amount", "expected_ad_rate"):
        setattr(profile, key, values.get(key))
    sku = await db.get(DimErpSku, values["sku_id"])
    profile.reference_selling_price = sku.reference_selling_price if sku else None
    platform = await db.get(DimPlatform, values["platform_code"])
    profile.platform_fee_rate = platform.default_fee_rate if platform else None
    await db.flush()
    estimates = []
    versions = [("estimated", preview["expected"])]
    if (
        preview.get("actual_logistics_cost") is not None
        or preview.get("actual_storage_cost") is not None
    ):
        versions.append(("actual_recost", preview["actual_recost"]))
    for basis, section in versions:
        row = SkuProfitEstimate(
            sku_id=values["sku_id"], operating_profile_id=profile.profile_id, platform_code=values["platform_code"], warehouse_code=values["warehouse_code"],
            assumption_version=values.get("assumption_version") or "platform-profit-workbench", scenario="base", calculation_basis=basis,
            selling_price=values.get("expected_selling_price") or profile.reference_selling_price, coupon_amount=values.get("seller_coupon_amount", 0),
            expected_selling_price=values.get("expected_selling_price") or profile.reference_selling_price, competitor_price=values.get("competitor_price"), expected_ad_rate=values.get("expected_ad_rate", 0),
            platform_fee=section.get("platform_fee", preview["expected"].get("platform_fee")), expected_ad_cost=preview["expected"].get("ad_cost"),
            expected_logistics_cost=preview["expected"].get("logistics_cost"), actual_logistics_cost=preview.get("actual_logistics_cost"),
            expected_storage_cost=preview["expected"].get("storage_cost"), actual_storage_cost=None,
            expected_profit=preview["expected"].get("profit"), expected_margin_rate=preview["expected"].get("margin_rate"),
            actual_recost_profit=preview["actual_recost"].get("profit"), actual_recost_margin_rate=preview["actual_recost"].get("margin_rate"), actual_recost_completeness=preview["actual_recost"].get("completeness"),
            logistics_cost_variance=preview["variance"].get("logistics"), storage_cost_variance=preview["variance"].get("storage"), total_cost_variance=preview["variance"].get("total"),
            reference_storage_days=preview.get("reference_storage_days"), storage_rule_id=preview.get("reference_storage_rule_id"), storage_rule_version=preview.get("reference_storage_rule_version"),
            estimated_contribution_profit=section.get("profit"), estimated_margin_rate=section.get("margin_rate"), cost_completeness=section.get("completeness", "complete"), confidence_level="medium",
        )
        db.add(row)
        estimates.append(row)
    await db.flush()
    await _enqueue_platform_sku_profit_projection(db, profile)
    await _write_product_center_audit(
        db, _user, action_type="create", resource_type="platform_sku_profit_estimate",
        resource_id=f"{values['platform_code']}:{values['warehouse_code']}:{values['sku_id']}",
        changes={
            "profile_id": profile.profile_id,
            "estimate_count": len(estimates),
            "calculation_bases": [basis for basis, _section in versions],
        },
    )
    await db.commit()
    return {"profile_id": profile.profile_id, "estimate_ids": [row.estimate_id for row in estimates]}


@router.get("/api/platform-sku-profit/estimates")
async def list_platform_sku_profit_estimates(
    platform_code: str = Query(..., min_length=1),
    warehouse_code: str = Query(..., min_length=1),
    sku_id: int | None = Query(None, gt=0),
    calculation_basis: str | None = Query(None, pattern=r"^(estimated|actual_recost)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = [SkuProfitEstimate.platform_code == platform_code, SkuProfitEstimate.warehouse_code == warehouse_code]
    if sku_id is not None:
        filters.append(SkuProfitEstimate.sku_id == sku_id)
    if calculation_basis:
        filters.append(SkuProfitEstimate.calculation_basis == calculation_basis)
    total = int((await db.execute(select(func.count()).select_from(SkuProfitEstimate).where(*filters))).scalar() or 0)
    rows = (await db.execute(select(SkuProfitEstimate).where(*filters).order_by(SkuProfitEstimate.estimate_as_of.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"data": [_decimal_payload({"estimate_id": row.estimate_id, "sku_id": row.sku_id, "calculation_basis": row.calculation_basis, "expected_profit": row.expected_profit, "expected_margin_rate": row.expected_margin_rate, "actual_recost_profit": row.actual_recost_profit, "actual_recost_margin_rate": row.actual_recost_margin_rate, "actual_recost_completeness": row.actual_recost_completeness, "estimate_as_of": row.estimate_as_of}) for row in rows], "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


@router.get("/api/sku-operating-profiles", response_model=list[SkuOperatingProfileResponse])
async def list_sku_operating_profiles(
    sku_id: int | None = Query(None, gt=0),
    platform_code: str | None = Query(None),
    spu: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    status: str | None = Query(None),
    include_unconfigured: bool = Query(True),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    for field, value in ((SkuOperatingProfile.sku_id, sku_id), (SkuOperatingProfile.platform_code, platform_code), (SkuOperatingProfile.warehouse_code, warehouse_code), (SkuOperatingProfile.status, status)):
        if value is not None:
            filters.append(field == value)
    rows = (await db.execute(select(SkuOperatingProfile).where(*filters).order_by(SkuOperatingProfile.platform_code, SkuOperatingProfile.warehouse_code, SkuOperatingProfile.sku_id))).scalars().all()
    sku_ids = {row.sku_id for row in rows}
    profile_ids = {row.profile_id for row in rows}
    sku_rows = (await db.execute(select(DimErpSku).where(DimErpSku.sku_id.in_(sku_ids)))).scalars().all() if sku_ids else []
    sku_by_id = {row.sku_id: row for row in sku_rows}
    bindings = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.sku_id.in_(sku_ids), BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None)))).scalars().all() if sku_ids else []
    spu_codes = {row.spu for row in bindings}
    spu_rows = (await db.execute(select(DimSpu).where(DimSpu.spu.in_(spu_codes)))).scalars().all() if spu_codes else []
    spu_by_code = {row.spu: row for row in spu_rows}
    binding_by_sku = {row.sku_id: row for row in bindings}
    estimates = (await db.execute(select(SkuProfitEstimate).where(SkuProfitEstimate.operating_profile_id.in_(profile_ids)).order_by(SkuProfitEstimate.estimate_as_of.desc()))).scalars().all() if profile_ids else []
    estimate_by_profile = {}
    for estimate in estimates:
        estimate_by_profile.setdefault(estimate.operating_profile_id, estimate)
    payloads = []
    finance_service = ProductFinanceService(db)
    for row in rows:
        payload = _serialize_operating_profile(
            row,
            sku=sku_by_id.get(row.sku_id),
            spu=spu_by_code.get(binding_by_sku[row.sku_id].spu) if row.sku_id in binding_by_sku else None,
            estimate=estimate_by_profile.get(row.profile_id),
        )
        payload["actual_logistics_cost"] = await finance_service.find_confirmed_logistics_cost(
            row.sku_id, row.warehouse_code, row.transport_type
        )
        payloads.append(payload)
    if spu:
        payloads = [payload for payload in payloads if payload.get("spu") == spu]
    if include_unconfigured and status in (None, "active"):
        active_skus = (await db.execute(select(DimErpSku).where(DimErpSku.status == "active"))).scalars().all()
        active_platforms = (await db.execute(select(DimPlatform).where(DimPlatform.is_active.is_(True)))).scalars().all()
        active_warehouses = (await db.execute(select(DimWarehouse).where(DimWarehouse.status == "active"))).scalars().all()
        sku_ids_for_bindings = {sku.sku_id for sku in active_skus}
        binding_rows = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.sku_id.in_(sku_ids_for_bindings), BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None)))).scalars().all() if sku_ids_for_bindings else []
        binding_by_sku = {row.sku_id: row.spu for row in binding_rows}
        bound_spu_rows = (await db.execute(select(DimSpu).where(DimSpu.spu.in_(set(binding_by_sku.values()))))).scalars().all() if binding_by_sku else []
        bound_spu_by_code = {row.spu: row for row in bound_spu_rows}
        mapped_platform_rows = (await db.execute(select(BridgeErpSkuKey.sku_id, BridgeErpSkuKey.source_platform).where(BridgeErpSkuKey.sku_id.in_(sku_ids_for_bindings), BridgeErpSkuKey.active.is_(True), BridgeErpSkuKey.effective_to.is_(None), BridgeErpSkuKey.source_platform.is_not(None)))).all() if sku_ids_for_bindings else []
        mapped_platforms = {}
        for mapped_sku_id, mapped_platform in mapped_platform_rows:
            mapped_platforms.setdefault(mapped_sku_id, set()).add(mapped_platform)
        existing_keys = {(row.sku_id, row.platform_code, row.warehouse_code) for row in rows}
        for sku in active_skus:
            bound_spu = binding_by_sku.get(sku.sku_id)
            bound_spu_row = bound_spu_by_code.get(bound_spu)
            if spu and bound_spu != spu:
                continue
            if sku_id is not None and sku.sku_id != sku_id:
                continue
            for platform in active_platforms:
                if platform_code and platform.platform_code != platform_code:
                    continue
                if mapped_platforms and platform.platform_code not in mapped_platforms.get(sku.sku_id, set()):
                    continue
                for warehouse in active_warehouses:
                    if warehouse_code and warehouse.warehouse_code != warehouse_code:
                        continue
                    key = (sku.sku_id, platform.platform_code, warehouse.warehouse_code)
                    if key in existing_keys:
                        continue
                    payloads.append({
                        "profile_id": None,
                        "sku_id": sku.sku_id,
                        "platform_code": platform.platform_code,
                        "warehouse_code": warehouse.warehouse_code,
                        "warehouse_name": warehouse.warehouse_name,
                        "transport_type": "sea",
                        "selling_price": None,
                        "default_coupon_amount": 0,
                        "platform_fee_rate": platform.default_fee_rate,
                        "expected_logistics_cost": None,
                        "expected_storage_cost": None,
                        "status": "active",
                        "effective_from": date.today(),
                        "effective_to": None,
                        "sku_key": sku.sku_key,
                        "sku_name": sku.sku_name,
                        "spu": bound_spu,
                        "logistics_damage_rate": bound_spu_row.logistics_damage_rate if bound_spu_row else None,
                        "return_loss_rate": bound_spu_row.return_loss_rate if bound_spu_row else None,
                        "cost_completeness": "incomplete",
                        "unconfigured": True,
                    })
    return payloads


async def _validate_operating_dimensions(db: AsyncSession, values: dict) -> None:
    if await db.get(DimErpSku, values["sku_id"]) is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    platform = await db.get(DimPlatform, values["platform_code"])
    if platform is None or not platform.is_active or platform.platform_role != "sales":
        raise HTTPException(status_code=422, detail="active sales platform not found")
    warehouse = await db.get(DimWarehouse, values["warehouse_code"])
    if warehouse is None or warehouse.status != "active":
        raise HTTPException(status_code=422, detail="warehouse not found or inactive")
    values["platform_fee_rate"] = platform.default_fee_rate


@router.post("/api/sku-operating-profiles", response_model=SkuOperatingProfileResponse, status_code=201)
async def create_sku_operating_profile(body: SkuOperatingProfileCreateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    values = body.model_dump()
    await _validate_operating_dimensions(db, values)
    row = SkuOperatingProfile(**values, created_by=getattr(_user, "user_id", None), updated_by=getattr(_user, "user_id", None))
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="sku_operating_profile",
            resource_id=str(row.profile_id), changes=values,
        )
        await _enqueue_platform_sku_profit_projection(db, row)
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="active SKU operating profile already exists") from exc
    return _serialize_operating_profile(row)


@router.patch("/api/sku-operating-profiles/{profile_id}", response_model=SkuOperatingProfileResponse)
async def update_sku_operating_profile(profile_id: int, body: SkuOperatingProfileUpdateRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    row = await db.get(SkuOperatingProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU operating profile not found")
    values = body.model_dump(exclude_unset=True)
    await _validate_operating_dimensions(
        db,
        {
            "sku_id": row.sku_id,
            "platform_code": row.platform_code,
            "warehouse_code": row.warehouse_code,
        },
    )
    for key, value in values.items():
        setattr(row, key, value)
    platform = await db.get(DimPlatform, row.platform_code)
    row.platform_fee_rate = platform.default_fee_rate if platform is not None else None
    row.updated_by = getattr(_user, "user_id", None)
    try:
        await _write_product_center_audit(
            db, _user, action_type="update", resource_type="sku_operating_profile",
            resource_id=str(row.profile_id), changes=values,
        )
        await _enqueue_platform_sku_profit_projection(db, row)
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="active SKU operating profile already exists") from exc
    return _serialize_operating_profile(row)


@router.post("/api/sku-operating-profiles/bulk")
async def bulk_save_sku_operating_profiles(body: SkuOperatingProfileBulkRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    created = 0
    updated = 0
    rows = []
    changes_by_row = []
    try:
        for item in body.items:
            values = item.model_dump()
            await _validate_operating_dimensions(db, values)
            filters = [SkuOperatingProfile.sku_id == values["sku_id"], SkuOperatingProfile.platform_code == values["platform_code"], SkuOperatingProfile.warehouse_code == values["warehouse_code"], SkuOperatingProfile.status == "active", SkuOperatingProfile.effective_to.is_(None)]
            row = (await db.execute(select(SkuOperatingProfile).where(*filters))).scalars().first()
            if row is None:
                row = SkuOperatingProfile(**values, created_by=getattr(_user, "user_id", None), updated_by=getattr(_user, "user_id", None))
                db.add(row)
                created += 1
                action_type = "create"
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                row.updated_by = getattr(_user, "user_id", None)
                updated += 1
                action_type = "update"
            rows.append(row)
            changes_by_row.append((action_type, row, values))
        await db.flush()
        for action_type, row, values in changes_by_row:
            await _write_product_center_audit(
                db, _user, action_type=action_type, resource_type="sku_operating_profile",
                resource_id=str(row.profile_id), changes=values,
            )
        for row in rows:
            await _enqueue_platform_sku_profit_projection(db, row)
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="bulk operating profile save conflicts with existing data") from exc
    return {"created": created, "updated": updated, "items": [_serialize_operating_profile(row) for row in rows]}


@router.get("/api/sku-operating-profiles/{profile_id}", response_model=SkuOperatingProfileResponse)
async def get_sku_operating_profile(profile_id: int, db: AsyncSession = Depends(get_async_db)):
    row = await db.get(SkuOperatingProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU operating profile not found")
    return _serialize_operating_profile(row)


@router.post("/api/sku-operating-profiles/{profile_id}/profit-preview", response_model=SkuOperatingProfitResponse)
async def preview_sku_operating_profit(profile_id: int, body: SkuOperatingProfitRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    try:
        result = await ProductFinanceService(db).preview_operating_profit(profile_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {key: float(value) if hasattr(value, "as_tuple") else value for key, value in result.items()}


@router.post("/api/sku-operating-profiles/{profile_id}/profit-estimates", response_model=SkuOperatingProfitSaveResponse, status_code=201)
async def save_sku_operating_profit(profile_id: int, body: SkuOperatingProfitRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(_require_editor)):
    try:
        row = await ProductFinanceService(db).save_operating_profit(profile_id, body.model_dump(exclude_unset=True))
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="sku_operating_profit_estimate",
            resource_id=str(row.estimate_id), changes={"profile_id": profile_id},
        )
        await _enqueue_platform_sku_profit_projection(db, await db.get(SkuOperatingProfile, profile_id))
        await db.commit()
        await db.refresh(row)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"estimate_id": row.estimate_id, "profile_id": row.operating_profile_id, "sku_id": row.sku_id, "estimated_contribution_profit": float(row.estimated_contribution_profit) if row.estimated_contribution_profit is not None else None, "estimated_margin_rate": float(row.estimated_margin_rate) if row.estimated_margin_rate is not None else None}


@router.get("/api/sku-operating-profiles/{profile_id}/profit-estimates", response_model=list[SkuOperatingProfitHistoryResponse])
async def list_sku_operating_profit_history(profile_id: int, limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_async_db)):
    rows = (await db.execute(select(SkuProfitEstimate).where(SkuProfitEstimate.operating_profile_id == profile_id).order_by(SkuProfitEstimate.estimate_as_of.desc()).limit(limit))).scalars().all()
    return [{"estimate_id": row.estimate_id, "profile_id": row.operating_profile_id, "sku_id": row.sku_id, "platform_code": row.platform_code, "warehouse_code": row.warehouse_code, "estimate_as_of": row.estimate_as_of, "estimated_contribution_profit": float(row.estimated_contribution_profit) if row.estimated_contribution_profit is not None else None, "estimated_margin_rate": float(row.estimated_margin_rate) if row.estimated_margin_rate is not None else None, "cost_completeness": row.cost_completeness, "confidence_level": row.confidence_level} for row in rows]


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
    await db.flush()
    await _write_product_center_audit(
        db, _user, action_type="create", resource_type="profit_estimate",
        resource_id=str(row.estimate_id), changes=values,
    )
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
        await _write_product_center_audit(
            db, _user, action_type="create", resource_type="profit_estimate",
            resource_id=str(row.estimate_id), changes=body.model_dump(mode="json"),
        )
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
    platform_sku_profit_table_id = body.platform_sku_profit_table_id or os.getenv("FEISHU_PRODUCT_PLATFORM_SKU_PROFIT_TABLE_ID")
    client = FeishuProjectionClient()
    try:
        config = await FeishuProjectionService(db).initialize_tables(client, spu_table_id, sku_table_id, platform_sku_profit_table_id)
        await _write_product_center_audit(
            db, _user, action_type="initialize", resource_type="feishu_projection",
            resource_id=config.provider_code,
            changes={"status": config.status, "projection_tables_initialized": True},
        )
        await db.commit()
    except RuntimeError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": config.status, "spu_table_id": config.spu_table_id, "sku_table_id": config.sku_table_id, "platform_sku_profit_table_id": config.platform_sku_profit_table_id}


@router.get("/api/feishu-projection/status")
async def get_feishu_projection_status(db: AsyncSession = Depends(get_async_db)):
    return await FeishuProjectionService(db).status()


@router.post("/api/feishu-projection/retry-failed")
async def retry_failed_feishu_projection(db: AsyncSession = Depends(get_async_db), _user=Depends(_require_projection_admin)):
    retried = await FeishuProjectionService(db).retry_failed()
    await _write_product_center_audit(
        db, _user, action_type="retry", resource_type="feishu_projection",
        resource_id="failed_tasks", changes={"retried": retried},
    )
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
