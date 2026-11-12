from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, func, select, text, update
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
    SpuBulkMutationResponse,
    SkuBulkMutationResponse,
    ProductCategoryCreateRequest,
    ProductCategoryResponse,
    ProductCategoryUpdateRequest,
    SpuItem,
    SkuItem,
    SpuListResponse,
    SkuListResponse,
    SkuPricingOverrideRequest,
    SkuPricingOverrideResponse,
    SkuSellingPricePreviewRequest,
    SkuSellingPricePreviewResponse,
    SkuSellingPriceCheck,
    SkuSellingPriceCheckResponse,
    ProductWarehouseCreateRequest,
    ProductWarehouseUpdateRequest,
    PlatformFeeRateUpdateRequest,
    PlatformFeeRateResponse,
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
    SpuOption,
    SpuOptionListResponse,
    SpuDeletionPreviewResponse,
    SpuDeletionCheck,
    SpuSoftDeleteRequest,
    SpuSoftDeleteResponse,
    SpuRestoreRequest,
    SpuRestoreResponse,
    BatchSpuSoftDeleteRequest,
    BatchSpuSoftDeleteItem,
    BatchSpuSoftDeleteResponse,
    SkuDeletionCheck,
    SkuDeletionPreviewResponse,
    SkuSoftDeleteRequest,
    SkuSoftDeleteResponse,
    SkuRestoreRequest,
    SkuRestoreResponse,
    SkuPricingPolicyCreateRequest,
    SkuPricingPolicyResponse,
    SkuPricingPolicyUpdateRequest,
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
    SkuPricingPolicy,
    WarehouseStorageRule,
)
from backend.services.product_finance_service import (
    BillTotalMismatchError,
    ProductFinanceService,
)
from backend.services.product_profit_service import (
    build_platform_profit_preview,
    reference_storage_days,
)
from backend.services.product_pricing_service import (
    POLICY_REJECT_FUTURE,
    PolicyUpdateRejected,
    resolve_policy_update,
)
from backend.services.product_pricing_query_service import (
    compute_pricing_for_sku as _compute_pricing_for_sku,
    compute_pricing_state as _compute_pricing_state,
    load_pricing_context as _pricing_context,
    resolve_pricing_platform_code as _pricing_platform_code,
)
from backend.services.inventory.warehouse_divergence_service import (
    detect_warehouse_divergence,
)
from backend.services.inventory.inventory_warehouse_stock_query_service import (
    load_warehouse_stock_snapshot,
    resolve_stock_status,
    select_sku_ids_by_stock,
)
from backend.services.product_pricing_override_service import (
    clear_platform_override,
    set_platform_override,
)
from backend.services.product_selling_price_service import (
    apply_selling_price_confirmation,
    assess_selling_price_deviation,
    build_selling_price_preview,
    compute_selling_price_age,
)
from backend.services.product_transaction_price_service import (
    load_transaction_price_bands,
)
from backend.services.sku_pricing_policy_service import (
    load_current_policies,
    policy_current_predicate,
)

# SPU 经营状态与「能不能挂货」的口径**只从真源取**（律 1）。
# 候选集查询与写入校验引用同一份判定 ⇒ 不会出现「下拉里能选、保存时被拒」。
from backend.services.product_spu_lifecycle import (
    SPU_BIZ_STATUS_PROMOTED,
    SPU_BIZ_STATUS_RETIRED,
    is_spu_assignable,
    spu_assignable_condition,
)

# SKU ↔ SPU **归属关系**的口径只从真源取（律 1）：
# 「当前有效」的判定条件、投影字段（spu + 生效日）都只有这一处定义。
from backend.services.product_spu_binding import (
    CURRENT_BINDING_STATUS,
    HISTORICAL_BINDING_STATUS,
    INACTIVE_BINDING_STATUS,
    archived_binding_condition,
    current_binding_condition,
    project_current_binding,
)
from backend.utils.exceptions import BusinessValidationError, ConflictError
from modules.core.logger import get_logger
from backend.services.feishu_projection_client import FeishuProjectionClient
from backend.services.feishu_projection_service import (
    FeishuProjectionService,
    trigger_pending_projection_delivery,
)

router = APIRouter(tags=["商品中心"], dependencies=[Depends(get_current_user)])
logger = get_logger(__name__)


def _jsonable(values: dict) -> dict:
    """把写入字典转成能进 JSON 审计字段的样子。

    审计里要记**实际写入**的值（含系统自动写的字段），所以不能只靠
    Pydantic 的 ``model_dump(mode="json")`` —— 那是给请求体用的。
    """
    out: dict = {}
    for key, value in (values or {}).items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = float(value)
        elif isinstance(value, (date,)):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


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
    if getattr(current_user, "is_superuser", False) or "admin" in extract_role_codes(
        current_user
    ):
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


def _require_platform_fee_editor(current_user=Depends(get_current_user)):
    if getattr(current_user, "is_superuser", False) or extract_role_codes(
        current_user
    ) & {"admin", "manager", "finance"}:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("/api/product-categories", response_model=list[ProductCategoryResponse])
async def list_product_categories(
    level: int | None = Query(None, ge=1, le=2),
    parent_category_code: str | None = Query(None),
    include_inactive: bool = Query(
        False, description="是否包含已停用（status != 'active'）的品类"
    ),
    include_unselectable: bool = Query(
        False,
        description=(
            "是否包含不可选（is_selectable = false）的品类。"
            "⚠️ 与「停用」是**两件不同的事**：停用=这个品类不再使用；"
            "不可选=历史上出过问题、不能再分配给新的 SPU。"
            "原先两者被挤在同一个 include_inactive 开关里，"
            "调用方无法只要其中一样。"
        ),
    ),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if level is not None:
        filters.append(DimProductCategory.level == level)
    if parent_category_code is not None:
        filters.append(DimProductCategory.parent_category_code == parent_category_code)
    if not include_inactive:
        filters.append(DimProductCategory.status == "active")
    if not include_unselectable:
        filters.append(DimProductCategory.is_selectable.is_(True))
    rows = (
        (
            await db.execute(
                select(DimProductCategory)
                .where(*filters)
                .order_by(DimProductCategory.level, DimProductCategory.category_code)
            )
        )
        .scalars()
        .all()
    )
    return [ProductCategoryResponse.model_validate(row) for row in rows]


@router.post(
    "/api/product-categories", response_model=ProductCategoryResponse, status_code=201
)
async def create_product_category(
    body: ProductCategoryCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    if body.level == 2:
        parent = (
            await db.execute(
                select(DimProductCategory)
                .where(DimProductCategory.category_code == body.parent_category_code)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            parent is None
            or parent.level != 1
            or (body.status == "active" and parent.status != "active")
        ):
            raise HTTPException(
                status_code=422,
                detail="level 2 category must reference an active level 1 category when active",
            )
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
        raise HTTPException(
            status_code=409, detail="category code already exists"
        ) from exc
    return ProductCategoryResponse.model_validate(row)


@router.patch(
    "/api/product-categories/{category_code}", response_model=ProductCategoryResponse
)
async def update_product_category(
    category_code: str,
    body: ProductCategoryUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
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
            (
                await db.execute(
                    select(DimProductCategory.category_code)
                    .where(
                        DimProductCategory.parent_category_code == row.category_code,
                        DimProductCategory.status == "active",
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if active_children:
            raise HTTPException(
                status_code=409,
                detail="cannot deactivate level 1 category with active children",
            )
    if values.get("status") == "active" and row.level == 2:
        parent = (
            await db.execute(
                select(DimProductCategory)
                .where(DimProductCategory.category_code == row.parent_category_code)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if parent is None or parent.status != "active":
            raise HTTPException(
                status_code=422,
                detail="cannot activate level 2 category under inactive level 1 parent",
            )
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
        for key in (
            "category_l1_code",
            "category_l1",
            "category_l2_code",
            "category_l2",
        )
    )
    if not category_l2_code and category_fields_provided:
        if legacy_category_value == existing_category_l2_code:
            for key in (
                "category_l1_code",
                "category_l1",
                "category_l2_code",
                "category_l2",
            ):
                values.pop(key, None)
            return values
        if (
            "category_l1_code" in values
            and "category_l2_code" not in values
            and "category_l2" not in values
        ):
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
        raise HTTPException(
            status_code=422,
            detail="category_l2_code must reference an active selectable level 2 category",
        )
    category_l1 = await db.get(DimProductCategory, category_l2.parent_category_code)
    if category_l1 is None or category_l1.level != 1 or category_l1.status != "active":
        raise HTTPException(
            status_code=422,
            detail="category_l2_code must have an active level 1 parent",
        )
    requested_l1_code = values.get("category_l1_code")
    if requested_l1_code and requested_l1_code != category_l1.category_code:
        raise HTTPException(
            status_code=422,
            detail="category_l1_code must match the selected level 2 category",
        )

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


async def _enqueue_platform_sku_profit_projection(
    db: AsyncSession, row: SkuOperatingProfile
) -> None:
    await db.refresh(row)
    await FeishuProjectionService(db).enqueue(
        "platform_sku_profit",
        str(row.profile_id),
        {
            "profile_id": row.profile_id,
            "reason": "platform_sku_profit_changed",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "selling_price": (
                float(row.selling_price) if row.selling_price is not None else None
            ),
            "expected_logistics_cost": (
                float(row.expected_logistics_cost)
                if row.expected_logistics_cost is not None
                else None
            ),
            "expected_storage_cost": (
                float(row.expected_storage_cost)
                if row.expected_storage_cost is not None
                else None
            ),
        },
    )


@router.get("/api/spus", response_model=SpuListResponse)
async def list_spus(
    keyword: str | None = Query(None),
    biz_status: str | None = Query(None),
    include_soft_deleted: bool = Query(
        False,
        description=(
            "是否包含已删除（软删 active=false）的 SPU。"
            "⚠️ 刻意不叫 include_inactive —— 「停用」在这个域里是 biz_status，"
            "与「已删除」是两件事；同名会让人以为三处端点的同一参数是同一口径。"
        ),
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if not include_soft_deleted:
        filters.append(DimSpu.active.is_(True))
    if keyword:
        pattern = f"%{keyword}%"
        filters.append((DimSpu.spu.ilike(pattern)) | (DimSpu.spu_name.ilike(pattern)))
    if biz_status:
        filters.append(DimSpu.biz_status == biz_status)
    total = int(
        (
            await db.execute(select(func.count()).select_from(DimSpu).where(*filters))
        ).scalar()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(DimSpu)
                .where(*filters)
                .order_by(DimSpu.spu)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [SpuItem.model_validate(row) for row in rows]
    return SpuListResponse(
        data=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


# ---------------------------------------------------------------------------
# 值的域（Value Domain）
# ---------------------------------------------------------------------------
#
# 「可选的款有哪些」是一个**业务问题**，答案由业务口径算出 —— 不是
# 「某个页面刚好加载了哪一页」的副产品。
#
# 事故背景（2026-11-12）：工具栏「所属 SPU」筛选器与新增 SKU 行的选款框，
# 候选集直接绑定了「SPU 管理」tab 的**分页表格数据**（``/api/spus`` 默认
# page=1、page_size=20）。dim_spu 实测 286 条 ⇒ 第 36 个 SPU
# （XH-FASHION-001）永远不在候选集里：运营输入后看到「无匹配数据」，
# 回车不生效，筛选根本没发生。
#
# ⇒ 这里给两个口径**各自独立**的端点：
#   * ``/api/spus/options``            —— 浏览口径：在售（可被筛到）
#   * ``/api/spus/assignable-options``  —— 可绑定口径：在售且未淘汰（可被挂货）
#
# ⚠️ 口径**固化在端点里**，不暴露给调用方自由拼装 —— 否则前端能组合出
#    自相矛盾的候选集（例如「已删除但状态还是候选」）。
# ⚠️ 与 ``/api/spus`` 的关系：``/api/spus`` 是**管理列表**（分页、可编辑行、
#    含软删行）；这里是**值的域**（轻量、可搜索、无分页）。两者职责不同，
#    不是重复实现。


def _spu_option_filters(
    keyword: str | None,
    extra_conditions: list | None = None,
) -> list:
    """值的域的公共过滤条件：关键词（编码或名称，模糊匹配）。"""
    filters = list(extra_conditions or [])
    if keyword:
        pattern = f"%{keyword}%"
        filters.append((DimSpu.spu.ilike(pattern)) | (DimSpu.spu_name.ilike(pattern)))
    return filters


@router.get("/api/spus/options", response_model=SpuOptionListResponse)
async def list_spu_options(
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    """值的域 · **浏览口径**：在售的款。

    含「逻辑淘汰但未删除」的款（``active=true`` + ``biz_status='retired'``）——
    业务上不再经营，但历史还在，运营可能仍需要筛它。

    ⚠️ 与「可绑定口径」分开：可挂货的范围更窄，见
       ``/api/spus/assignable-options``。
    """
    filters = _spu_option_filters(keyword, [DimSpu.active.is_(True)])
    rows = (
        (
            await db.execute(
                select(DimSpu).where(*filters).order_by(DimSpu.spu).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return SpuOptionListResponse(
        data=[SpuOption(spu=row.spu, spu_name=row.spu_name) for row in rows]
    )


@router.get("/api/spus/assignable-options", response_model=SpuOptionListResponse)
async def list_spu_assignable_options(
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    """值的域 · **可绑定口径**：现在还允许挂新 SKU 的款。

    口径来自真源 :func:`spu_assignable_condition` —— 与写入时的校验
    ``_assert_spu_assignable`` **引用同一份判定** ⇒ 不会出现
    「下拉里能选、保存时被拒」。
    """
    filters = _spu_option_filters(keyword, [spu_assignable_condition()])
    rows = (
        (
            await db.execute(
                select(DimSpu).where(*filters).order_by(DimSpu.spu).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return SpuOptionListResponse(
        data=[SpuOption(spu=row.spu, spu_name=row.spu_name) for row in rows]
    )


@router.post("/api/spus", response_model=SpuItem, status_code=201)
async def create_spu(
    body: SpuCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    values = body.model_dump()
    if not values.get("category_l2_code") and not values.get("category_l2"):
        raise HTTPException(
            status_code=422, detail="category_l2_code is required when creating an SPU"
        )
    row = DimSpu(**(await _apply_spu_category(db, values)))
    db.add(row)
    try:
        await db.flush()
        await _enqueue_spu_projection(db, row)
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="spu",
            resource_id=row.spu,
            changes=values,
        )
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SPU already exists") from exc
    return SpuItem.model_validate(row)


@router.patch("/api/spus/{spu}", response_model=SpuItem)
async def update_spu(
    spu: str,
    body: SpuUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
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
        db,
        _user,
        action_type="update",
        resource_type="spu",
        resource_id=row.spu,
        changes=values,
    )
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return SpuItem.model_validate(row)


# ==================== SPU 删除向导 (M1: 软删最小可用 / M2: 批量软删) ====================


async def _check_spu_deletion_blockers(
    db: AsyncSession, spu_code: str
) -> list[SpuDeletionCheck]:
    """7 项删除前置校验。status=fail 阻塞;warn 软提示;pass 无影响。

    当前实现:3 项核心(spu_exists / biz_status_warn / spu_has_active_skus)。
    其余 4 项(operating profile / pending version / pending inventory / platform listing)
    已在 M2/M3 占位返回 pass,未来按需加深。
    """
    checks: list[SpuDeletionCheck] = []

    # 1. SPU 存在
    spu_row = await db.get(DimSpu, spu_code)
    if spu_row is None:
        checks.append(
            SpuDeletionCheck(
                code="spu_exists",
                label="SPU 存在",
                status="fail",
                detail=f"SPU '{spu_code}' 不存在",
            )
        )
        return checks
    checks.append(SpuDeletionCheck(code="spu_exists", label="SPU 存在", status="pass"))

    # 2. biz_status 提示(非 fail,鼓励改 retired 再删)
    if spu_row.biz_status == SPU_BIZ_STATUS_RETIRED:
        checks.append(
            SpuDeletionCheck(
                code="biz_status_not_retired",
                label="biz_status 应为 retired",
                status="pass",
            )
        )
    else:
        checks.append(
            SpuDeletionCheck(
                code="biz_status_not_retired",
                label="biz_status 应为 retired",
                status="warn",
                detail=f"当前 biz_status={spu_row.biz_status},建议先改 retired 再删",
            )
        )

    # 3. active SKU 阻塞
    active_binding_count = (
        await db.execute(
            select(func.count(BridgeSpuSku.id)).where(
                BridgeSpuSku.spu == spu_code,
                *current_binding_condition(),
            )
        )
    ).scalar() or 0
    if active_binding_count == 0:
        checks.append(
            SpuDeletionCheck(
                code="spu_has_active_skus", label="无 active SKU 挂载", status="pass"
            )
        )
    else:
        checks.append(
            SpuDeletionCheck(
                code="spu_has_active_skus",
                label="无 active SKU 挂载",
                status="fail",
                detail=f"仍有 {active_binding_count} 个 active SKU,请先停用 SKU",
            )
        )

    # 4-7 占位(均为 pass,M3 完善)
    checks.append(
        SpuDeletionCheck(
            code="no_active_profiles",
            label="无 active operating profile",
            status="pass",
        )
    )
    checks.append(
        SpuDeletionCheck(
            code="no_pending_versions",
            label="无 pending profit version",
            status="pass",
            detail="M2 完善",
        )
    )
    checks.append(
        SpuDeletionCheck(
            code="no_pending_inventory",
            label="无未消耗 inventory",
            status="pass",
            detail="M2 完善",
        )
    )
    checks.append(
        SpuDeletionCheck(
            code="no_active_listings",
            label="无平台在架",
            status="pass",
            detail="M2 完善",
        )
    )

    return checks


@router.post(
    "/api/spus/{spu}/deletion-preview", response_model=SpuDeletionPreviewResponse
)
async def preview_spu_deletion(
    spu: str,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """预览删除:返回 7 项校验明细 + 软删/硬删能力 + 影响范围。"""
    spu_row = await db.get(DimSpu, spu)
    checks = await _check_spu_deletion_blockers(db, spu)
    blocked = [c for c in checks if c.status == "fail"]

    soft_impact: dict[str, int] = {}
    can_soft_delete = len(blocked) == 0
    if can_soft_delete:
        binding_count = (
            await db.execute(
                select(func.count(BridgeSpuSku.id)).where(
                    BridgeSpuSku.spu == spu,
                    *current_binding_condition(),
                )
            )
        ).scalar() or 0
        soft_impact["dim_spu"] = 1
        soft_impact["bridge_spu_sku_inactive"] = binding_count
        soft_impact["fact_audit_log"] = 1

    return SpuDeletionPreviewResponse(
        spu=spu,
        spu_name=spu_row.spu_name if spu_row else None,
        can_soft_delete=can_soft_delete,
        can_hard_delete=False,
        checks=checks,
        soft_delete_impact=soft_impact,
        hard_delete_impact={},
        blocked_reasons=[c.label + ": " + (c.detail or "") for c in blocked],
    )


@router.post("/api/spus/{spu}/soft-delete", response_model=SpuSoftDeleteResponse)
async def soft_delete_spu(
    spu: str,
    body: SpuSoftDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """软删 SPU:active=false + biz_status=retired,失效 binding,写 audit。"""
    checks = await _check_spu_deletion_blockers(db, spu)
    blocked = [c for c in checks if c.status == "fail"]
    if blocked:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "spu_deletion_blocked",
                "blocked_checks": [c.model_dump() for c in blocked],
                "blocked_reasons": [c.label + ": " + (c.detail or "") for c in blocked],
            },
        )

    spu_row = await db.get(DimSpu, spu)
    if spu_row is None:
        raise HTTPException(status_code=404, detail=f"SPU '{spu}' not found")

    spu_row.active = False
    if spu_row.biz_status != SPU_BIZ_STATUS_RETIRED:
        spu_row.biz_status = SPU_BIZ_STATUS_RETIRED

    binding_result = await db.execute(
        update(BridgeSpuSku)
        .where(
            BridgeSpuSku.spu == spu,
            *current_binding_condition(),
        )
        .values(binding_status=INACTIVE_BINDING_STATUS, effective_to=date.today())
    )
    affected_bindings = binding_result.rowcount or 0

    await _write_product_center_audit(
        db,
        _user,
        action_type="soft_delete",
        resource_type="spu",
        resource_id=spu,
        changes={
            "active": False,
            "biz_status": spu_row.biz_status,
            "affected_bindings": affected_bindings,
            "reason": body.reason,
            "warn_checks": [c.model_dump() for c in checks if c.status == "warn"],
        },
    )
    await db.commit()

    return SpuSoftDeleteResponse(
        spu=spu,
        spu_name=spu_row.spu_name,
        soft_deleted_at=datetime.now(timezone.utc),
        affected_bindings=affected_bindings,
        biz_status=spu_row.biz_status,
        audit_recorded=True,
    )


@router.post("/api/spus/{spu}/restore", response_model=SpuRestoreResponse)
async def restore_spu(
    spu: str,
    body: SpuRestoreRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """恢复 SPU:active=false → active=true, biz_status 还原。

    复活最早的 inactive binding(effective_to 清空 + binding_status='active')。
    其他历史 binding 保留 inactive 状态以备追溯。
    """
    spu_row = await db.get(DimSpu, spu)
    if spu_row is None:
        raise HTTPException(status_code=404, detail=f"SPU '{spu}' not found")
    if spu_row.active:
        raise HTTPException(
            status_code=409,
            detail=f"SPU '{spu}' 已是启用状态,无需恢复",
        )

    previous_biz_status = spu_row.biz_status
    spu_row.active = True
    # biz_status 复位:从 retired 回到 promoted(用户恢复意图=重新启用)
    if spu_row.biz_status == SPU_BIZ_STATUS_RETIRED:
        spu_row.biz_status = SPU_BIZ_STATUS_PROMOTED

    earliest_inactive = (
        await db.execute(
            select(BridgeSpuSku)
            .where(
                BridgeSpuSku.spu == spu,
                *archived_binding_condition(),
            )
            .order_by(BridgeSpuSku.effective_to.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    restored_bindings = 0
    if earliest_inactive is not None:
        earliest_inactive.binding_status = CURRENT_BINDING_STATUS
        earliest_inactive.effective_to = None
        restored_bindings = 1

    await _write_product_center_audit(
        db,
        _user,
        action_type="spu_restore",
        resource_type="spu",
        resource_id=spu,
        changes={
            "active": True,
            "previous_biz_status": previous_biz_status,
            "new_biz_status": spu_row.biz_status,
            "restored_bindings": restored_bindings,
            "reason": body.reason,
        },
    )
    await db.commit()

    return SpuRestoreResponse(
        spu=spu,
        spu_name=spu_row.spu_name,
        previous_biz_status=previous_biz_status,
        new_biz_status=spu_row.biz_status,
        restored_bindings=restored_bindings,
        restored_at=datetime.now(timezone.utc),
        audit_recorded=True,
    )


@router.post("/api/spus/batch-soft-delete", response_model=BatchSpuSoftDeleteResponse)
async def batch_soft_delete_spus(
    body: BatchSpuSoftDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """批量软删(1~100 个),任一 fail 整体回滚,保证事务原子性。"""
    items: list[BatchSpuSoftDeleteItem] = []
    blocked_spus: list[str] = []

    for spu in body.spus:
        spu_row = await db.get(DimSpu, spu)
        if spu_row is None:
            blocked_spus.append(spu)
            items.append(
                BatchSpuSoftDeleteItem(
                    spu=spu,
                    status="blocked",
                    blocked_reasons=[f"SPU '{spu}' 不存在"],
                )
            )
            continue
        checks = await _check_spu_deletion_blockers(db, spu)
        blocked = [c for c in checks if c.status == "fail"]
        warn_checks = [c for c in checks if c.status == "warn"]
        if blocked:
            blocked_spus.append(spu)
            items.append(
                BatchSpuSoftDeleteItem(
                    spu=spu,
                    spu_name=spu_row.spu_name,
                    status="blocked",
                    blocked_reasons=[
                        c.label + ": " + (c.detail or "") for c in blocked
                    ],
                    warn_checks=[c.model_dump() for c in warn_checks],
                )
            )
        else:
            items.append(
                BatchSpuSoftDeleteItem(
                    spu=spu,
                    spu_name=spu_row.spu_name,
                    status="deleted",
                    affected_bindings=0,
                    warn_checks=[c.model_dump() for c in warn_checks],
                )
            )

    if blocked_spus:
        return BatchSpuSoftDeleteResponse(
            total=len(body.spus),
            deleted=0,
            blocked=len(blocked_spus),
            rolled_back=True,
            items=items,
        )

    success_count = 0
    try:
        for spu in body.spus:
            spu_row = await db.get(DimSpu, spu)
            if spu_row is None:
                continue
            spu_row.active = False
            if spu_row.biz_status != SPU_BIZ_STATUS_RETIRED:
                spu_row.biz_status = SPU_BIZ_STATUS_RETIRED
            binding_result = await db.execute(
                update(BridgeSpuSku)
                .where(
                    BridgeSpuSku.spu == spu,
                    *current_binding_condition(),
                )
                .values(
                    binding_status=INACTIVE_BINDING_STATUS, effective_to=date.today()
                )
            )
            affected_bindings = binding_result.rowcount or 0
            for item in items:
                if item.spu == spu and item.status == "deleted":
                    item.affected_bindings = affected_bindings
                    break
            await _write_product_center_audit(
                db,
                _user,
                action_type="batch_soft_delete",
                resource_type="spu",
                resource_id=spu,
                changes={
                    "active": False,
                    "biz_status": spu_row.biz_status,
                    "affected_bindings": affected_bindings,
                    "reason": body.reason,
                    "batch_total": len(body.spus),
                },
            )
            success_count += 1
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return BatchSpuSoftDeleteResponse(
        total=len(body.spus),
        deleted=success_count,
        blocked=0,
        rolled_back=False,
        items=items,
    )


# ==================== SKU 停用/恢复 (M5.1) ====================


async def _count_sku_business_references(
    db: AsyncSession, sku_id: int
) -> dict[str, int]:
    """统计 SKU 在 9 张业务表中的引用数。返回 {table: count}。

    软删不强制要求 0;硬删(M5.2)才要求全部 0。
    """
    refs: dict[str, int] = {}
    # sku_id 字段的表
    sku_id_tables = [
        ("finance", "sku_profit_estimates"),
        ("finance", "sku_operating_profiles"),
        ("finance", "logistics_bill_lines"),
        ("core", "bridge_erp_sku_keys"),
    ]
    for sch, tbl in sku_id_tables:
        try:
            c = (
                await db.execute(
                    text(f"SELECT COUNT(*) FROM {sch}.{tbl} WHERE sku_id = :id"),
                    {"id": sku_id},
                )
            ).scalar() or 0
            refs[f"{sch}.{tbl}"] = int(c)
        except Exception:
            await db.rollback()
            refs[f"{sch}.{tbl}"] = 0
    # platform_sku 字段的表(用 sku_key 查)
    sku_row = await db.get(DimErpSku, sku_id)
    sku_key = sku_row.sku_key if sku_row else None
    if sku_key:
        platform_sku_tables = [
            ("finance", "po_lines"),
            ("finance", "grn_lines"),
            ("finance", "inventory_layers"),
            ("finance", "inventory_ledger"),
            ("finance", "return_orders"),
            ("core", "staging_inventory"),
        ]
        for sch, tbl in platform_sku_tables:
            try:
                c = (
                    await db.execute(
                        text(
                            f"SELECT COUNT(*) FROM {sch}.{tbl} WHERE platform_sku = :k"
                        ),
                        {"k": sku_key},
                    )
                ).scalar() or 0
                refs[f"{sch}.{tbl}"] = int(c)
            except Exception:
                await db.rollback()
                refs[f"{sch}.{tbl}"] = 0
    return refs


async def _check_sku_deletion_blockers(
    db: AsyncSession, sku_id: int
) -> list[SkuDeletionCheck]:
    """6 项 SKU 停用前置校验。

    fail = 阻塞(只 SKU 不存在);warn = 软提示;pass = 无影响。
    业务引用计数不阻断软删,只用于提示与未来硬删门槛。
    """
    checks: list[SkuDeletionCheck] = []

    # 1. SKU 存在
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        checks.append(
            SkuDeletionCheck(
                code="sku_exists",
                label="SKU 存在",
                status="fail",
                detail=f"SKU id={sku_id} 不存在",
            )
        )
        return checks
    checks.append(SkuDeletionCheck(code="sku_exists", label="SKU 存在", status="pass"))

    # 2. status 提示
    if sku_row.status == "inactive":
        checks.append(
            SkuDeletionCheck(
                code="sku_already_inactive",
                label="当前已是停用状态",
                status="warn",
                detail="如需恢复请走恢复路径",
            )
        )
    else:
        checks.append(
            SkuDeletionCheck(
                code="sku_already_inactive", label="当前已是停用状态", status="pass"
            )
        )

    # 3. active binding 提示(软删会一并失效,不阻断)
    active_binding_count = (
        await db.execute(
            select(func.count(BridgeSpuSku.id)).where(
                BridgeSpuSku.sku_id == sku_id,
                *current_binding_condition(),
            )
        )
    ).scalar() or 0
    if active_binding_count > 0:
        checks.append(
            SkuDeletionCheck(
                code="has_active_bindings",
                label="存在 active SPU 绑定",
                status="warn",
                detail=f"将有 {active_binding_count} 条 binding 同步失效",
            )
        )
    else:
        checks.append(
            SkuDeletionCheck(
                code="has_active_bindings", label="存在 active SPU 绑定", status="pass"
            )
        )

    # 4. 业务引用提示(不阻断软删)
    refs = await _count_sku_business_references(db, sku_id)
    total_refs = sum(refs.values())
    non_zero = {k: v for k, v in refs.items() if v > 0}
    if total_refs > 0:
        detail_parts = [f"{k}={v}" for k, v in non_zero.items()]
        checks.append(
            SkuDeletionCheck(
                code="business_references",
                label="业务表引用",
                status="warn",
                detail=f"共 {total_refs} 条引用({'; '.join(detail_parts[:3])}{'...' if len(detail_parts) > 3 else ''}),停用不影响数据",
            )
        )
    else:
        checks.append(
            SkuDeletionCheck(
                code="business_references",
                label="业务表引用",
                status="pass",
                detail="0 引用,具备未来硬删条件",
            )
        )

    # 5-6 占位
    checks.append(
        SkuDeletionCheck(
            code="no_pending_versions",
            label="无 pending 利润版本",
            status="pass",
            detail="M5.2 完善",
        )
    )
    checks.append(
        SkuDeletionCheck(
            code="no_pending_inventory",
            label="无未消耗库存",
            status="pass",
            detail="M5.2 完善",
        )
    )

    return checks


@router.post(
    "/api/skus/{sku_id}/deletion-preview", response_model=SkuDeletionPreviewResponse
)
async def preview_sku_deletion(
    sku_id: int,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """预览 SKU 停用:返回校验明细 + 业务引用计数 + 影响范围。"""
    sku_row = await db.get(DimErpSku, sku_id)
    checks = await _check_sku_deletion_blockers(db, sku_id)
    blocked = [c for c in checks if c.status == "fail"]

    refs = await _count_sku_business_references(db, sku_id)
    total_refs = sum(refs.values())

    can_soft_delete = (
        sku_row is not None and sku_row.status == "active" and len(blocked) == 0
    )
    can_hard_delete = sku_row is not None and total_refs == 0  # M5.2 才启用入口

    soft_impact: dict[str, int] = {}
    if can_soft_delete:
        active_binding_count = (
            await db.execute(
                select(func.count(BridgeSpuSku.id)).where(
                    BridgeSpuSku.sku_id == sku_id,
                    *current_binding_condition(),
                )
            )
        ).scalar() or 0
        soft_impact["dim_erp_sku_status"] = 1
        soft_impact["bridge_spu_sku_inactive"] = int(active_binding_count)
        soft_impact["fact_audit_log"] = 1

    return SkuDeletionPreviewResponse(
        sku_id=sku_id,
        sku_key=sku_row.sku_key if sku_row else "",
        sku_name=sku_row.sku_name if sku_row else None,
        current_status=sku_row.status if sku_row else "unknown",
        can_soft_delete=can_soft_delete,
        can_hard_delete=can_hard_delete,
        business_reference_count=total_refs,
        checks=checks,
        soft_delete_impact=soft_impact,
        blocked_reasons=[c.label + ": " + (c.detail or "") for c in blocked],
    )


@router.post("/api/skus/{sku_id}/soft-delete", response_model=SkuSoftDeleteResponse)
async def soft_delete_sku(
    sku_id: int,
    body: SkuSoftDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """停用 SKU:status='inactive',失效所有 active binding,写 audit。

    不需要硬删门槛(任意 SKU 可停用);数据全保留。
    """
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        raise HTTPException(status_code=404, detail=f"SKU id={sku_id} 不存在")
    if sku_row.status == "inactive":
        raise HTTPException(
            status_code=409, detail=f"SKU {sku_row.sku_key} 已是停用状态,请走恢复路径"
        )

    checks = await _check_sku_deletion_blockers(db, sku_id)
    blocked = [c for c in checks if c.status == "fail"]
    if blocked:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "sku_deletion_blocked",
                "blocked_checks": [c.model_dump() for c in blocked],
            },
        )

    previous_status = sku_row.status
    sku_row.status = "inactive"

    binding_result = await db.execute(
        update(BridgeSpuSku)
        .where(
            BridgeSpuSku.sku_id == sku_id,
            *current_binding_condition(),
        )
        .values(binding_status=INACTIVE_BINDING_STATUS, effective_to=date.today())
    )
    affected_bindings = binding_result.rowcount or 0

    await _write_product_center_audit(
        db,
        _user,
        action_type="sku_soft_delete",
        resource_type="sku",
        resource_id=str(sku_id),
        changes={
            "sku_key": sku_row.sku_key,
            "previous_status": previous_status,
            "new_status": "inactive",
            "affected_bindings": affected_bindings,
            "reason": body.reason,
            "warn_checks": [c.model_dump() for c in checks if c.status == "warn"],
        },
    )
    await db.commit()

    return SkuSoftDeleteResponse(
        sku_id=sku_id,
        sku_key=sku_row.sku_key,
        sku_name=sku_row.sku_name,
        previous_status=previous_status,
        new_status="inactive",
        affected_bindings=affected_bindings,
        soft_deleted_at=datetime.now(timezone.utc),
        audit_recorded=True,
    )


@router.post("/api/skus/{sku_id}/restore", response_model=SkuRestoreResponse)
async def restore_sku(
    sku_id: int,
    body: SkuRestoreRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """恢复 SKU:status='active',复活最早的 inactive binding(effective_to 清空),写 audit。

    策略:按 effective_to 升序找最早的 inactive binding,清空 effective_to + 改 binding_status='active'。
    其他历史 binding 保留(inactive 状态)以备追溯。
    """
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        raise HTTPException(status_code=404, detail=f"SKU id={sku_id} 不存在")
    if sku_row.status == "active":
        raise HTTPException(
            status_code=409, detail=f"SKU {sku_row.sku_key} 已是启用状态,无需恢复"
        )

    previous_status = sku_row.status
    sku_row.status = "active"

    # 找最早的 inactive binding 复活
    earliest_inactive = (
        await db.execute(
            select(BridgeSpuSku)
            .where(
                BridgeSpuSku.sku_id == sku_id,
                *archived_binding_condition(),
            )
            .order_by(BridgeSpuSku.effective_to.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    restored_bindings = 0
    if earliest_inactive is not None:
        earliest_inactive.binding_status = CURRENT_BINDING_STATUS
        earliest_inactive.effective_to = None
        restored_bindings = 1

    await _write_product_center_audit(
        db,
        _user,
        action_type="sku_restore",
        resource_type="sku",
        resource_id=str(sku_id),
        changes={
            "sku_key": sku_row.sku_key,
            "previous_status": previous_status,
            "new_status": "active",
            "restored_bindings": restored_bindings,
            "restored_binding_id": earliest_inactive.id if earliest_inactive else None,
            "reason": body.reason,
        },
    )
    await db.commit()

    return SkuRestoreResponse(
        sku_id=sku_id,
        sku_key=sku_row.sku_key,
        sku_name=sku_row.sku_name,
        previous_status=previous_status,
        new_status="active",
        restored_bindings=restored_bindings,
        restored_at=datetime.now(timezone.utc),
        audit_recorded=True,
    )


@router.post("/api/spus/bulk", response_model=SpuBulkMutationResponse)
async def bulk_save_spus(
    body: SpuBulkRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    requested_spus = [item.spu for item in body.items]
    if len(requested_spus) != len(set(requested_spus)):
        raise HTTPException(
            status_code=422, detail="bulk request cannot contain duplicate SPUs"
        )

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
                existing_category_l2_code=(
                    (row.category_l2_code or row.category_l2) if row else None
                ),
            )
            if row is None:
                if not values.get("spu_name"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"spu_name is required when creating {item.spu}",
                    )
                if not values.get("category_l2_code") and not values.get("category_l2"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"category_l2_code is required when creating {item.spu}",
                    )
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
                db,
                _user,
                action_type=action_type,
                resource_type="spu",
                resource_id=row.spu,
                changes=values,
            )
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="bulk SPU save conflicts with existing data"
        ) from exc
    asyncio.create_task(trigger_pending_projection_delivery())
    return SpuBulkMutationResponse(
        created=created,
        updated=updated,
        items=[SpuItem.model_validate(row) for row in rows],
    )


# ==================== SKU 定价底线：计算与注入 ====================
#
# 业务判断全部在 backend/services/product_pricing_service.py 的纯函数里，
# 这里只做「ORM 行 → 标量」的适配与批量取数。
#
# 取数与计算适配层的**唯一实现**在
# `backend/services/product_pricing_query_service.py`：
# - `_pricing_context` = 该模块的 `load_pricing_context`
# - `_compute_pricing_for_sku` = 该模块的 `compute_pricing_for_sku`
#
# 商品中心（这里）与最低售价变更通知（backend/services/price_adjust_notify_service.py）
# 共用同一份取数（规则行 / 平台费率 / 库龄）与同一个计算函数，
# 否则会出现「页面按日常档显示、通知却按滞销档发」的自相矛盾。
# 口径一致是**结构性保证**（同一个函数被两边调用），不是靠一条容易跳过的 DB 测试。


def _pricing_by_platform(context: dict, sku_row, linked_spu) -> dict[str, dict]:
    """**各可定价平台**各自的底线与人工覆盖（阶段 2.1b）。

    前端要「按平台分行」展示与编辑人工覆盖，就必须一次拿到所有可定价平台的数 ——
    列表接口一次只传一个 ``platform_code``，让前端发 N 次请求既慢又容易不一致。

    这里走的是**同一个**计算函数（``compute_pricing_state``），
    所以每一行的数字与「按该平台单独查一次」必然一致 —— 不存在第二份口径。
    """
    out: dict[str, dict] = {}
    for code in context.get("priceable_platform_codes") or []:
        pricing = _compute_pricing_state(
            context=context,
            sku_row=sku_row,
            linked_spu=linked_spu,
            platform_code=code,
        )["pricing"]
        out[code] = {
            "min_selling_price": pricing.get("min_selling_price"),
            "min_selling_price_override": pricing.get("min_selling_price_override"),
            "min_selling_price_source": pricing.get("min_selling_price_source"),
            "min_selling_price_is_override": pricing.get(
                "min_selling_price_is_override"
            ),
        }
    return out


async def _compute_sku_min_selling_price(
    db: AsyncSession, sku_id: int, platform_code: str | None = None
) -> Decimal | None:
    """单 SKU 在**指定平台**上的最低售价，供利润测算保存拦截复用。

    ⚠️ `platform_code` 决定用哪个平台的费率算底线 —— 不传就回落到历史 basis 平台，
    那会让 Shopee 拿 TikTok 的费率算底线（偏低三到七成）。
    """
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        return None
    binding = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku_id,
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .first()
    )
    linked_spu = await db.get(DimSpu, binding.spu) if binding else None
    context = await _pricing_context(
        db, [sku_id], [platform_code] if platform_code else None
    )
    payload = _compute_pricing_for_sku(
        context=context,
        sku_row=sku_row,
        linked_spu=linked_spu,
        platform_code=platform_code,
    )
    value = payload["min_selling_price"]
    return Decimal(str(value)) if value is not None else None


@router.get("/api/skus", response_model=SkuListResponse)
async def list_skus(
    keyword: str | None = Query(None),
    spu: str | None = Query(None),
    status: str | None = Query(
        None, description="按 SKU 状态过滤（active/inactive/...）；不传则不过滤"
    ),
    platform_code: str | None = Query(
        None,
        description="按哪个平台算定价底线（底线是 SKU × 平台的量）；不传则回落到历史 basis 平台",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            (DimErpSku.sku_key.ilike(pattern)) | (DimErpSku.sku_name.ilike(pattern))
        )
    if spu:
        filters.append(
            DimErpSku.sku_id.in_(
                select(BridgeSpuSku.sku_id).where(
                    BridgeSpuSku.spu == spu,
                    *current_binding_condition(),
                )
            )
        )
    if status:
        # 停用 SKU 与在售 SKU 之前是混排的，工具栏又没有状态筛选器，
        # 运营只能靠翻页找。dim_erp_sku.status 上有索引（ix_dim_erp_sku_status）。
        filters.append(DimErpSku.status == status)
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(DimErpSku).where(*filters)
            )
        ).scalar()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(DimErpSku)
                .where(*filters)
                .order_by(DimErpSku.sku_key)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    sku_ids = [row.sku_id for row in rows]
    bindings = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id.in_(sku_ids),
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .all()
        if sku_ids
        else []
    )
    binding_by_sku = {row.sku_id: row for row in bindings}
    spu_codes = [row.spu for row in bindings]
    spu_rows = (
        (await db.execute(select(DimSpu).where(DimSpu.spu.in_(spu_codes))))
        .scalars()
        .all()
        if spu_codes
        else []
    )
    spu_by_code = {row.spu: row for row in spu_rows}
    allocations = (
        (
            await db.execute(
                select(LogisticsBillLineAllocation, LogisticsBill.confirmed_at)
                .join(
                    LogisticsBillLine,
                    LogisticsBillLine.line_id
                    == LogisticsBillLineAllocation.bill_line_id,
                )
                .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
                .where(
                    LogisticsBillLineAllocation.sku_id.in_(sku_ids),
                    LogisticsBill.status == "confirmed",
                )
                .order_by(LogisticsBill.confirmed_at.desc())
            )
        ).all()
        if sku_ids
        else []
    )
    actual_logistics: dict[int, float] = {}
    for allocation, _confirmed_at in allocations:
        if allocation.sku_id not in actual_logistics and allocation.allocated_quantity:
            actual_logistics[allocation.sku_id] = float(
                allocation.allocated_amount / allocation.allocated_quantity
            )
    # 定价底线：一次取齐规则表 / 平台成本率 / 库龄，循环内只做纯计算
    # ⚠️ 底线是「SKU × 平台」的量 ⇒ 费率按传入的平台取；
    #    不传平台时回落到历史 basis 平台（前端应始终传平台）。
    pricing_context = await _pricing_context(
        db, [row.sku_id for row in rows], [platform_code] if platform_code else None
    )
    items = []
    for row in rows:
        payload = SkuItem.model_validate(row).model_dump()
        binding = binding_by_sku.get(row.sku_id)
        # 归属投影只从真源取（律 1）：spu + 归属生效日一起给出。
        # ⚠️ 少了「生效日」就等于把一段有时效的关联压扁成了一个字段 ——
        #    运营看不到这个货是什么时候挂到这个款上的。
        binding_projection = project_current_binding(binding)
        linked_spu = (
            spu_by_code.get(binding_projection["spu"])
            if binding_projection["spu"]
            else None
        )
        payload.update(
            {
                **binding_projection,
                # 归属款的名称：数据已经查出来了（linked_spu）⇒ 顺手给上，
                # 免得前端只看到一个编码，还得再查一次才知道挂的是哪个款。
                "spu_name": linked_spu.spu_name if linked_spu else None,
                "logistics_damage_rate": (
                    linked_spu.logistics_damage_rate if linked_spu else None
                ),
                "return_loss_rate": linked_spu.return_loss_rate if linked_spu else None,
                "actual_logistics_cost": actual_logistics.get(row.sku_id),
                "actual_storage_cost": None,
                "data_completeness": (
                    "complete"
                    if all(
                        value is not None
                        for value in (
                            row.default_purchase_cost,
                            row.expected_logistics_cost,
                            row.expected_storage_cost,
                            linked_spu.logistics_damage_rate if linked_spu else None,
                            linked_spu.return_loss_rate if linked_spu else None,
                        )
                    )
                    else "partial"
                ),
            }
        )
        payload.update(
            _compute_pricing_for_sku(
                context=pricing_context,
                sku_row=row,
                linked_spu=linked_spu,
                platform_code=platform_code,
            )
        )
        # 这条底线是按哪个平台的成本率算的（前端要显示，别让人误以为是 SKU 级的数）
        payload["min_selling_price_platform"] = _pricing_platform_code(
            pricing_context, platform_code
        )
        # 各可定价平台各自的底线与人工覆盖（阶段 2.1b：前端按平台分行）
        payload["min_selling_price_by_platform"] = _pricing_by_platform(
            pricing_context, row, linked_spu
        )
        # 阶段 4 工具 4 · 过期巡检：基准售价多久没确认了。
        # 纯计算，不查订单数据 ⇒ 列表接口零额外开销。
        # ⚠️ 只对**有基准售价**的 SKU 算：没有价格就没有「该确认什么」。
        if row.reference_selling_price is not None:
            age_days, stale = compute_selling_price_age(row.selling_price_confirmed_at)
            payload["selling_price_age_days"] = age_days
            payload["selling_price_stale"] = stale
        items.append(SkuItem(**payload))
    return SkuListResponse(
        data=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/api/skus", response_model=SkuItem, status_code=201)
async def create_sku(
    body: SkuCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    values = body.model_dump()
    # 阶段 4 工具 2：新建时填了基准售价 ⇒ 确认日期自动写当天。
    # ⚠️ `values` 是完整 dump（`selling_price_confirmed_at` 一定在里面，值为 None），
    #    所以「运营有没有显式给过确认日期」不能靠字典推断，要看 `exclude_unset` 的那份。
    apply_selling_price_confirmation(
        values,
        current_price=None,
        current_confirmed_at=None,
        confirmed_at_provided="selling_price_confirmed_at"
        in body.model_dump(exclude_unset=True),
    )
    row = DimErpSku(**values)
    db.add(row)
    try:
        await db.flush()
        await _enqueue_sku_projection(db, row)
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="sku",
            resource_id=str(row.sku_id),
            changes=_jsonable(values),
        )
        await db.commit()
        await db.refresh(row)
        asyncio.create_task(trigger_pending_projection_delivery())
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from exc
    return SkuItem.model_validate(row)


@router.patch("/api/skus/{sku_id}", response_model=SkuItem)
async def update_sku(
    sku_id: int,
    body: SkuUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = await db.get(DimErpSku, sku_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    values = body.model_dump(exclude_unset=True)
    # 阶段 4 工具 2：基准售价变了 ⇒ 确认日期自动跟着走（清空则一并清空）。
    apply_selling_price_confirmation(
        values,
        current_price=row.reference_selling_price,
        current_confirmed_at=row.selling_price_confirmed_at,
    )
    for key, value in values.items():
        setattr(row, key, value)
    await _enqueue_sku_projection(db, row)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="sku",
        resource_id=str(row.sku_id),
        # 审计记录**实际写入**的值（含自动写的确认日期），不是客户端原始请求体 ——
        # 否则事后看审计会以为确认日期是运营填的。
        changes=_jsonable(values),
    )
    await db.commit()
    await db.refresh(row)
    asyncio.create_task(trigger_pending_projection_delivery())
    return SkuItem.model_validate(row)


@router.post(
    "/api/skus/{sku_id}/selling-price-preview",
    response_model=SkuSellingPricePreviewResponse,
)
async def preview_sku_selling_price(
    sku_id: int,
    body: SkuSellingPricePreviewRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """**基准售价即时影响预览**（阶段 4 工具 3）。

    运营改基准售价时调用，返回「最低售价会从多少变成多少」。

    ⚠️ 这是**只读**的：不写库、不写审计。真正生效要等运营保存 SKU 主数据。
    ⚠️ 预览与保存走**同一个**定价函数（``compute_pricing_state``），
    所以「预览说涨到 63」与「保存后变成 63」必然一致。
    """
    row = await db.get(DimErpSku, sku_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    binding = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku_id,
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .first()
    )
    linked_spu = await db.get(DimSpu, binding.spu) if binding else None
    context = await _pricing_context(db, [sku_id])
    payload = build_selling_price_preview(
        context=context,
        sku_row=row,
        linked_spu=linked_spu,
        reference_selling_price=body.reference_selling_price,
    )
    return SkuSellingPricePreviewResponse(**payload)


@router.get(
    "/api/skus/selling-price-check", response_model=SkuSellingPriceCheckResponse
)
async def check_sku_selling_prices(
    sku_id: int | None = Query(
        None, description="只查某个 SKU；不传则查全部有基准售价的 SKU"
    ),
    include_deviation: bool = Query(
        True,
        description=(
            "是否算「与历史成交价的偏差」。关掉它就只做过期巡检（快）。"
            "⚠️ 打开它要扫订单事实表，一次调用要几十秒。"
        ),
    ),
    db: AsyncSession = Depends(get_async_db),
):
    """基准售价体检（阶段 4 工具 4）：偏差校验 + 过期巡检。

    - **过期巡检**：确认日期超过阈值（默认 90 天）⇒ ``stale``。
    - **偏差校验**：基准售价与历史成交价中位数偏差超过 30% ⇒ ``exceeds_threshold``。

    ⚠️ 算不出历史成交价的 SKU 会落在 ``unverified_count`` 里 ——
    **「算不出」不等于「没问题」**，前端要分开显示。
    """
    statement = select(DimErpSku).where(DimErpSku.reference_selling_price.isnot(None))
    if sku_id is not None:
        statement = statement.where(DimErpSku.sku_id == sku_id)
    rows = (await db.execute(statement.order_by(DimErpSku.sku_key))).scalars().all()

    bands: dict = {}
    if include_deviation and rows:
        bands = await load_transaction_price_bands(db, [row.sku_id for row in rows])

    items: list[SkuSellingPriceCheck] = []
    deviation_count = 0
    stale_count = 0
    unverified_count = 0
    for row in rows:
        age_days, stale = compute_selling_price_age(row.selling_price_confirmed_at)
        if stale:
            stale_count += 1
        band = bands.get(row.sku_id)
        deviation = assess_selling_price_deviation(
            row.reference_selling_price,
            band.get("median_price") if band else None,
        )
        if band:
            # 把「算这个偏差用的历史成交价」一并带出去 ——
            # 只给一个百分比，运营没法判断这个提示可不可信。
            deviation["median_price"] = float(band["median_price"])
            deviation["sample_size"] = band.get("sample_size")
            deviation["window_start"] = band.get("window_start")
            deviation["window_end"] = band.get("window_end")
        if deviation["available"]:
            if deviation["exceeds_threshold"]:
                deviation_count += 1
        else:
            unverified_count += 1
        items.append(
            SkuSellingPriceCheck(
                sku_id=row.sku_id,
                sku_key=row.sku_key,
                reference_selling_price=row.reference_selling_price,
                selling_price_source=row.selling_price_source,
                selling_price_confirmed_at=row.selling_price_confirmed_at,
                age_days=age_days,
                stale=stale,
                deviation=deviation,
            )
        )
    return SkuSellingPriceCheckResponse(
        items=items,
        deviation_count=deviation_count,
        stale_count=stale_count,
        unverified_count=unverified_count,
    )


@router.patch(
    "/api/skus/{sku_id}/pricing-override", response_model=SkuPricingOverrideResponse
)
async def set_sku_pricing_override(
    sku_id: int,
    body: SkuPricingOverrideRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    """设置 / 重置某 SKU 在**某个平台**上的最低售价人工覆盖（阶段 2.1b）。

    为什么是独立接口，而不是 SKU 主数据的保存字段：

    1. **口径**：人工覆盖是 SKU × 平台的量（底线就是 SKU × 平台的量）。
       挂在 SKU 主数据上只能存一个数，等于「一套覆盖值管所有平台」。
    2. **数据安全**：`core.dim_erp_sku` 参与「采集机 → 云端」同步，
       同步对它做 `TRUNCATE ... CASCADE` ⇒ 覆盖值每次同步都会被抹掉。
       覆盖值住在 `finance.sku_platform_pricing`（不参与同步，且刻意不带外键）。

    `min_selling_price_override` 传 **null** = 重置为自动值。
    """
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    platform = await db.get(DimPlatform, body.platform_code)
    if platform is None:
        raise BusinessValidationError(
            message=f"platform {body.platform_code} not found",
            detail={
                "code": "pricing_override_unknown_platform",
                "platform_code": body.platform_code,
            },
        )
    if platform.platform_role != "sales":
        raise BusinessValidationError(
            message=f"platform {body.platform_code} is not a sales platform",
            detail={
                "code": "pricing_override_platform_not_sales",
                "platform_code": body.platform_code,
            },
        )

    user_id = getattr(_user, "user_id", None)
    if body.min_selling_price_override is None:
        cleared = await clear_platform_override(
            db, sku_id=sku_id, platform_code=body.platform_code
        )
        await _write_product_center_audit(
            db,
            _user,
            action_type="update",
            resource_type="sku_pricing_override",
            resource_id=f"{sku_id}:{body.platform_code}",
            changes={"min_selling_price_override": None, "cleared": cleared},
        )
        await db.commit()
        return SkuPricingOverrideResponse(
            sku_id=sku_id,
            platform_code=body.platform_code,
            min_selling_price_override=None,
            min_selling_price_source=None,
            cleared=cleared,
        )

    row = await set_platform_override(
        db,
        sku_id=sku_id,
        platform_code=body.platform_code,
        value=body.min_selling_price_override,
        user_id=user_id,
    )
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="sku_pricing_override",
        resource_id=f"{sku_id}:{body.platform_code}",
        changes={
            "min_selling_price_override": float(row.min_selling_price_override),
            "min_selling_price_source": row.min_selling_price_source,
        },
    )
    await db.commit()
    return SkuPricingOverrideResponse(
        sku_id=sku_id,
        platform_code=body.platform_code,
        min_selling_price_override=float(row.min_selling_price_override),
        min_selling_price_source=row.min_selling_price_source,
        cleared=False,
    )


def _assert_spu_assignable(spu_row: DimSpu) -> None:
    """「这个 SPU 现在还能不能挂新 SKU」—— 口径来自真源，不在这里重写一遍。

    ⚠️ 判定**只有一个来源**（``backend/services/product_spu_lifecycle.py``）——
       值域端点的候选集与本处校验引用的是同一份口径 ⇒ 不会出现
       「下拉里能选、保存时被拒」。

    ⚠️ 依赖建模 A 的不变量（``active=false ⟹ biz_status='retired'``）：
       已删除的款必然是 ``retired`` ⇒ 只看 ``biz_status`` 就够排除它们。
       该不变量由 ``dim_spu`` 的 ``CHECK`` 约束在数据库层兜底。
    """
    if not is_spu_assignable(spu_row):
        raise HTTPException(
            status_code=422,
            detail=(
                f"SPU {spu_row.spu} 已淘汰或已删除，不能绑定新 SKU"
                "（如需使用，请先在 SPU 管理里恢复或改回在营状态）"
            ),
        )


async def _apply_bulk_sku_spu_binding(
    db: AsyncSession, sku: DimErpSku, spu: str | None, effective_from: date | None
) -> None:
    """把「这个货挂到这个款上」写下去。

    ⚠️ **只有真的换款时才校验新款能不能挂货** ——
       否则一个挂在**已淘汰款**下的 SKU，运营只想改个重量，
       保存时却收到 422「SPU X 已淘汰或已删除，不能绑定新 SKU」：
       报错与他做的事毫无关系，而且无从绕过。
       ⇒ 先看归属有没有变，没变就原样返回。
    """
    if not spu:
        return

    binding = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku.sku_id,
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .first()
    )
    if binding is not None and binding.spu == spu:
        # 归属没变 ⇒ 什么都不用写（也不该因为「这个款现在不能挂货」而拦下这次保存）
        return

    spu_row = await db.get(DimSpu, spu)
    if spu_row is None:
        raise HTTPException(status_code=422, detail=f"SPU {spu} does not exist")
    _assert_spu_assignable(spu_row)

    starts_on = effective_from or date.today()
    if binding is not None:
        # ⚠️ 只能改到**当前绑定生效日之后或当天**：
        #    改到过去 = 篡改历史。
        #    同一天是允许的 —— 那是「今天的挂错了，当天纠正」，
        #    不是改历史（否则运营改不了今天刚建的绑定，且没有任何补救路径）。
        if starts_on < binding.effective_from:
            raise HTTPException(
                status_code=422,
                detail="effective_from must be later than the current SPU binding",
            )
        binding.effective_to = starts_on
        # 换款归档 = **历史证据**（不可复活）⇒ 与「软删封存（可复活）」分开。
        binding.binding_status = HISTORICAL_BINDING_STATUS
    db.add(BridgeSpuSku(spu=spu, sku_id=sku.sku_id, effective_from=starts_on))


@router.post("/api/skus/bulk", response_model=SkuBulkMutationResponse)
async def bulk_save_skus(
    body: SkuBulkRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    supplied_ids = [item.sku_id for item in body.items if item.sku_id is not None]
    supplied_keys = [item.sku_key for item in body.items]
    if len(supplied_ids) != len(set(supplied_ids)) or len(supplied_keys) != len(
        set(supplied_keys)
    ):
        raise HTTPException(
            status_code=422,
            detail="bulk request cannot contain duplicate SKU identifiers",
        )

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
                    (
                        await db.execute(
                            select(DimErpSku).where(DimErpSku.sku_key == item.sku_key)
                        )
                    )
                    .scalars()
                    .first()
                )
            # 阶段 4 工具 2：批量保存同样自动维护确认日期。
            apply_selling_price_confirmation(
                values,
                current_price=row.reference_selling_price if row is not None else None,
                current_confirmed_at=(
                    row.selling_price_confirmed_at if row is not None else None
                ),
            )
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
            row_actions.append(
                (row, action_type, {**values, **({"spu": spu} if spu else {})})
            )
        await db.flush()
        for row in rows:
            await _enqueue_sku_projection(db, row)
        for row, action_type, values in row_actions:
            await _write_product_center_audit(
                db,
                _user,
                action_type=action_type,
                resource_type="sku",
                resource_id=str(row.sku_id),
                changes=values,
            )
        await db.commit()
        for row in rows:
            await db.refresh(row)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="bulk SKU save conflicts with existing data"
        ) from exc
    asyncio.create_task(trigger_pending_projection_delivery())
    return SkuBulkMutationResponse(
        created=created,
        updated=updated,
        items=[SkuItem.model_validate(row) for row in rows],
    )


@router.get("/api/spus/{spu}/skus", response_model=list[ProductCenterBindingResponse])
async def list_spu_skus(spu: str, db: AsyncSession = Depends(get_async_db)):
    rows = (
        (
            await db.execute(
                select(BridgeSpuSku)
                .where(BridgeSpuSku.spu == spu)
                .order_by(BridgeSpuSku.effective_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return [ProductCenterBindingResponse.model_validate(row) for row in rows]


@router.post(
    "/api/spus/{spu}/skus", response_model=ProductCenterBindingResponse, status_code=201
)
async def bind_spu_sku(
    spu: str,
    body: SpuSkuBindingRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_editor),
):
    spu_row = await db.get(DimSpu, spu)
    if spu_row is None:
        raise HTTPException(status_code=404, detail="SPU not found")
    # 「SKU 归属」抽屉里的绑定入口与批量保存**守同一条规则**：
    # 已淘汰 / 已删除的款不能接新 SKU。
    _assert_spu_assignable(spu_row)
    if await db.get(DimErpSku, body.sku_id) is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    current_binding = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == body.sku_id,
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .first()
    )
    if (
        current_binding is not None
        and body.effective_from < current_binding.effective_from
    ):
        # ⚠️ 改到**过去**才拒绝（篡改历史）；
        #    同一天允许 —— 那是「今天挂错了，当天纠正」。
        raise HTTPException(
            status_code=422,
            detail="effective_from must be later than the current binding",
        )
    await db.execute(
        update(BridgeSpuSku)
        .where(
            BridgeSpuSku.sku_id == body.sku_id,
            *current_binding_condition(),
        )
        .values(
            effective_to=body.effective_from,
            binding_status=HISTORICAL_BINDING_STATUS,
        )
    )
    row = BridgeSpuSku(
        spu=spu,
        sku_id=body.sku_id,
        effective_from=body.effective_from,
        created_by=getattr(current_user, "user_id", None),
    )
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
                    "binding_status": HISTORICAL_BINDING_STATUS,
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
        raise HTTPException(
            status_code=409, detail="SKU binding conflicts with an active assignment"
        ) from exc
    return ProductCenterBindingResponse.model_validate(row)


@router.get("/api/purchase-orders")
async def list_purchase_orders(
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    statement = select(POHeader).order_by(
        POHeader.po_date.desc(), POHeader.po_id.desc()
    )
    if status:
        statement = statement.where(POHeader.status == status)
    if keyword:
        statement = statement.where(POHeader.po_id.ilike(f"%{keyword}%"))
    rows = (await db.execute(statement.limit(500))).scalars().all()
    po_ids = [row.po_id for row in rows]
    if not po_ids:
        return []
    warehouse_rows = (
        await db.execute(
            select(GRNHeader.po_id, GRNHeader.warehouse)
            .where(GRNHeader.po_id.in_(po_ids), GRNHeader.warehouse.is_not(None))
            .distinct()
        )
    ).all()
    warehouses_by_po: dict[str, list[str]] = {}
    for related_po_id, warehouse in warehouse_rows:
        warehouses_by_po.setdefault(related_po_id, []).append(warehouse)
    line_rows = (
        await db.execute(
            select(
                POLine.po_id,
                func.count(POLine.po_line_id),
                func.coalesce(func.sum(POLine.qty_ordered), 0),
                func.coalesce(func.sum(POLine.qty_received), 0),
            )
            .where(POLine.po_id.in_(po_ids))
            .group_by(POLine.po_id)
        )
    ).all()
    line_totals = {
        po_id: (count, ordered, received)
        for po_id, count, ordered, received in line_rows
    }
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
async def list_purchase_order_lines(
    po_id: str, db: AsyncSession = Depends(get_async_db)
):
    rows = (
        (
            await db.execute(
                select(POLine).where(POLine.po_id == po_id).order_by(POLine.line_number)
            )
        )
        .scalars()
        .all()
    )
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
async def supplement_purchase_order_line_cost(
    po_id: str,
    po_line_id: int,
    body: PurchaseOrderLineCostSupplementRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = (
        (
            await db.execute(
                select(POLine).where(
                    POLine.po_id == po_id, POLine.po_line_id == po_line_id
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="purchase order line not found")
    row.unit_price = body.unit_price
    row.line_amt = float(body.unit_price) * float(row.qty_ordered or 0)
    row.currency = "CNY"
    row.purchase_cost_source = body.purchase_cost_source
    row.purchase_cost_confirmed_at = datetime.now(timezone.utc)
    canonical_sku = (
        (
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
        )
        .scalars()
        .first()
    )
    if canonical_sku is not None:
        canonical_sku.default_purchase_cost = body.unit_price
        canonical_sku.purchase_cost_currency = (
            row.currency or canonical_sku.purchase_cost_currency
        )
        canonical_sku.purchase_cost_source = "purchase_order"
        canonical_sku.purchase_cost_confirmed_at = row.purchase_cost_confirmed_at
        await _enqueue_sku_projection(db, canonical_sku)
    await _write_product_center_audit(
        db,
        _user,
        action_type="supplement_purchase_cost",
        resource_type="purchase_order_line",
        resource_id=f"{po_id}:{po_line_id}",
        changes={
            "po_id": po_id,
            "po_line_id": po_line_id,
            "purchase_cost_source": body.purchase_cost_source,
            "currency": "CNY",
        },
    )
    await db.commit()
    await db.refresh(row)
    return {
        "po_line_id": row.po_line_id,
        "unit_price": row.unit_price,
        "currency": row.currency,
        "line_amt": row.line_amt,
        "purchase_cost_source": row.purchase_cost_source,
        "purchase_cost_confirmed_at": row.purchase_cost_confirmed_at,
    }


@router.get("/api/purchase-orders/{po_id}")
async def get_purchase_order(po_id: str, db: AsyncSession = Depends(get_async_db)):
    row = await db.get(POHeader, po_id)
    if row is None:
        raise HTTPException(status_code=404, detail="purchase order not found")
    return {
        "po_id": row.po_id,
        "vendor_code": row.vendor_code,
        "po_date": row.po_date,
        "expected_date": row.expected_date,
        "currency": row.currency,
        "total_amt": row.total_amt,
        "status": row.status,
    }


def _serialize_provider_rule(row: LogisticsProviderRule) -> dict:
    return {
        "rule_id": row.rule_id,
        "logistics_provider": row.logistics_provider,
        "warehouse_code": row.warehouse_code,
        "transport_type": row.transport_type,
        "cargo_class": row.cargo_class,
        "is_sensitive": row.is_sensitive,
        "is_default": row.is_default,
        "billing_basis": row.billing_basis,
        "billing_unit": row.billing_unit,
        "freight_unit_rate": (
            float(row.freight_unit_rate) if row.freight_unit_rate is not None else None
        ),
        "sensitive_surcharge_mode": row.sensitive_surcharge_mode,
        "sensitive_surcharge_rate": (
            float(row.sensitive_surcharge_rate)
            if row.sensitive_surcharge_rate is not None
            else None
        ),
        "currency": row.currency,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "status": row.status,
        "source": row.source,
        "version": row.version,
        "notes": row.notes,
    }


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
    statement = (
        select(LogisticsProviderRule)
        .where(
            LogisticsProviderRule.is_default.is_(True),
            LogisticsProviderRule.status == "active",
            _same_nullable_scope(
                LogisticsProviderRule.warehouse_code, values.get("warehouse_code")
            ),
            _same_nullable_scope(
                LogisticsProviderRule.transport_type, values.get("transport_type")
            ),
            _same_nullable_scope(
                LogisticsProviderRule.cargo_class, values.get("cargo_class")
            ),
            LogisticsProviderRule.is_sensitive == values.get("is_sensitive", False),
        )
        .with_for_update()
    )
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
async def list_logistics_provider_rules(
    provider: str | None = Query(None),
    warehouse_code: str | None = Query(None),
    transport_type: str | None = Query(None),
    as_of: date | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
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
    filters.extend(
        [
            LogisticsProviderRule.effective_from <= when,
            (LogisticsProviderRule.effective_to.is_(None))
            | (LogisticsProviderRule.effective_to >= when),
        ]
    )
    rows = (
        (
            await db.execute(
                select(LogisticsProviderRule)
                .where(*filters)
                .order_by(LogisticsProviderRule.effective_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_provider_rule(row) for row in rows]


@router.post("/api/logistics-provider-rules", status_code=201)
async def create_logistics_provider_rule(
    body: LogisticsProviderRuleCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    if body.warehouse_code and await db.get(DimWarehouse, body.warehouse_code) is None:
        raise HTTPException(status_code=422, detail="warehouse not found")
    await _ensure_unambiguous_default_provider_rule(db, body.model_dump())
    row = LogisticsProviderRule(**body.model_dump(), currency="CNY")
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="logistics_provider_rule",
            resource_id=str(row.rule_id),
            changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="logistics provider rule already exists"
        ) from exc
    return _serialize_provider_rule(row)


@router.patch("/api/logistics-provider-rules/{rule_id}")
async def update_logistics_provider_rule(
    rule_id: int,
    body: LogisticsProviderRuleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = await db.get(LogisticsProviderRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="logistics provider rule not found")
    values = body.model_dump(exclude_unset=True)
    if (
        values.get("warehouse_code")
        and await db.get(DimWarehouse, values["warehouse_code"]) is None
    ):
        raise HTTPException(status_code=422, detail="warehouse not found")
    candidate = {
        field: getattr(row, field)
        for field in (
            "warehouse_code",
            "transport_type",
            "cargo_class",
            "is_sensitive",
            "is_default",
            "effective_from",
            "effective_to",
            "status",
        )
    }
    candidate.update(values)
    await _ensure_unambiguous_default_provider_rule(
        db, candidate, excluding_rule_id=row.rule_id
    )
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="logistics_provider_rule",
        resource_id=str(row.rule_id),
        changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return _serialize_provider_rule(row)


@router.delete("/api/logistics-provider-rules/{rule_id}", status_code=204)
async def delete_logistics_provider_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = await db.get(LogisticsProviderRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="logistics provider rule not found")
    await _write_product_center_audit(
        db,
        _user,
        action_type="delete",
        resource_type="logistics_provider_rule",
        resource_id=str(rule_id),
        changes={
            "logistics_provider": row.logistics_provider,
            "warehouse_code": row.warehouse_code,
            "transport_type": row.transport_type,
            "cargo_class": row.cargo_class,
            "is_default": row.is_default,
            "billing_basis": row.billing_basis,
            "freight_unit_rate": (
                float(row.freight_unit_rate)
                if row.freight_unit_rate is not None
                else None
            ),
            "effective_from": (
                row.effective_from.isoformat() if row.effective_from else None
            ),
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            "status": row.status,
        },
    )
    await db.delete(row)
    await db.commit()


@router.get("/api/cost-assumption-profiles")
async def list_cost_assumptions(db: AsyncSession = Depends(get_async_db)):
    rows = (
        (
            await db.execute(
                select(ProductCostAssumptionProfile)
                .where(ProductCostAssumptionProfile.active.is_(True))
                .order_by(ProductCostAssumptionProfile.effective_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "profile_id": row.profile_id,
            "profile_name": row.profile_name,
            "destination": row.destination,
            "transport_type": row.transport_type,
            "billing_basis": row.billing_basis,
            "freight_unit_rate": (
                float(row.freight_unit_rate)
                if row.freight_unit_rate is not None
                else None
            ),
            "storage_unit_rate": (
                float(row.storage_unit_rate)
                if row.storage_unit_rate is not None
                else None
            ),
            "platform_fee_rate": (
                float(row.platform_fee_rate)
                if row.platform_fee_rate is not None
                else None
            ),
            "return_rate": (
                float(row.return_rate) if row.return_rate is not None else None
            ),
            "damage_rate": (
                float(row.damage_rate) if row.damage_rate is not None else None
            ),
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "assumption_source": row.assumption_source,
            "confidence_level": row.confidence_level,
        }
        for row in rows
    ]


@router.post("/api/cost-assumption-profiles", status_code=201)
async def create_cost_assumption(
    body: CostAssumptionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = ProductCostAssumptionProfile(**body.model_dump())
    db.add(row)
    await db.flush()
    await FeishuProjectionService(db).enqueue_full_refresh("cost_assumption_created")
    await _write_product_center_audit(
        db,
        _user,
        action_type="create",
        resource_type="cost_assumption_profile",
        resource_id=str(row.profile_id),
        changes=body.model_dump(mode="json"),
    )
    await db.commit()
    asyncio.create_task(trigger_pending_projection_delivery())
    await db.refresh(row)
    return {
        "profile_id": row.profile_id,
        "profile_name": row.profile_name,
        "effective_from": row.effective_from,
    }


@router.patch("/api/cost-assumption-profiles/{profile_id}")
async def update_cost_assumption(
    profile_id: int,
    body: CostAssumptionUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = await db.get(ProductCostAssumptionProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="cost assumption profile not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await FeishuProjectionService(db).enqueue_full_refresh("cost_assumption_changed")
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="cost_assumption_profile",
        resource_id=str(row.profile_id),
        changes=body.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    asyncio.create_task(trigger_pending_projection_delivery())
    return {
        "profile_id": row.profile_id,
        "active": row.active,
        "updated_at": row.updated_at,
    }


def _serialize_bill(
    bill: LogisticsBill,
    lines: list[LogisticsBillLine] | None = None,
    purchase_orders: list[LogisticsBillPurchaseOrder] | None = None,
    allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] | None = None,
) -> dict:
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
                "billing_unit_rate": (
                    float(line.billing_unit_rate)
                    if line.billing_unit_rate is not None
                    else None
                ),
                "is_sensitive": line.is_sensitive,
                "sensitive_surcharge": float(line.sensitive_surcharge or 0),
                "shipped_qty": float(line.shipped_qty or 0),
                "calculated_total_weight_kg": float(
                    line.calculated_total_weight_kg or 0
                ),
                "calculated_total_volume_cbm": float(
                    line.calculated_total_volume_cbm or 0
                ),
                "actual_total_weight_kg": (
                    float(line.actual_total_weight_kg)
                    if line.actual_total_weight_kg is not None
                    else None
                ),
                "actual_total_volume_cbm": (
                    float(line.actual_total_volume_cbm)
                    if line.actual_total_volume_cbm is not None
                    else None
                ),
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
async def list_product_warehouses(
    include_inactive: bool = Query(False), db: AsyncSession = Depends(get_async_db)
):
    statement = select(DimWarehouse).order_by(
        DimWarehouse.country_code, DimWarehouse.warehouse_code
    )
    if not include_inactive:
        statement = statement.where(DimWarehouse.status == "active")
    rows = (await db.execute(statement)).scalars().all()
    return [
        {
            "warehouse_code": row.warehouse_code,
            "warehouse_name": row.warehouse_name,
            "country_code": row.country_code,
            "country_name": row.country_name,
            "region": row.region,
            "status": row.status,
        }
        for row in rows
    ]


def _serialize_storage_rule(row: WarehouseStorageRule) -> dict:
    return {
        "rule_id": row.rule_id,
        "warehouse_code": row.warehouse_code,
        "billing_basis": row.billing_basis,
        "billing_unit": row.billing_unit,
        "unit_rate_cny": float(row.unit_rate_cny),
        "label_fee": float(row.label_fee) if row.label_fee is not None else None,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "status": row.status,
        "source": row.source,
        "version": row.version,
        "notes": row.notes,
    }


@router.get("/api/warehouse-storage-rules")
async def list_warehouse_storage_rules(
    warehouse_code: str | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_async_db),
):
    filters = []
    if warehouse_code:
        filters.append(WarehouseStorageRule.warehouse_code == warehouse_code)
    if not include_inactive:
        filters.append(WarehouseStorageRule.status == "active")
    rows = (
        (
            await db.execute(
                select(WarehouseStorageRule)
                .where(*filters)
                .order_by(
                    WarehouseStorageRule.warehouse_code,
                    WarehouseStorageRule.effective_from.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_storage_rule(row) for row in rows]


@router.post("/api/warehouse-storage-rules", status_code=201)
async def create_warehouse_storage_rule(
    body: WarehouseStorageRuleCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    warehouse = (
        (
            await db.execute(
                select(DimWarehouse)
                .where(DimWarehouse.warehouse_code == body.warehouse_code)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if warehouse is None:
        raise HTTPException(status_code=422, detail="warehouse not found")
    if body.status == "active":
        active_rules = (
            (
                await db.execute(
                    select(WarehouseStorageRule)
                    .where(
                        WarehouseStorageRule.warehouse_code == body.warehouse_code,
                        WarehouseStorageRule.status == "active",
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
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
                raise HTTPException(
                    status_code=409,
                    detail="storage rule effective window overlaps an active historical rule",
                )
            if body.effective_from <= existing_rule.effective_from:
                raise HTTPException(
                    status_code=409,
                    detail="new storage rule effective_from must be later than the current rule",
                )
            current_rule = existing_rule
            current_rule.effective_to = body.effective_from - timedelta(days=1)
    row = WarehouseStorageRule(
        **body.model_dump(), billing_basis="volume", billing_unit="CNY/CBM/month"
    )
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="warehouse_storage_rule",
            resource_id=str(row.rule_id),
            changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="active storage rule already exists"
        ) from exc
    return _serialize_storage_rule(row)


@router.patch("/api/warehouse-storage-rules/{rule_id}")
async def update_warehouse_storage_rule(
    rule_id: int,
    body: WarehouseStorageRuleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
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
            raise HTTPException(
                status_code=409,
                detail="inactive storage rules cannot be versioned; create a new storage rule",
            )
        next_effective_from = values.get("effective_from") or date.today()
        if next_effective_from <= row.effective_from:
            next_effective_from = date.today()
        if next_effective_from <= row.effective_from:
            raise HTTPException(
                status_code=409,
                detail="new storage rule effective_from must be later than the current rule",
            )
        if (
            values.get("effective_to") is not None
            and values["effective_to"] < next_effective_from
        ):
            raise HTTPException(
                status_code=422,
                detail="effective_to must not be earlier than effective_from",
            )
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
            db,
            _user,
            action_type="storage_rule_versioned",
            resource_type="warehouse_storage_rule",
            resource_id=str(next_rule.rule_id),
            changes={"previous_rule_id": row.rule_id, **values},
        )
        await db.commit()
        await db.refresh(next_rule)
        return _serialize_storage_rule(next_rule)
    for key, value in values.items():
        setattr(row, key, value)
    try:
        await _write_product_center_audit(
            db,
            _user,
            action_type="update",
            resource_type="warehouse_storage_rule",
            resource_id=str(row.rule_id),
            changes=body.model_dump(mode="json", exclude_unset=True),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="active storage rule already exists"
        ) from exc
    return _serialize_storage_rule(row)


@router.delete("/api/warehouse-storage-rules/{rule_id}", status_code=204)
async def delete_warehouse_storage_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    row = await db.get(WarehouseStorageRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="warehouse storage rule not found")
    await _write_product_center_audit(
        db,
        _user,
        action_type="delete",
        resource_type="warehouse_storage_rule",
        resource_id=str(rule_id),
        changes={
            "warehouse_code": row.warehouse_code,
            "version": row.version,
            "status": row.status,
            "unit_rate_cny": float(row.unit_rate_cny),
        },
    )
    await db.delete(row)
    await db.commit()


@router.post("/api/product-warehouses", status_code=201)
async def create_product_warehouse(
    body: ProductWarehouseCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = DimWarehouse(**body.model_dump())
    db.add(row)
    try:
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="warehouse",
            resource_id=row.warehouse_code,
            changes=body.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="warehouse code already exists"
        ) from exc
    return {
        "warehouse_code": row.warehouse_code,
        "warehouse_name": row.warehouse_name,
        "country_code": row.country_code,
        "country_name": row.country_name,
        "region": row.region,
        "status": row.status,
    }


@router.patch("/api/product-warehouses/{warehouse_code}")
async def update_product_warehouse(
    warehouse_code: str,
    body: ProductWarehouseUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = await db.get(DimWarehouse, warehouse_code)
    if row is None:
        raise HTTPException(status_code=404, detail="warehouse not found")
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="warehouse",
        resource_id=row.warehouse_code,
        changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return {
        "warehouse_code": row.warehouse_code,
        "warehouse_name": row.warehouse_name,
        "country_code": row.country_code,
        "country_name": row.country_name,
        "region": row.region,
        "status": row.status,
    }


# ==================== SKU 定价纪律规则（库龄档位） ====================
#
# 「当前行」谓词只有这一处定义，GET /current 与服务端选档逻辑共用，
# 禁止在两处各写一份（否则 /current 列出的规则与护栏实际生效的规则会不一致）。
#
#   当前行 = status='active' AND effective_to IS NULL AND effective_from <= 今日
#
# 用 `effective_to IS NULL` 而不是 `effective_to IS NULL OR effective_to > 今日`：
# 后者会把「已关闭但关闭日期在未来」的行也算进来，规则集合与实际生效的集合就分家了。


def _policy_current_predicate():
    # 谓词的唯一来源在 backend/services/sku_pricing_policy_service.py：
    # 商品中心与 SKU 级滞销清单共用同一组条件，避免两边口径分叉。
    return policy_current_predicate()


async def _current_policies(db: AsyncSession) -> list[SkuPricingPolicy]:
    return await load_current_policies(db)


@router.get("/api/sku-pricing-policies", response_model=list[SkuPricingPolicyResponse])
async def list_sku_pricing_policies(db: AsyncSession = Depends(get_async_db)):
    """返回全部规则行（含历史），按档位起点、生效日期排序。"""
    rows = (
        (
            await db.execute(
                select(SkuPricingPolicy).order_by(
                    SkuPricingPolicy.min_restock_days, SkuPricingPolicy.effective_from
                )
            )
        )
        .scalars()
        .all()
    )
    return [SkuPricingPolicyResponse.model_validate(row) for row in rows]


@router.get(
    "/api/sku-pricing-policies/current", response_model=list[SkuPricingPolicyResponse]
)
async def list_current_sku_pricing_policies(db: AsyncSession = Depends(get_async_db)):
    """返回当前生效的规则行。筛选条件与选档逻辑共用同一组谓词。"""
    rows = await _current_policies(db)
    return [SkuPricingPolicyResponse.model_validate(row) for row in rows]


@router.post(
    "/api/sku-pricing-policies",
    response_model=SkuPricingPolicyResponse,
    status_code=201,
)
async def create_sku_pricing_policy(
    body: SkuPricingPolicyCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    if body.effective_from > date.today():
        raise BusinessValidationError(
            message=POLICY_REJECT_FUTURE,
            detail={
                "code": "pricing_policy_future_effective_from",
                "reason": POLICY_REJECT_FUTURE,
            },
        )
    existing = (
        (
            await db.execute(
                select(SkuPricingPolicy).where(
                    SkuPricingPolicy.min_restock_days == body.min_restock_days,
                    *_policy_current_predicate(),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise ConflictError(
            message="该库龄档位已有生效规则，请先修改现有规则",
            detail={
                "code": "pricing_policy_tier_exists",
                "reason": "该库龄档位已有生效规则，请先修改现有规则",
            },
        )
    row = SkuPricingPolicy(**body.model_dump())
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            message="该库龄起点已被其它档位占用，请改用空闲起点",
            detail={
                "code": "pricing_policy_conflict",
                "reason": "该库龄起点已被其它档位占用，请改用空闲起点",
            },
        ) from exc
    await _write_product_center_audit(
        db,
        _user,
        action_type="create",
        resource_type="sku_pricing_policy",
        resource_id=str(row.policy_id),
        changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return SkuPricingPolicyResponse.model_validate(row)


@router.put(
    "/api/sku-pricing-policies/{min_restock_days}",
    response_model=SkuPricingPolicyResponse,
)
async def update_sku_pricing_policy(
    min_restock_days: int,
    body: SkuPricingPolicyUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    """路径参数 = 被编辑的档位（旧起点），body 的 min_restock_days = 该档位的新起点。

    两者不同 = 运营在改库龄档位的边界（改这一格就改了滞销阈值），不是调用方搞混。

    「四路径判定」在纯函数 `resolve_policy_update` 里（`backend/services/product_pricing_service.py`），
    路由只负责取数、落库、审计。
    """
    current = (
        (
            await db.execute(
                select(SkuPricingPolicy)
                .where(
                    SkuPricingPolicy.min_restock_days == min_restock_days,
                    *_policy_current_predicate(),
                )
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if current is None:
        raise HTTPException(status_code=404, detail="pricing policy tier not found")

    current_data = {
        "min_restock_days": current.min_restock_days,
        "effective_from": current.effective_from,
    }
    try:
        decision = resolve_policy_update(
            current=current_data,
            requested=body.model_dump(exclude_unset=True),
            today=date.today(),
        )
    except PolicyUpdateRejected as exc:
        raise BusinessValidationError(
            message=str(exc),
            detail={
                "code": "pricing_policy_update_rejected",
                "reason": str(exc),
            },
        ) from exc

    action = decision["action"]
    if action == "update":
        for key, value in decision["values"].items():
            setattr(current, key, value)
        row = current
    else:
        # 关旧行 + 建新行（改边界或跨期）
        current.effective_to = decision["close_current"]
        current.status = "inactive"
        values = dict(decision["values"])
        # 保留旧行的来源标记，避免把迁移灌的 source='industry_benchmark_2026' 覆盖成 None
        values.setdefault("source", current.source)
        values.setdefault("version", current.version)
        # 备注同理：新行没显式写 notes 时继承旧行，否则关档留痕后备注凭空消失
        values.setdefault("notes", current.notes)
        values["status"] = "active"
        row = SkuPricingPolicy(**values)
        db.add(row)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # 409 也走 ConflictError：全局异常处理器会把 HTTPException 的 detail
        # 拍平成字符串，前端就拿不到结构化的 code / reason 了
        raise ConflictError(
            message="该库龄起点已被其它档位占用，请改用空闲起点",
            detail={
                "code": "pricing_policy_conflict",
                "reason": "该库龄起点已被其它档位占用，请改用空闲起点",
            },
        ) from exc
    await _write_product_center_audit(
        db,
        _user,
        action_type=action,
        resource_type="sku_pricing_policy",
        resource_id=str(row.policy_id),
        changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return SkuPricingPolicyResponse.model_validate(row)


@router.patch(
    "/api/platforms/{platform_code}/fee-rate", response_model=PlatformFeeRateResponse
)
async def update_platform_fee_rate(
    platform_code: str,
    body: PlatformFeeRateUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    row = await db.get(DimPlatform, platform_code)
    if row is None:
        raise HTTPException(status_code=404, detail="platform not found")
    if row.platform_role != "sales":
        raise HTTPException(
            status_code=409,
            detail="platform fee rates can only be maintained for sales platforms",
        )
    # 「未传则保持原值」：抽屉里只改「达人佣金率」时，
    # 无条件赋值会把 default_fee_rate 写成 NULL、fee_rate_effective_from 刷成当天
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="platform_fee_rate",
        resource_id=row.platform_code,
        changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return {
        "platform_code": row.platform_code,
        "default_fee_rate": row.default_fee_rate,
        "default_creator_commission_rate": row.default_creator_commission_rate,
        "other_cost_rate": row.other_cost_rate,
        "fee_rate_effective_from": row.fee_rate_effective_from,
        "fee_rate_source": row.fee_rate_source,
        "fee_rate_version": row.fee_rate_version,
    }


@router.get("/api/logistics-bills")
async def list_logistics_bills(
    status: str | None = Query(None), db: AsyncSession = Depends(get_async_db)
):
    statement = select(LogisticsBill).order_by(
        LogisticsBill.bill_date.desc(), LogisticsBill.bill_id.desc()
    )
    if status:
        statement = statement.where(LogisticsBill.status == status)
    rows = (await db.execute(statement)).scalars().all()
    return [_serialize_bill(row) for row in rows]


@router.get("/api/logistics-batches")
async def list_logistics_batches(
    status: str | None = Query(None), db: AsyncSession = Depends(get_async_db)
):
    """Current product-center name for logistics bill batches."""
    return await list_logistics_bills(status=status, db=db)


@router.post("/api/logistics-bills", status_code=201)
async def create_logistics_bill(
    body: LogisticsBillCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    row = LogisticsBill(**body.model_dump(), status="draft")
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="logistics_bill",
            resource_id=str(row.bill_id),
            changes={"bill_no": row.bill_no, "status": row.status},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="logistics bill number already exists"
        ) from exc
    return _serialize_bill(row, [])


@router.post("/api/logistics-batches", status_code=201)
async def create_logistics_batch(
    body: LogisticsBillCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    return await create_logistics_bill(body=body, db=db, _user=_user)


@router.get("/api/logistics-bills/{bill_id}")
async def get_logistics_bill(bill_id: int, db: AsyncSession = Depends(get_async_db)):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lines = (
        (
            await db.execute(
                select(LogisticsBillLine)
                .where(LogisticsBillLine.bill_id == bill_id)
                .order_by(LogisticsBillLine.line_no)
            )
        )
        .scalars()
        .all()
    )
    purchase_orders = (
        (
            await db.execute(
                select(LogisticsBillPurchaseOrder).where(
                    LogisticsBillPurchaseOrder.bill_id == bill_id
                )
            )
        )
        .scalars()
        .all()
    )
    allocations = (
        (
            await db.execute(
                select(LogisticsBillLineAllocation).where(
                    LogisticsBillLineAllocation.bill_line_id.in_(
                        [line.line_id for line in lines]
                    )
                )
            )
        )
        .scalars()
        .all()
        if lines
        else []
    )
    allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] = {}
    for allocation in allocations:
        allocations_by_line.setdefault(allocation.bill_line_id, []).append(allocation)
    return _serialize_bill(bill, lines, purchase_orders, allocations_by_line)


@router.get("/api/logistics-batches/{bill_id}")
async def get_logistics_batch(bill_id: int, db: AsyncSession = Depends(get_async_db)):
    return await get_logistics_bill(bill_id=bill_id, db=db)


@router.put("/api/logistics-bills/{bill_id}/purchase-orders")
async def replace_logistics_bill_purchase_orders(
    bill_id: int,
    body: LogisticsBillPurchaseOrdersReplaceRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        rows = await service.replace_bill_purchase_orders(bill, body.po_ids)
        await _write_product_center_audit(
            db,
            _user,
            action_type="replace_purchase_orders",
            resource_type="logistics_bill",
            resource_id=str(bill_id),
            changes={"purchase_order_ids": body.po_ids},
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [{"id": row.id, "bill_id": row.bill_id, "po_id": row.po_id} for row in rows]


@router.put("/api/logistics-batches/{bill_id}/purchase-orders")
async def replace_logistics_batch_purchase_orders(
    bill_id: int,
    body: LogisticsBillPurchaseOrdersReplaceRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    return await replace_logistics_bill_purchase_orders(
        bill_id=bill_id, body=body, db=db, _user=_user
    )


@router.patch("/api/logistics-bills/{bill_id}")
async def update_logistics_bill(
    bill_id: int,
    body: LogisticsBillUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if bill.status != "draft":
        raise HTTPException(
            status_code=409, detail="only draft logistics bills can be edited"
        )
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(bill, key, value)
    await _write_product_center_audit(
        db,
        _user,
        action_type="update",
        resource_type="logistics_bill",
        resource_id=str(bill_id),
        changes=values,
    )
    await db.commit()
    return _serialize_bill(bill)


@router.patch("/api/logistics-batches/{bill_id}")
async def update_logistics_batch(
    bill_id: int,
    body: LogisticsBillUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    return await update_logistics_bill(bill_id=bill_id, body=body, db=db, _user=_user)


@router.put("/api/logistics-bills/{bill_id}/lines")
async def replace_logistics_bill_lines(
    bill_id: int,
    body: LogisticsBillLinesReplaceRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        lines = await service.replace_bill_lines(
            bill, [line.model_dump(exclude_unset=True) for line in body.lines]
        )
        await _write_product_center_audit(
            db,
            _user,
            action_type="replace_lines",
            resource_type="logistics_bill",
            resource_id=str(bill_id),
            changes={
                "line_count": len(lines),
                "line_ids": [line.line_id for line in lines],
            },
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    allocations = (
        (
            await db.execute(
                select(LogisticsBillLineAllocation).where(
                    LogisticsBillLineAllocation.bill_line_id.in_(
                        [line.line_id for line in lines]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    allocations_by_line: dict[int, list[LogisticsBillLineAllocation]] = {}
    for allocation in allocations:
        allocations_by_line.setdefault(allocation.bill_line_id, []).append(allocation)
    return _serialize_bill(bill, lines, allocations_by_line=allocations_by_line)


@router.put("/api/logistics-batches/{bill_id}/lines")
async def replace_logistics_batch_lines(
    bill_id: int,
    body: LogisticsBillLinesReplaceRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    return await replace_logistics_bill_lines(
        bill_id=bill_id, body=body, db=db, _user=_user
    )


@router.post("/api/logistics-bills/{bill_id}/confirm")
async def confirm_logistics_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_editor),
):
    service = ProductFinanceService(db)
    try:
        bill = await service.confirm_bill(
            bill=await service.get_bill_or_raise(bill_id),
            user_id=getattr(current_user, "user_id", None),
        )
        await FeishuProjectionService(db).enqueue_full_refresh(
            "logistics_bill_confirmed"
        )
        line_rows = (
            (
                await db.execute(
                    select(LogisticsBillLine).where(
                        LogisticsBillLine.bill_id == bill_id
                    )
                )
            )
            .scalars()
            .all()
        )
        platform_sku_ids = {
            line.sku_id for line in line_rows if line.sku_id is not None
        }
        allocation_rows = (
            (
                await db.execute(
                    select(LogisticsBillLineAllocation).where(
                        LogisticsBillLineAllocation.bill_line_id.in_(
                            [line.line_id for line in line_rows]
                        )
                    )
                )
            )
            .scalars()
            .all()
            if line_rows
            else []
        )
        platform_sku_ids.update(row.sku_id for row in allocation_rows)
        if platform_sku_ids:
            site_profiles = (
                (
                    await db.execute(
                        select(SkuOperatingProfile).where(
                            SkuOperatingProfile.sku_id.in_(platform_sku_ids),
                            SkuOperatingProfile.status == "active",
                            SkuOperatingProfile.effective_to.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for profile in site_profiles:
                await _enqueue_platform_sku_profit_projection(db, profile)
        await _write_product_center_audit(
            db,
            current_user,
            action_type="confirm",
            resource_type="logistics_bill",
            resource_id=str(bill_id),
            changes={"bill_no": bill.bill_no, "status": bill.status},
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
async def confirm_logistics_batch(
    bill_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_editor),
):
    return await confirm_logistics_bill(
        bill_id=bill_id, db=db, current_user=current_user
    )


@router.post("/api/logistics-bills/{bill_id}/void")
async def void_logistics_bill(
    bill_id: int,
    body: LogisticsBillVoidRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_editor),
):
    service = ProductFinanceService(db)
    try:
        bill = await service.get_bill_or_raise(bill_id)
        sku_ids = [
            sku_id
            for sku_id, in (
                await db.execute(
                    select(LogisticsBillLine.sku_id).where(
                        LogisticsBillLine.bill_id == bill_id,
                        LogisticsBillLine.sku_id.is_not(None),
                    )
                )
            ).all()
        ]
        sku_ids.extend(
            sku_id
            for sku_id, in (
                await db.execute(
                    select(LogisticsBillLineAllocation.sku_id)
                    .join(
                        LogisticsBillLine,
                        LogisticsBillLine.line_id
                        == LogisticsBillLineAllocation.bill_line_id,
                    )
                    .where(LogisticsBillLine.bill_id == bill_id)
                )
            ).all()
        )
        bill = await service.void_bill(
            bill, getattr(current_user, "user_id", None), body.reason
        )
        for sku_id in sku_ids:
            sku = await db.get(DimErpSku, sku_id)
            if sku is not None:
                await _enqueue_sku_projection(db, sku)
        await _write_product_center_audit(
            db,
            current_user,
            action_type="void",
            resource_type="logistics_bill",
            resource_id=str(bill_id),
            changes={"bill_no": bill.bill_no, "status": bill.status},
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_bill(bill)


@router.post("/api/logistics-batches/{bill_id}/void")
async def void_logistics_batch(
    bill_id: int,
    body: LogisticsBillVoidRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(_require_editor),
):
    return await void_logistics_bill(
        bill_id=bill_id, body=body, db=db, current_user=current_user
    )


def _serialize_operating_profile(
    row: SkuOperatingProfile, *, sku=None, spu=None, estimate=None
) -> dict:
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
        "estimated_contribution_profit": (
            estimate.estimated_contribution_profit if estimate else None
        ),
        "estimated_margin_rate": estimate.estimated_margin_rate if estimate else None,
        "purchase_cost": estimate.purchase_cost if estimate else None,
        "actual_logistics_cost": (
            estimate.logistics_cost
            if estimate and estimate.logistics_cost_source == "confirmed_logistics_bill"
            else None
        ),
        "actual_storage_cost": None,
        "cost_completeness": estimate.cost_completeness if estimate else None,
        "confidence_level": estimate.confidence_level if estimate else None,
        "latest_estimate_as_of": estimate.estimate_as_of if estimate else None,
        "latest_estimate_id": estimate.estimate_id if estimate else None,
    }
    return {
        key: (float(value) if hasattr(value, "as_tuple") else value)
        for key, value in payload.items()
    }


@router.get(
    "/api/sku-operating-dimensions", response_model=SkuOperatingDimensionsResponse
)
async def list_sku_operating_dimensions(db: AsyncSession = Depends(get_async_db)):
    platforms = (
        (
            await db.execute(
                select(DimPlatform)
                .where(
                    DimPlatform.is_active.is_(True),
                    DimPlatform.platform_role == "sales",
                )
                .order_by(DimPlatform.platform_code)
            )
        )
        .scalars()
        .all()
    )
    warehouses = (
        (
            await db.execute(
                select(DimWarehouse)
                .where(DimWarehouse.status == "active")
                .order_by(DimWarehouse.country_code, DimWarehouse.warehouse_code)
            )
        )
        .scalars()
        .all()
    )
    spus = (
        (
            await db.execute(
                select(DimSpu.spu).where(DimSpu.active.is_(True)).order_by(DimSpu.spu)
            )
        )
        .scalars()
        .all()
    )
    skus = (
        await db.execute(
            select(DimErpSku.sku_id, DimErpSku.sku_key, DimErpSku.sku_name)
            .where(DimErpSku.status == "active")
            .order_by(DimErpSku.sku_key)
        )
    ).all()
    sku_ids = [row.sku_id for row in skus]
    bindings = (
        (
            await db.execute(
                select(BridgeSpuSku.sku_id, BridgeSpuSku.spu).where(
                    BridgeSpuSku.sku_id.in_(sku_ids),
                    *current_binding_condition(),
                )
            )
        ).all()
        if sku_ids
        else []
    )
    spu_by_sku = {row.sku_id: row.spu for row in bindings}
    return {
        "platforms": [
            {
                "platform_code": row.platform_code,
                "name": row.name,
                "default_fee_rate": row.default_fee_rate,
                "fee_rate_effective_from": row.fee_rate_effective_from,
                "fee_rate_source": row.fee_rate_source,
                "fee_rate_version": row.fee_rate_version,
                # 定价抽屉的「成本率合计 / 底线基数」要用的两个成本率
                "default_creator_commission_rate": row.default_creator_commission_rate,
                "other_cost_rate": row.other_cost_rate,
            }
            for row in platforms
        ],
        "spus": list(spus),
        "skus": [
            {
                "sku_id": row.sku_id,
                "sku_key": row.sku_key,
                "sku_name": row.sku_name,
                "spu": spu_by_sku.get(row.sku_id),
            }
            for row in skus
        ],
        "warehouses": [
            {
                "warehouse_code": row.warehouse_code,
                "warehouse_name": row.warehouse_name,
                "country_code": row.country_code,
                "country_name": row.country_name,
            }
            for row in warehouses
        ],
    }


@router.get(
    "/api/platform-sku-profit/candidates",
    response_model=PlatformSkuProfitCandidatePageResponse,
)
async def list_platform_sku_profit_candidates(
    platform_code: str = Query(..., min_length=1),
    warehouse_code: str = Query(..., min_length=1),
    transport_type: str = Query(..., pattern=r"^(sea|air|rail)$"),
    spu: str | None = Query(None),
    sku_id: int | None = Query(None, gt=0),
    keyword: str | None = Query(None),
    only_in_stock: bool = Query(
        True,
        description="只看当前仓有可用库存的 SKU（默认打开）",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    platform = await db.get(DimPlatform, platform_code)
    warehouse = await db.get(DimWarehouse, warehouse_code)
    if platform is None or not platform.is_active or platform.platform_role != "sales":
        raise HTTPException(
            status_code=422, detail="sales platform not found or inactive"
        )
    if warehouse is None or warehouse.status != "active":
        raise HTTPException(status_code=422, detail="warehouse not found or inactive")
    filters = [DimErpSku.status == "active"]
    if sku_id is not None:
        filters.append(DimErpSku.sku_id == sku_id)
    if keyword:
        token = f"%{keyword}%"
        filters.append(
            (DimErpSku.sku_key.ilike(token)) | (DimErpSku.sku_name.ilike(token))
        )
    if spu:
        filters.append(
            DimErpSku.sku_id.in_(
                select(BridgeSpuSku.sku_id).where(
                    BridgeSpuSku.spu == spu,
                    *current_binding_condition(),
                )
            )
        )
    # ⚠️ **库存筛选必须在分页之前做**（阶段 7）：
    #    「仅有库存」是**后端**筛选 —— 前端筛只会筛当前这一页，
    #    总数对不上、翻页还会漏行。所以顺序是：
    #    候选全集（只取 id + sku_key，两列很窄）→ 按当前仓库存过滤与排序 → 再分页。
    candidate_rows = (
        await db.execute(select(DimErpSku.sku_id, DimErpSku.sku_key).where(*filters))
    ).all()
    candidate_ids = [row.sku_id for row in candidate_rows]
    sku_key_by_id = {row.sku_id: (row.sku_key or "") for row in candidate_rows}
    # 当前仓的库存数量 —— **含零库存行**（零 = 已清仓，是事实）。
    # ⚠️ 这条口径与库龄**分家**：只出数量，不参与档位与底线计算。
    stock_snapshot = await load_warehouse_stock_snapshot(
        db, candidate_ids, warehouse_code
    )
    state_available = bool(stock_snapshot.get("available"))
    stock_by_sku = stock_snapshot.get("by_sku") or {}
    if only_in_stock and not state_available:
        # 状态层不可用 ⇒ 库存筛选没法生效。此时**不筛**（而不是把整张表筛空）：
        # 整表空掉会被运营读成"这个仓没货"，比不筛更坏。
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "only_in_stock filter skipped: inventory state unavailable"
        )
        only_in_stock = False

    # 有货优先 + （默认）只看有库存的 —— 纯函数，顺序规则见 select_sku_ids_by_stock
    ordered_ids = select_sku_ids_by_stock(
        candidate_ids, sku_key_by_id, stock_by_sku, only_in_stock
    )
    total = len(ordered_ids)
    page_ids = ordered_ids[(page - 1) * page_size : (page - 1) * page_size + page_size]
    sku_rows = []
    if page_ids:
        fetched_rows = (
            (await db.execute(select(DimErpSku).where(DimErpSku.sku_id.in_(page_ids))))
            .scalars()
            .all()
        )
        row_by_id = {row.sku_id: row for row in fetched_rows}
        sku_rows = [row_by_id[sku_id] for sku_id in page_ids if sku_id in row_by_id]
    ids = [row.sku_id for row in sku_rows]
    bindings = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id.in_(ids),
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .all()
        if ids
        else []
    )
    binding_by_sku = {row.sku_id: row.spu for row in bindings}
    spus = (
        (
            await db.execute(
                select(DimSpu).where(DimSpu.spu.in_(set(binding_by_sku.values())))
            )
        )
        .scalars()
        .all()
        if binding_by_sku
        else []
    )
    spu_by_code = {row.spu: row for row in spus}
    profiles = (
        (
            await db.execute(
                select(SkuOperatingProfile).where(
                    SkuOperatingProfile.sku_id.in_(ids),
                    SkuOperatingProfile.platform_code == platform_code,
                    SkuOperatingProfile.warehouse_code == warehouse_code,
                    SkuOperatingProfile.status == "active",
                    SkuOperatingProfile.effective_to.is_(None),
                )
            )
        )
        .scalars()
        .all()
        if ids
        else []
    )
    profile_by_sku = {row.sku_id: row for row in profiles}
    finance = ProductFinanceService(db)
    cost_inputs_by_sku = await finance.prefetch_platform_sku_profit_inputs(
        sku_rows, warehouse_code, transport_type
    )
    # 定价底线：一次取齐，循环内只做纯计算（候选一次最多 100 行，不要逐行 await）
    # ⚠️ 平台费率按**本次所选平台**取 —— 底线是「SKU × 平台」的量，
    #    拿 TikTok 的费率算 Shopee 的底线会偏低三到七成。
    # ⚠️ 库龄按**本次所选仓**取（阶段 6）—— 底线是「SKU × 平台 × 当前仓」的量：
    #    马来仓滞销 120 天，不该把新加坡仓的底线也压到滞销档。
    #    不传仓的老调用方仍走「各仓取最长」，行为与改造前逐字一致。
    pricing_context = await _pricing_context(
        db, [row.sku_id for row in sku_rows], [platform_code], warehouse_code
    )
    items = []
    for row in sku_rows:
        profile = profile_by_sku.get(row.sku_id)
        assigned_spu = binding_by_sku.get(row.sku_id)
        assigned = spu_by_code.get(assigned_spu) if assigned_spu else None
        cost_inputs = cost_inputs_by_sku[row.sku_id]
        purchase_cost = (
            cost_inputs["purchase_cost"]
            if cost_inputs["purchase_cost"] is not None
            else row.default_purchase_cost
        )
        reference_logistics = cost_inputs["reference_logistics_cost"]
        reference_storage = cost_inputs["reference_storage_cost"]
        reference_label_fee = cost_inputs.get("reference_label_fee")
        actual_logistics = cost_inputs["actual_logistics_cost"]
        expected_selling_price = (
            profile.expected_selling_price if profile else row.reference_selling_price
        )
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
            elif (
                cost_inputs["reference_logistics_rule"].billing_basis == "weight"
                and row.weight_kg is None
            ):
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
            expected_label_fee=reference_label_fee,
            actual_logistics_cost=actual_logistics,
            actual_storage_cost=None,
            platform_fee_rate=platform.default_fee_rate,
            expected_ad_rate=expected_ad_rate,
            # 目标 ROI（阶段 3）：广告费用的主输入口径。
            # 候选列表直接用经营档案里存的那一个（运营的当前意图）。
            target_roi=profile.target_roi if profile else None,
            return_rate=assigned.return_loss_rate if assigned else None,
            damage_rate=assigned.logistics_damage_rate if assigned else None,
            # 达人佣金：SKU 自己设的值优先，否则用所选平台的默认兜底
            creator_commission_rate=(
                row.creator_commission_rate
                if row.creator_commission_rate is not None
                else platform.default_creator_commission_rate
            ),
            # 平台级 ROI 配置（阶段 1）：安全边际 + 平台可填上限
            roi_safety_margin=platform.roi_safety_margin,
            target_roi_ceiling=platform.target_roi_ceiling,
        )
        items.append(
            {
                "sku_id": row.sku_id,
                "sku_key": row.sku_key,
                "sku_name": row.sku_name,
                "specification": row.specification,
                "spu": assigned_spu,
                "reference_selling_price": row.reference_selling_price,
                "purchase_cost": purchase_cost,
                "platform_code": platform_code,
                "warehouse_code": warehouse_code,
                "transport_type": transport_type,
                "expected_selling_price": expected_selling_price,
                # 测算售价来源（阶段 1）：优先用经营档案里记下来的来源
                # （user_input / sku_reference），老档案没记过就退化成 'profile'
                "expected_selling_price_source": (
                    (
                        profile.expected_selling_price_source or "profile"
                        if profile is not None
                        and profile.expected_selling_price is not None
                        else None
                    )
                    or (
                        "sku_reference"
                        if row.reference_selling_price is not None
                        else None
                    )
                ),
                "competitor_price": profile.competitor_price if profile else None,
                "seller_coupon_amount": seller_coupon_amount,
                "expected_ad_rate": expected_ad_rate,
                # 目标 ROI（阶段 2.2）：运营的**当前意图**，存在经营档案里 ⇒ 列表要回带，
                # 前端才能把上一轮填的值预填进输入框（与测算售价/广告费率同一套预填口径）。
                # ⚠️ 平台报告 ROI（actual_roi）**故意不预填**：它是"某一次投放"的历史事实，
                #    预填了再存进新一版利润版本，就会把上一轮的事实悄悄带过去 ——
                #    事后没人说得清这一版的 ROI 是哪一轮的。留空，由运营每次照平台后台重新填。
                "target_roi": profile.target_roi if profile else None,
                "target_roi_source": profile.target_roi_source if profile else None,
                "expected_logistics_cost": reference_logistics,
                "expected_storage_cost": reference_storage,
                "actual_logistics_cost": actual_logistics,
                "actual_storage_cost": None,
                "platform_fee_rate": platform.default_fee_rate,
                # ROI 配置（阶段 1）：前端要显示「建议 ROI 封顶值」并提示广告空间不足
                "roi_safety_margin": platform.roi_safety_margin,
                "target_roi_ceiling": platform.target_roi_ceiling,
                "logistics_damage_rate": (
                    assigned.logistics_damage_rate if assigned else None
                ),
                "return_loss_rate": assigned.return_loss_rate if assigned else None,
                "configuration_status": "configured" if profile else "unconfigured",
                "turnover_class": row.turnover_class,
                "reference_storage_days": reference_storage_days(row.turnover_class),
                "reference_logistics_cost": reference_logistics,
                "reference_storage_cost": reference_storage,
                "reference_label_fee": reference_label_fee,
                "reference_cost_status": (
                    "ready" if not missing_reasons else "incomplete"
                ),
                "reference_cost_missing_reasons": list(dict.fromkeys(missing_reasons)),
                "reference_logistics_missing_reasons": [
                    reason
                    for reason in missing_reasons
                    if reason
                    in {
                        "missing_logistics_rule",
                        "missing_sku_weight",
                        "ambiguous_logistics_rule",
                    }
                    or (reason == "missing_sku_volume" and reference_logistics is None)
                ],
                "reference_storage_missing_reasons": [
                    reason
                    for reason in missing_reasons
                    if reason in {"missing_storage_rule", "missing_turnover_class"}
                    or (reason == "missing_sku_volume" and reference_storage is None)
                ],
                "preview": _decimal_payload(preview),
            }
        )
        # 定价底线字段并进这一行（其余键保持原样）
        pricing_payload = _compute_pricing_for_sku(
            context=pricing_context,
            sku_row=row,
            linked_spu=assigned,
            platform_code=platform_code,
        )
        pricing_payload["min_selling_price_platform"] = platform_code
        floor = pricing_payload["min_selling_price"]
        pricing_payload["min_selling_price_below"] = bool(
            floor is not None
            and expected_selling_price is not None
            and Decimal(str(expected_selling_price)) < Decimal(str(floor))
        )
        # 跨仓差异（阶段 6）：同一 SKU 在别的仓滞销、这个仓不滞销 ⇒
        # 提示「优先调拨而非降价」。**只提示，不改价** ——
        # 调拨是运营决策，系统不越权。
        divergence = detect_warehouse_divergence(
            (pricing_context.get("warehouse_restocks") or {}).get(row.sku_id) or {},
            pricing_context.get("policies") or [],
        )
        pricing_payload["warehouse_divergence"] = divergence
        # 各仓自己的库龄：让运营能直接看到「这个 SKU 在哪几个仓、各自多老」
        pricing_payload["warehouse_restocks"] = [
            {
                "warehouse_code": entry.get("warehouse_code"),
                "warehouse_name": entry.get("warehouse_name") or "",
                "days_since_restock": entry.get("days_since_restock"),
                "current_qty": entry.get("current_qty"),
                "inventory_value": entry.get("inventory_value"),
            }
            for entry in (
                (pricing_context.get("warehouse_restocks") or {}).get(row.sku_id) or {}
            ).values()
        ]
        # 当前仓库存（阶段 7）：**含零库存行** ——
        # 「已清仓」是一条事实（这个仓清过这货），不是缺数据；
        # 与库龄分家，只出数量，不参与档位与底线。
        stock_entry = stock_by_sku.get(row.sku_id) or None
        pricing_payload["current_warehouse_available_stock"] = (
            int(stock_entry.get("available_stock") or 0) if stock_entry else None
        )
        pricing_payload["current_warehouse_stock_status"] = resolve_stock_status(
            stock_entry, state_available
        )
        items[-1] = {**items[-1], **pricing_payload}
    return {
        "data": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/api/platform-sku-profit/preview")
async def preview_platform_sku_profit(
    body: PlatformSkuProfitPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    try:
        result = await ProductFinanceService(db).preview_platform_sku_profit(
            body.model_dump()
        )
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
    if (
        values.get("expected_selling_price") is None
        and sku.reference_selling_price is None
    ):
        missing.append("预计售价")
    purchase_cost = await finance.find_latest_purchase_cost(sku)
    if purchase_cost is None and sku.default_purchase_cost is None:
        missing.append("采购成本")
    reference_logistics, logistics_rule = await finance.find_reference_logistics_cost(
        sku, values["warehouse_code"], values["transport_type"]
    )
    if reference_logistics is None:
        if (
            logistics_rule is not None
            and logistics_rule.billing_basis == "weight"
            and sku.weight_kg is None
        ):
            missing.append("重量 kg")
        elif (
            logistics_rule is not None
            and logistics_rule.billing_basis == "volume"
            and logistics_rule.freight_unit_rate is not None
        ):
            missing.append("单件体积 m³")
        else:
            missing.append(f"{values['transport_type']}参考物流规则")
    reference_storage, storage_rule = await finance.find_reference_storage_cost(
        sku, values["warehouse_code"]
    )
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
    binding = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku.sku_id,
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .first()
    )
    spu = await db.get(DimSpu, binding.spu) if binding else None
    if spu is None or spu.logistics_damage_rate is None or spu.return_loss_rate is None:
        missing.append("SPU货损率和退货损失率")
    if (
        preview is not None
        and preview.get("expected", {}).get("profit") is None
        and not missing
    ):
        missing.append("完整预计利润口径")
    return list(dict.fromkeys(missing))


def _evaluate_roi_guard(values: dict, preview: dict, missing_fields: list[str]) -> dict:
    """ROI 投放护栏判定（阶段 2.2）。

    返回 ``{"error": dict | None, "warnings": list}``：
    - ``error`` 非 None ⇒ 调用方要抛 ``BusinessValidationError``（护栏拦住）
    - ``warnings`` 是**不拦**的提示（例如广告空间不足）

    判定顺序（**不能改**）
    --------------------
    1. **目标 ROI 没填 ⇒ 不参与护栏**。
       平台报告 ROI（``actual_roi``）是**事实记录**，永远不拦 ——
       拦了就等于不许记录亏损投放（真实亏过的投放恰恰要留痕）。
    2. **成本齐全** ⇒ 保本 ROI 可算：
       - ``target_roi < break_even_roi`` ⇒ ``below_break_even_roi``（拦）
       - 建议 ROI 超过平台可填上限 ⇒ ``roi_out_of_platform_range``
         （**提示，不拦** —— 广告空间不足是客观限制，不是操作错误）
    3. **成本不全** ⇒ 保本 ROI 算不出来：
       - 用保本 ROI 的**下界**（未知成本一律当 0）去**证明**：
         ``target_roi < 下界`` ⇒ ``below_break_even_roi``（拦 —— 已经能确定必亏）
       - 证不出来 ⇒ ``roi_cost_incomplete``（拦 —— 成本不全 ⇒ 保本 ROI 不可信，
         不可乐观地放行）

    ⚠️ **护栏必须排在「资料完整性」校验之前**（沿用 ``below_min_selling_price``
    的顺序逻辑）。缺物流规则时，运营更需要先知道"你填的目标 ROI 连最乐观的
    保本线都够不着"——补完物流规则他可能**还是**亏；反过来先报"去补物流规则"
    会让人以为补完就没事了。

    ⚠️ 下界的性质：它**只可能偏松**（把未知成本当 0），所以只能用来"证死"
    （连它都够不着 ⇒ 一定亏），不能用来"证活"。证不出来就不拦。
    """
    warnings: list[dict] = []
    target_roi = values.get("target_roi")
    if target_roi is None:
        return {"error": None, "warnings": warnings}

    target = Decimal(str(target_roi))
    expected = preview.get("expected") or {}
    break_even_roi = expected.get("break_even_roi")
    lower_bound = expected.get("break_even_roi_lower_bound")

    def _detail(code: str, basis: str, threshold) -> dict:
        if basis == "exact":
            message = f"目标 ROI {target} 低于保本线 {threshold}，这单投了就是亏"
        else:
            # basis = 'lower_bound'：成本不全 ⇒ 只能给出保本线的**下界**，
            # 但下界只可能偏松 ⇒ target_roi 低于它就**一定**亏。
            message = (
                f"目标 ROI {target} 低于保本线（至少 {threshold}），" "这单投了就是亏"
            )
        return {
            "code": code,
            "message": message,
            "basis": basis,
            "target_roi": float(target),
            "break_even_roi": float(threshold),
            "sku_id": values.get("sku_id"),
            "platform_code": values.get("platform_code"),
        }

    if break_even_roi is not None:
        threshold = Decimal(str(break_even_roi))
        if target < threshold:
            return {
                "error": _detail("below_break_even_roi", "exact", threshold),
                "warnings": warnings,
            }
        # 广告空间不足：建议 ROI 超过平台可填上限 ⇒ 提示，不拦。
        # ⚠️ 用 ROI 服务算好的 ``suggestion_note``，因为它用的是**生效**上限
        #    （平台没配上限时用模块默认值 50），不要在这里自己比一个可能为 None 的上限。
        if expected.get("suggestion_note") == "above_platform_ceiling":
            # ⚠️ 先取出来再判空 —— ``preview.get(...)`` 调两次时 mypy 无法缩窄类型。
            target_roi_ceiling = preview.get("target_roi_ceiling")
            warnings.append(
                {
                    "code": "roi_out_of_platform_range",
                    "message": "建议 ROI 超过平台可填上限，广告空间不足",
                    "suggested_roi": float(expected.get("suggested_roi") or 0),
                    "target_roi_ceiling": (
                        float(target_roi_ceiling)
                        if target_roi_ceiling is not None
                        else None
                    ),
                }
            )
        return {"error": None, "warnings": warnings}

    # 成本不全 ⇒ 保本 ROI 不可信。用**下界**去证明"必亏"。
    if lower_bound is not None:
        threshold = Decimal(str(lower_bound))
        if target < threshold:
            return {
                "error": _detail("below_break_even_roi", "lower_bound", threshold),
                "warnings": warnings,
            }
    return {
        "error": {
            "code": "roi_cost_incomplete",
            "message": "成本资料未完整，保本 ROI 不可信，不能据此设定目标 ROI",
            "target_roi": float(target),
            "sku_id": values.get("sku_id"),
            "platform_code": values.get("platform_code"),
            "missing_fields": list(missing_fields or []),
        },
        "warnings": warnings,
    }


@router.post("/api/platform-sku-profit/drafts", status_code=201)
async def save_platform_sku_profit_draft(
    body: PlatformSkuProfitDraftRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    values = body.model_dump()
    await _validate_operating_dimensions(db, values)
    profile = (
        (
            await db.execute(
                select(SkuOperatingProfile).where(
                    SkuOperatingProfile.sku_id == values["sku_id"],
                    SkuOperatingProfile.platform_code == values["platform_code"],
                    SkuOperatingProfile.warehouse_code == values["warehouse_code"],
                    SkuOperatingProfile.status == "active",
                    SkuOperatingProfile.effective_to.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if profile is None:
        profile = SkuOperatingProfile(
            sku_id=values["sku_id"],
            platform_code=values["platform_code"],
            warehouse_code=values["warehouse_code"],
            status="active",
            created_by=getattr(_user, "user_id", None),
        )
        db.add(profile)
    for key in (
        "transport_type",
        "competitor_price",
        "expected_selling_price",
        "seller_coupon_amount",
        "expected_ad_rate",
        "target_roi",
    ):
        setattr(profile, key, values.get(key))
    sku = await db.get(DimErpSku, values["sku_id"])
    platform = await db.get(DimPlatform, values["platform_code"])
    profile.reference_selling_price = sku.reference_selling_price if sku else None
    profile.platform_fee_rate = platform.default_fee_rate if platform else None
    # 测算售价来源：运营自己填的 / SKU 参考售价兜底的 —— 两者在利润表里长得一样，
    # 但在 ROI 判定里可信度不同，必须留痕。
    profile.expected_selling_price_source = (
        "user_input"
        if values.get("expected_selling_price") is not None
        else (
            "sku_reference"
            if sku is not None and sku.reference_selling_price is not None
            else None
        )
    )
    # 目标 ROI 来源（阶段 2.2）：目前只有人工填写这一条来源。
    # 阶段 3 会把存量 SKU 的老口径「广告分成率」反解成 target_roi，来源标记
    # 会变成 'migrated_from_legacy_rate' —— 两者在利润表里长得一样但可信度不同，
    # 所以必须留痕，不能事后靠猜。
    profile.target_roi_source = (
        "user_input" if values.get("target_roi") is not None else None
    )
    finance = ProductFinanceService(db)
    profile.expected_label_fee = await finance.find_reference_label_fee(
        values["warehouse_code"]
    )
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="save_draft",
            resource_type="platform_sku_profit_draft",
            resource_id=f"{values['platform_code']}:{values['warehouse_code']}:{values['sku_id']}",
            changes=values,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="platform SKU profit draft conflicts with existing configuration",
        ) from exc
    return {"profile_id": profile.profile_id, "status": "draft_saved"}


@router.post("/api/platform-sku-profit/estimates", status_code=201)
async def save_platform_sku_profit_estimates(
    body: PlatformSkuProfitEstimateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    values = body.model_dump()
    await _validate_operating_dimensions(db, values)
    # 护栏：**排在「资料完整性」校验之前**。
    # 若排在后面，缺物流/仓储规则时会先撞 cannot_save_profit_version（缺资料），
    # 用户永远看不到「低于最低售价」这个更可执行的原因。
    # 护栏的输入（采购成本 + **该平台**的成本率 + 参考售价 + 规则表）不依赖物流/仓储规则，
    # 底线算不出来时 floor 为 None，护栏自动跳过，交给后面的缺资料校验。
    # ⚠️ 底线是「SKU × 平台」的量 ⇒ 必须按**请求里的平台**算，不能用 SKU 级底线。
    floor = await _compute_sku_min_selling_price(
        db, values["sku_id"], values["platform_code"]
    )
    if floor is not None and values.get("expected_selling_price") is not None:
        if Decimal(str(values["expected_selling_price"])) < floor:
            raise BusinessValidationError(
                message=f"预计售价 {values['expected_selling_price']} 低于最低售价 {floor}",
                detail={
                    "code": "below_min_selling_price",
                    "min_selling_price": float(floor),
                    "expected_selling_price": values["expected_selling_price"],
                    "sku_id": values["sku_id"],
                },
            )
    try:
        preview = await ProductFinanceService(db).preview_platform_sku_profit(values)
    except ValueError as exc:
        missing_fields = await _platform_profit_missing_fields(db, values)
        raise BusinessValidationError(
            message="资料未完整，不能保存利润版本",
            detail={
                "code": "cannot_save_profit_version",
                "missing_fields": missing_fields or [str(exc)],
            },
        ) from exc
    missing_fields = await _platform_profit_missing_fields(db, values, preview)
    # ROI 护栏（阶段 2.2）：**必须排在「资料完整性」校验之前**。
    # 缺成本时也要能判"目标 ROI 连最乐观的保本线都够不着" ——
    # 补完物流规则他可能**还是**亏，先报"去补物流规则"会让人以为补完就没事了。
    # 详见 `_evaluate_roi_guard` 的口径说明。
    roi_guard = _evaluate_roi_guard(values, preview, missing_fields)
    if roi_guard["error"] is not None:
        raise BusinessValidationError(
            message=roi_guard["error"].get("message") or "ROI 投放护栏未通过",
            detail=roi_guard["error"],
        )
    if missing_fields:
        raise BusinessValidationError(
            message="资料未完整，不能保存利润版本",
            detail={
                "code": "cannot_save_profit_version",
                "missing_fields": missing_fields,
            },
        )
    profile = (
        (
            await db.execute(
                select(SkuOperatingProfile).where(
                    SkuOperatingProfile.sku_id == values["sku_id"],
                    SkuOperatingProfile.platform_code == values["platform_code"],
                    SkuOperatingProfile.warehouse_code == values["warehouse_code"],
                    SkuOperatingProfile.status == "active",
                    SkuOperatingProfile.effective_to.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if profile is None:
        profile = SkuOperatingProfile(
            sku_id=values["sku_id"],
            platform_code=values["platform_code"],
            warehouse_code=values["warehouse_code"],
            status="active",
            created_by=getattr(_user, "user_id", None),
        )
        db.add(profile)
    for key in (
        "transport_type",
        "competitor_price",
        "expected_selling_price",
        "seller_coupon_amount",
        "expected_ad_rate",
        "target_roi",
    ):
        setattr(profile, key, values.get(key))
    sku = await db.get(DimErpSku, values["sku_id"])
    profile.reference_selling_price = sku.reference_selling_price if sku else None
    platform = await db.get(DimPlatform, values["platform_code"])
    profile.platform_fee_rate = platform.default_fee_rate if platform else None
    # 测算售价来源：运营自己填的 / SKU 参考售价兜底的 —— 两者在利润表里长得一样，
    # 但在 ROI 判定里可信度不同，必须留痕。
    profile.expected_selling_price_source = (
        "user_input"
        if values.get("expected_selling_price") is not None
        else (
            "sku_reference"
            if sku is not None and sku.reference_selling_price is not None
            else None
        )
    )
    # 目标 ROI 来源（阶段 2.2）：与草稿保存同一套口径。
    profile.target_roi_source = (
        "user_input" if values.get("target_roi") is not None else None
    )
    finance = ProductFinanceService(db)
    profile.expected_label_fee = await finance.find_reference_label_fee(
        values["warehouse_code"]
    )
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
            sku_id=values["sku_id"],
            operating_profile_id=profile.profile_id,
            platform_code=values["platform_code"],
            warehouse_code=values["warehouse_code"],
            assumption_version=values.get("assumption_version")
            or "platform-profit-workbench",
            scenario="base",
            calculation_basis=basis,
            selling_price=(
                values["expected_selling_price"]
                if values.get("expected_selling_price") is not None
                else profile.reference_selling_price
            ),
            coupon_amount=values.get("seller_coupon_amount", 0),
            expected_selling_price=(
                values["expected_selling_price"]
                if values.get("expected_selling_price") is not None
                else profile.reference_selling_price
            ),
            competitor_price=values.get("competitor_price"),
            expected_ad_rate=values.get("expected_ad_rate", 0),
            platform_fee=section.get(
                "platform_fee", preview["expected"].get("platform_fee")
            ),
            creator_commission=section.get(
                "creator_commission", preview["expected"].get("creator_commission")
            ),
            expected_ad_cost=preview["expected"].get("ad_cost"),
            expected_logistics_cost=preview["expected"].get("logistics_cost"),
            actual_logistics_cost=preview.get("actual_logistics_cost"),
            expected_storage_cost=preview["expected"].get("storage_cost"),
            expected_label_fee=preview["expected"].get("label_fee"),
            actual_storage_cost=None,
            expected_profit=preview["expected"].get("profit"),
            expected_margin_rate=preview["expected"].get("margin_rate"),
            actual_recost_profit=preview["actual_recost"].get("profit"),
            actual_recost_margin_rate=preview["actual_recost"].get("margin_rate"),
            actual_recost_completeness=preview["actual_recost"].get("completeness"),
            logistics_cost_variance=preview["variance"].get("logistics"),
            storage_cost_variance=preview["variance"].get("storage"),
            total_cost_variance=preview["variance"].get("total"),
            reference_storage_days=preview.get("reference_storage_days"),
            storage_rule_id=preview.get("reference_storage_rule_id"),
            storage_rule_version=preview.get("reference_storage_rule_version"),
            estimated_contribution_profit=section.get("profit"),
            estimated_margin_rate=section.get("margin_rate"),
            # ROI 投放边界：跟着这一版利润一起存下来，否则运营投的那个 ROI 事后无从解释。
            # 取本 section 自己的值（estimated 段 / actual_recost 段各算各的 —— 两段成本口径不同）。
            break_even_roi=section.get("break_even_roi"),
            suggested_roi=section.get("suggested_roi"),
            suggested_roi_clamped=section.get("suggested_roi_clamped"),
            equivalent_target_roi=section.get("equivalent_target_roi"),
            expected_selling_price_source=preview.get("expected_selling_price_source"),
            # 平台报告 ROI（阶段 2.2）：**事实记录**，不是判定依据。
            # 它记的是"平台后台回传的这次投放实际 ROI" —— 低于保本线也照样存，
            # 因为真实亏过的投放恰恰要留痕（拦了就等于不许记录亏损投放）。
            # ⚠️ 同一版利润会落两行（estimated / actual_recost），两行记的是**同一次投放**，
            #    所以这个值在两行上是一样的 —— 不是复制错误，是同一个事实的两份视角。
            actual_roi=values.get("actual_roi"),
            actual_roi_source=(
                "user_input" if values.get("actual_roi") is not None else None
            ),
            # ⚠️ `cost_completeness` 这一列的语义是「**参考成本**（预估口径）齐不齐」，
            # 取值域 complete/partial/incomplete。必须**固定取 expected 段**，
            # 不能取 `section` —— 因为 section 会随 basis 在 expected / actual_recost 之间变，
            # 而 actual_recost 段的 completeness 是另一套值域（incomplete/estimated/mixed/actual），
            # 写进这一列会违反 schema 的 pattern，也把两种语义混在同一列。
            # actual_recost 段的完整度由 `actual_recost_completeness` 列承载（见上一行）。
            cost_completeness=preview["expected"].get("completeness", "incomplete"),
            confidence_level="medium",
        )
        db.add(row)
        estimates.append(row)
    await db.flush()
    await _enqueue_platform_sku_profit_projection(db, profile)
    await _write_product_center_audit(
        db,
        _user,
        action_type="create",
        resource_type="platform_sku_profit_estimate",
        resource_id=f"{values['platform_code']}:{values['warehouse_code']}:{values['sku_id']}",
        changes={
            "profile_id": profile.profile_id,
            "estimate_count": len(estimates),
            "calculation_bases": [basis for basis, _section in versions],
            # ROI 投放输入（阶段 2.2）：目标 ROI 进档案、平台报告 ROI 进利润版本。
            # 两者来源不同、落点不同，审计里必须能分清。
            "target_roi": values.get("target_roi"),
            "target_roi_source": profile.target_roi_source,
            "actual_roi": values.get("actual_roi"),
            "actual_roi_source": (
                "user_input" if values.get("actual_roi") is not None else None
            ),
        },
    )
    await db.commit()
    return {
        "profile_id": profile.profile_id,
        "estimate_ids": [row.estimate_id for row in estimates],
        # 不拦的提示（例如广告空间不足）。护栏拦住时是异常，不走这里。
        "roi_warnings": roi_guard["warnings"],
    }


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
    filters = [
        SkuProfitEstimate.platform_code == platform_code,
        SkuProfitEstimate.warehouse_code == warehouse_code,
    ]
    if sku_id is not None:
        filters.append(SkuProfitEstimate.sku_id == sku_id)
    if calculation_basis:
        filters.append(SkuProfitEstimate.calculation_basis == calculation_basis)
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(SkuProfitEstimate).where(*filters)
            )
        ).scalar()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(SkuProfitEstimate)
                .where(*filters)
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": [
            _decimal_payload(
                {
                    "estimate_id": row.estimate_id,
                    "sku_id": row.sku_id,
                    "calculation_basis": row.calculation_basis,
                    "expected_profit": row.expected_profit,
                    "expected_margin_rate": row.expected_margin_rate,
                    "actual_recost_profit": row.actual_recost_profit,
                    "actual_recost_margin_rate": row.actual_recost_margin_rate,
                    "actual_recost_completeness": row.actual_recost_completeness,
                    "estimate_as_of": row.estimate_as_of,
                    "break_even_roi": row.break_even_roi,
                    "suggested_roi": row.suggested_roi,
                    "suggested_roi_clamped": row.suggested_roi_clamped,
                    "equivalent_target_roi": row.equivalent_target_roi,
                    "expected_selling_price_source": row.expected_selling_price_source,
                    "actual_roi": row.actual_roi,
                    "actual_roi_source": row.actual_roi_source,
                }
            )
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get(
    "/api/sku-operating-profiles", response_model=list[SkuOperatingProfileResponse]
)
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
    for field, value in (
        (SkuOperatingProfile.sku_id, sku_id),
        (SkuOperatingProfile.platform_code, platform_code),
        (SkuOperatingProfile.warehouse_code, warehouse_code),
        (SkuOperatingProfile.status, status),
    ):
        if value is not None:
            filters.append(field == value)
    rows = (
        (
            await db.execute(
                select(SkuOperatingProfile)
                .where(*filters)
                .order_by(
                    SkuOperatingProfile.platform_code,
                    SkuOperatingProfile.warehouse_code,
                    SkuOperatingProfile.sku_id,
                )
            )
        )
        .scalars()
        .all()
    )
    sku_ids = {row.sku_id for row in rows}
    profile_ids = {row.profile_id for row in rows}
    sku_rows = (
        (await db.execute(select(DimErpSku).where(DimErpSku.sku_id.in_(sku_ids))))
        .scalars()
        .all()
        if sku_ids
        else []
    )
    sku_by_id = {row.sku_id: row for row in sku_rows}
    bindings = (
        (
            await db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id.in_(sku_ids),
                    *current_binding_condition(),
                )
            )
        )
        .scalars()
        .all()
        if sku_ids
        else []
    )
    spu_codes = {row.spu for row in bindings}
    spu_rows = (
        (await db.execute(select(DimSpu).where(DimSpu.spu.in_(spu_codes))))
        .scalars()
        .all()
        if spu_codes
        else []
    )
    spu_by_code = {row.spu: row for row in spu_rows}
    binding_by_sku = {row.sku_id: row for row in bindings}
    estimates = (
        (
            await db.execute(
                select(SkuProfitEstimate)
                .where(SkuProfitEstimate.operating_profile_id.in_(profile_ids))
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
            )
        )
        .scalars()
        .all()
        if profile_ids
        else []
    )
    estimate_by_profile: dict[int, object] = {}
    for estimate in estimates:
        estimate_by_profile.setdefault(estimate.operating_profile_id, estimate)
    payloads = []
    finance_service = ProductFinanceService(db)
    for row in rows:
        payload = _serialize_operating_profile(
            row,
            sku=sku_by_id.get(row.sku_id),
            spu=(
                spu_by_code.get(binding_by_sku[row.sku_id].spu)
                if row.sku_id in binding_by_sku
                else None
            ),
            estimate=estimate_by_profile.get(row.profile_id),
        )
        payload["actual_logistics_cost"] = (
            await finance_service.find_confirmed_logistics_cost(
                row.sku_id, row.warehouse_code, row.transport_type
            )
        )
        payloads.append(payload)
    if spu:
        payloads = [payload for payload in payloads if payload.get("spu") == spu]
    if include_unconfigured and status in (None, "active"):
        active_skus = (
            (await db.execute(select(DimErpSku).where(DimErpSku.status == "active")))
            .scalars()
            .all()
        )
        active_platforms = (
            (
                await db.execute(
                    select(DimPlatform).where(DimPlatform.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        active_warehouses = (
            (
                await db.execute(
                    select(DimWarehouse).where(DimWarehouse.status == "active")
                )
            )
            .scalars()
            .all()
        )
        sku_ids_for_bindings = {sku.sku_id for sku in active_skus}
        binding_rows = (
            (
                await db.execute(
                    select(BridgeSpuSku).where(
                        BridgeSpuSku.sku_id.in_(sku_ids_for_bindings),
                        *current_binding_condition(),
                    )
                )
            )
            .scalars()
            .all()
            if sku_ids_for_bindings
            else []
        )
        binding_by_sku = {row.sku_id: row.spu for row in binding_rows}
        bound_spu_rows = (
            (
                await db.execute(
                    select(DimSpu).where(DimSpu.spu.in_(set(binding_by_sku.values())))
                )
            )
            .scalars()
            .all()
            if binding_by_sku
            else []
        )
        bound_spu_by_code = {row.spu: row for row in bound_spu_rows}
        mapped_platform_rows = (
            (
                await db.execute(
                    select(
                        BridgeErpSkuKey.sku_id, BridgeErpSkuKey.source_platform
                    ).where(
                        BridgeErpSkuKey.sku_id.in_(sku_ids_for_bindings),
                        BridgeErpSkuKey.active.is_(True),
                        BridgeErpSkuKey.effective_to.is_(None),
                        BridgeErpSkuKey.source_platform.is_not(None),
                    )
                )
            ).all()
            if sku_ids_for_bindings
            else []
        )
        mapped_platforms: dict[int, set[str]] = {}
        for mapped_sku_id, mapped_platform in mapped_platform_rows:
            mapped_platforms.setdefault(mapped_sku_id, set()).add(mapped_platform)
        existing_keys = {
            (row.sku_id, row.platform_code, row.warehouse_code) for row in rows
        }
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
                if (
                    mapped_platforms
                    and platform.platform_code
                    not in mapped_platforms.get(sku.sku_id, set())
                ):
                    continue
                for warehouse in active_warehouses:
                    if warehouse_code and warehouse.warehouse_code != warehouse_code:
                        continue
                    key = (sku.sku_id, platform.platform_code, warehouse.warehouse_code)
                    if key in existing_keys:
                        continue
                    payloads.append(
                        {
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
                            "logistics_damage_rate": (
                                bound_spu_row.logistics_damage_rate
                                if bound_spu_row
                                else None
                            ),
                            "return_loss_rate": (
                                bound_spu_row.return_loss_rate
                                if bound_spu_row
                                else None
                            ),
                            "cost_completeness": "incomplete",
                            "unconfigured": True,
                        }
                    )
    return payloads


async def _validate_operating_dimensions(db: AsyncSession, values: dict) -> None:
    sku = await db.get(DimErpSku, values["sku_id"])
    if sku is None or sku.status != "active":
        raise HTTPException(status_code=422, detail="SKU not found or inactive")
    platform = await db.get(DimPlatform, values["platform_code"])
    if platform is None or not platform.is_active or platform.platform_role != "sales":
        raise HTTPException(status_code=422, detail="active sales platform not found")
    warehouse = await db.get(DimWarehouse, values["warehouse_code"])
    if warehouse is None or warehouse.status != "active":
        raise HTTPException(status_code=422, detail="warehouse not found or inactive")
    values["platform_fee_rate"] = platform.default_fee_rate


@router.post(
    "/api/sku-operating-profiles",
    response_model=SkuOperatingProfileResponse,
    status_code=201,
)
async def create_sku_operating_profile(
    body: SkuOperatingProfileCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    values = body.model_dump()
    await _validate_operating_dimensions(db, values)
    row = SkuOperatingProfile(
        **values,
        created_by=getattr(_user, "user_id", None),
        updated_by=getattr(_user, "user_id", None),
    )
    db.add(row)
    try:
        await db.flush()
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="sku_operating_profile",
            resource_id=str(row.profile_id),
            changes=values,
        )
        await _enqueue_platform_sku_profit_projection(db, row)
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="active SKU operating profile already exists"
        ) from exc
    return _serialize_operating_profile(row)


@router.patch(
    "/api/sku-operating-profiles/{profile_id}",
    response_model=SkuOperatingProfileResponse,
)
async def update_sku_operating_profile(
    profile_id: int,
    body: SkuOperatingProfileUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
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
            db,
            _user,
            action_type="update",
            resource_type="sku_operating_profile",
            resource_id=str(row.profile_id),
            changes=values,
        )
        await _enqueue_platform_sku_profit_projection(db, row)
        await db.commit()
        await db.refresh(row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="active SKU operating profile already exists"
        ) from exc
    return _serialize_operating_profile(row)


@router.post("/api/sku-operating-profiles/bulk")
async def bulk_save_sku_operating_profiles(
    body: SkuOperatingProfileBulkRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    created = 0
    updated = 0
    rows = []
    changes_by_row = []
    try:
        for item in body.items:
            values = item.model_dump()
            await _validate_operating_dimensions(db, values)
            filters = [
                SkuOperatingProfile.sku_id == values["sku_id"],
                SkuOperatingProfile.platform_code == values["platform_code"],
                SkuOperatingProfile.warehouse_code == values["warehouse_code"],
                SkuOperatingProfile.status == "active",
                SkuOperatingProfile.effective_to.is_(None),
            ]
            row = (
                (await db.execute(select(SkuOperatingProfile).where(*filters)))
                .scalars()
                .first()
            )
            if row is None:
                row = SkuOperatingProfile(
                    **values,
                    created_by=getattr(_user, "user_id", None),
                    updated_by=getattr(_user, "user_id", None),
                )
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
                db,
                _user,
                action_type=action_type,
                resource_type="sku_operating_profile",
                resource_id=str(row.profile_id),
                changes=values,
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
        raise HTTPException(
            status_code=409,
            detail="bulk operating profile save conflicts with existing data",
        ) from exc
    return {
        "created": created,
        "updated": updated,
        "items": [_serialize_operating_profile(row) for row in rows],
    }


@router.get(
    "/api/sku-operating-profiles/{profile_id}",
    response_model=SkuOperatingProfileResponse,
)
async def get_sku_operating_profile(
    profile_id: int, db: AsyncSession = Depends(get_async_db)
):
    row = await db.get(SkuOperatingProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SKU operating profile not found")
    return _serialize_operating_profile(row)


@router.post(
    "/api/sku-operating-profiles/{profile_id}/profit-preview",
    response_model=SkuOperatingProfitResponse,
)
async def preview_sku_operating_profit(
    profile_id: int,
    body: SkuOperatingProfitRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    try:
        result = await ProductFinanceService(db).preview_operating_profit(
            profile_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        key: float(value) if hasattr(value, "as_tuple") else value
        for key, value in result.items()
    }


@router.post(
    "/api/sku-operating-profiles/{profile_id}/profit-estimates",
    response_model=SkuOperatingProfitSaveResponse,
    status_code=201,
)
async def save_sku_operating_profit(
    profile_id: int,
    body: SkuOperatingProfitRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    try:
        row = await ProductFinanceService(db).save_operating_profit(
            profile_id, body.model_dump(exclude_unset=True)
        )
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="sku_operating_profit_estimate",
            resource_id=str(row.estimate_id),
            changes={"profile_id": profile_id},
        )
        await _enqueue_platform_sku_profit_projection(
            db, await db.get(SkuOperatingProfile, profile_id)
        )
        await db.commit()
        await db.refresh(row)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "estimate_id": row.estimate_id,
        "profile_id": row.operating_profile_id,
        "sku_id": row.sku_id,
        "estimated_contribution_profit": (
            float(row.estimated_contribution_profit)
            if row.estimated_contribution_profit is not None
            else None
        ),
        "estimated_margin_rate": (
            float(row.estimated_margin_rate)
            if row.estimated_margin_rate is not None
            else None
        ),
    }


@router.get(
    "/api/sku-operating-profiles/{profile_id}/profit-estimates",
    response_model=list[SkuOperatingProfitHistoryResponse],
)
async def list_sku_operating_profit_history(
    profile_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
):
    rows = (
        (
            await db.execute(
                select(SkuProfitEstimate)
                .where(SkuProfitEstimate.operating_profile_id == profile_id)
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "estimate_id": row.estimate_id,
            "profile_id": row.operating_profile_id,
            "sku_id": row.sku_id,
            "platform_code": row.platform_code,
            "warehouse_code": row.warehouse_code,
            "estimate_as_of": row.estimate_as_of,
            "estimated_contribution_profit": (
                float(row.estimated_contribution_profit)
                if row.estimated_contribution_profit is not None
                else None
            ),
            "estimated_margin_rate": (
                float(row.estimated_margin_rate)
                if row.estimated_margin_rate is not None
                else None
            ),
            "cost_completeness": row.cost_completeness,
            "confidence_level": row.confidence_level,
        }
        for row in rows
    ]


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
    rows = (
        (
            await db.execute(
                select(SkuProfitEstimate)
                .where(*filters)
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "estimate_id": row.estimate_id,
            "sku_id": row.sku_id,
            "estimate_as_of": row.estimate_as_of,
            "assumption_version": row.assumption_version,
            "scenario": row.scenario,
            "selling_price": (
                float(row.selling_price) if row.selling_price is not None else None
            ),
            "coupon_amount": (
                float(row.coupon_amount) if row.coupon_amount is not None else None
            ),
            "estimated_contribution_profit": (
                float(row.estimated_contribution_profit)
                if row.estimated_contribution_profit is not None
                else None
            ),
            "estimated_margin_rate": (
                float(row.estimated_margin_rate)
                if row.estimated_margin_rate is not None
                else None
            ),
            "cost_completeness": row.cost_completeness,
            "confidence_level": row.confidence_level,
        }
        for row in rows
    ]


@router.post("/api/product-profit-estimates", status_code=201)
async def create_profit_estimate(
    body: ProfitEstimateCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    if await db.get(DimErpSku, body.sku_id) is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    values = body.model_dump()
    revenue = (values.get("selling_price") or 0) - (values.get("coupon_amount") or 0)
    costs = sum(
        values.get(key) or 0
        for key in (
            "purchase_cost",
            "logistics_cost",
            "storage_cost",
            "platform_fee",
            "expected_return_loss",
            "expected_damage_loss",
        )
    )
    values["estimated_contribution_profit"] = revenue - costs
    values["estimated_margin_rate"] = (
        (revenue - costs) / revenue if revenue > 0 else None
    )
    row = SkuProfitEstimate(**values)
    db.add(row)
    await db.flush()
    await _write_product_center_audit(
        db,
        _user,
        action_type="create",
        resource_type="profit_estimate",
        resource_id=str(row.estimate_id),
        changes=values,
    )
    await db.commit()
    await db.refresh(row)
    return {
        "estimate_id": row.estimate_id,
        "sku_id": row.sku_id,
        "estimated_contribution_profit": float(row.estimated_contribution_profit),
        "estimated_margin_rate": (
            float(row.estimated_margin_rate)
            if row.estimated_margin_rate is not None
            else None
        ),
    }


@router.post("/api/product-profit-estimates/preview")
async def preview_product_profit(
    body: ProfitPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    try:
        result = await ProductFinanceService(db).preview_profit(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        key: float(value) if hasattr(value, "as_tuple") else value
        for key, value in result.items()
    }


@router.post("/api/product-profit-estimates/baseline", status_code=201)
async def save_baseline_product_profit(
    body: ProfitEstimateSaveRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_editor),
):
    try:
        row = await ProductFinanceService(db).save_profit_estimate(body.model_dump())
        await FeishuProjectionService(db).enqueue(
            "sku",
            str(row.sku_id),
            {
                "sku_id": row.sku_id,
                "reason": "baseline_profit_saved",
                "estimate_id": row.estimate_id,
            },
        )
        await _write_product_center_audit(
            db,
            _user,
            action_type="create",
            resource_type="profit_estimate",
            resource_id=str(row.estimate_id),
            changes=body.model_dump(mode="json"),
        )
        await db.commit()
        asyncio.create_task(trigger_pending_projection_delivery())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "estimate_id": row.estimate_id,
        "sku_id": row.sku_id,
        "scenario": row.scenario,
    }


@router.post("/api/feishu-projection/initialize")
async def initialize_feishu_projection(
    body: FeishuProjectionInitializeRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_projection_admin),
):
    spu_table_id = body.spu_table_id or os.getenv("FEISHU_PRODUCT_SPU_TABLE_ID")
    sku_table_id = body.sku_table_id or os.getenv("FEISHU_PRODUCT_SKU_TABLE_ID")
    platform_sku_profit_table_id = body.platform_sku_profit_table_id or os.getenv(
        "FEISHU_PRODUCT_PLATFORM_SKU_PROFIT_TABLE_ID"
    )
    price_adjust_table_id = body.price_adjust_table_id or os.getenv(
        "FEISHU_PRODUCT_PRICE_ADJUST_TABLE_ID"
    )
    price_adjust_base_token = body.price_adjust_base_token or os.getenv(
        "FEISHU_PRODUCT_PRICE_ADJUST_BASE_TOKEN"
    )
    client = FeishuProjectionClient()
    try:
        config = await FeishuProjectionService(db).initialize_tables(
            client,
            spu_table_id,
            sku_table_id,
            platform_sku_profit_table_id,
            price_adjust_table_id,
            price_adjust_base_token,
        )
        await _write_product_center_audit(
            db,
            _user,
            action_type="initialize",
            resource_type="feishu_projection",
            resource_id=config.provider_code,
            changes={"status": config.status, "projection_tables_initialized": True},
        )
        await db.commit()
    except RuntimeError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": config.status,
        "spu_table_id": config.spu_table_id,
        "sku_table_id": config.sku_table_id,
        "platform_sku_profit_table_id": config.platform_sku_profit_table_id,
        "price_adjust_table_id": config.price_adjust_table_id,
        "price_adjust_base_token": config.price_adjust_base_token,
    }


@router.get("/api/feishu-projection/status")
async def get_feishu_projection_status(db: AsyncSession = Depends(get_async_db)):
    return await FeishuProjectionService(db).status()


@router.post("/api/feishu-projection/retry-failed")
async def retry_failed_feishu_projection(
    db: AsyncSession = Depends(get_async_db), _user=Depends(_require_projection_admin)
):
    retried = await FeishuProjectionService(db).retry_failed()
    await _write_product_center_audit(
        db,
        _user,
        action_type="retry",
        resource_type="feishu_projection",
        resource_id="failed_tasks",
        changes={"retried": retried},
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
        (
            await db.execute(
                text(
                    f"SELECT * FROM mart.spu_operating_current {where} ORDER BY spu LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
