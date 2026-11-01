from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.shop_account import (
    ShopAccountCreate,
    ShopAccountResponse,
    ShopAccountUpdate,
)
from backend.services.cache_service import get_cache_service
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.shop_internal_code_service import (
    load_taken_internal_codes,
    suggest_internal_code_for_account,
)
from backend.services.shop_rename_service import (
    apply_store_name_rename as _apply_store_name_rename,
)
from backend.utils.text_normalization import normalize_alias_text
from modules.core.db import (
    MainAccount,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountBusinessRole,
    ShopAccountCapability,
)
from modules.core.logger import get_logger


router = APIRouter(
    prefix="/shop-accounts",
    tags=["shop account management"],
    dependencies=[Depends(require_admin)],
)

logger = get_logger(__name__)

_SHOP_IDENTITY_REFRESH_TARGETS = [
    "semantic.fact_orders_monthly_atomic_mv",
    "semantic.fact_analytics_monthly_atomic_mv",
]
_SHOP_IDENTITY_FIELDS = {
    "main_account_id",
    "store_name",
    "platform_shop_id",
    "platform_shop_id_status",
}


def _default_capabilities_for(shop_type: str | None) -> dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
        "purchase": True,
    }
    if shop_type == "global":
        defaults["services"] = False
    return defaults


async def _load_capabilities(
    db: AsyncSession,
    shop_account_db_id: int,
    shop_type: str | None,
) -> dict[str, bool]:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account_db_id
        )
    )
    rows = capability_result.scalars().all()
    if rows:
        return {
            row.data_domain: bool(row.enabled)
            for row in rows
        }
    return _default_capabilities_for(shop_type)


async def _ensure_capability_rows(
    db: AsyncSession,
    shop_account: ShopAccount,
    *,
    shop_type: str | None = None,
    capabilities: dict[str, bool] | None = None,
) -> None:
    capability_result = await db.execute(
        select(ShopAccountCapability).where(
            ShopAccountCapability.shop_account_id == shop_account.id
        )
    )
    existing = capability_result.scalars().all()
    existing_map = {
        row.data_domain: row
        for row in existing
    }
    target_capabilities = (
        capabilities
        if capabilities is not None
        else _default_capabilities_for(shop_type or shop_account.shop_type)
    )

    for domain, enabled in target_capabilities.items():
        capability_row = existing_map.get(domain)
        if capability_row is not None:
            capability_row.enabled = bool(enabled)
            continue
        db.add(
            ShopAccountCapability(
                shop_account_id=shop_account.id,
                data_domain=str(domain),
                enabled=bool(enabled),
            )
        )


async def _serialize_shop_account(
    db: AsyncSession,
    record: ShopAccount,
    *,
    taken_codes: dict[str, set[str]] | None = None,
) -> ShopAccountResponse:
    alias_result = await db.execute(
        select(ShopAccountAlias).where(
            ShopAccountAlias.shop_account_id == record.id,
            ShopAccountAlias.is_active == True,
        )
    )
    aliases = alias_result.scalars().all()
    primary_alias = next((alias.alias_value for alias in aliases if alias.is_primary), None)
    if primary_alias is None:
        primary_alias = next((alias.alias_value for alias in aliases), None)
    capabilities = await _load_capabilities(db, record.id, record.shop_type)
    suggested_internal_code = await suggest_internal_code_for_account(
        db,
        record,
        taken_codes=taken_codes,
    )
    return ShopAccountResponse(
        id=record.id,
        platform=record.platform,
        shop_account_id=record.shop_account_id,
        main_account_id=record.main_account_id,
        account_alias=normalize_alias_text(primary_alias),
        alias_count=len(aliases),
        capabilities=capabilities,
        store_name=record.store_name,
        internal_code=record.internal_code,
        suggested_internal_code=suggested_internal_code,
        platform_shop_id=record.platform_shop_id,
        platform_shop_id_status=record.platform_shop_id_status,
        shop_region=record.shop_region,
        shop_type=record.shop_type,
        business_role=record.business_role,
        enabled=record.enabled,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _get_shop_account_or_404(db: AsyncSession, shop_account_id: str) -> ShopAccount:
    result = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"shop_account_id '{shop_account_id}' not found")
    return record


async def _assert_platform_shop_id_unique(
    db: AsyncSession,
    *,
    platform: str,
    platform_shop_id: str | None,
    exclude_id: int | None = None,
) -> None:
    normalized_platform_shop_id = (platform_shop_id or "").strip()
    if not normalized_platform_shop_id:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.platform == platform,
        ShopAccount.platform_shop_id == normalized_platform_shop_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"platform_shop_id '{normalized_platform_shop_id}' already exists "
                f"for platform '{platform}' on shop_account_id '{existing.shop_account_id}'"
            ),
        )


async def _assert_internal_code_unique(
    db: AsyncSession,
    *,
    platform: str,
    internal_code: str | None,
    exclude_id: int | None = None,
) -> None:
    """内部标准名同平台内唯一（库层约束 uq_shop_accounts_platform_internal_code）。

    这里把约束翻译成人话：冲突时告诉运营「这个名字被哪个店占用了」。
    """
    normalized_internal_code = (internal_code or "").strip()
    if not normalized_internal_code:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.platform == platform,
        ShopAccount.internal_code == normalized_internal_code,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"内部标准名 '{normalized_internal_code}' 已被平台 '{platform}' 的店铺账号 "
                f"'{existing.shop_account_id}'（店名 {existing.store_name}）占用"
            ),
        )


async def _assert_store_name_unique_in_main_account(
    db: AsyncSession,
    main_account_id: str,
    store_name: str | None,
    *,
    exclude_id: int | None = None,
) -> None:
    """同一个主账号下店铺名唯一（改名联动的第一步校验）。"""
    normalized_store_name = (store_name or "").strip()
    if not normalized_store_name:
        return

    stmt = select(ShopAccount).where(
        ShopAccount.main_account_id == main_account_id,
        ShopAccount.store_name == normalized_store_name,
    )
    if exclude_id is not None:
        stmt = stmt.where(ShopAccount.id != exclude_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"主账号 '{main_account_id}' 下已存在同名店铺 '{normalized_store_name}'"
                f"（店铺账号 '{existing.shop_account_id}'）"
            ),
        )


async def _assert_main_account_exists(
    db: AsyncSession, platform: str, main_account_id: str
) -> None:
    result = await db.execute(
        select(MainAccount).where(
            MainAccount.platform == platform,
            MainAccount.main_account_id == main_account_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail=f"main_account_id '{main_account_id}' not found")


async def _enqueue_shop_identity_refresh(
    db: AsyncSession,
    *,
    shop_account: ShopAccount,
    changed_fields: list[str],
) -> None:
    if not changed_fields:
        return
    try:
        await RefreshQueueService(db).enqueue_refresh(
            trigger_type="shop_identity_changed",
            pipeline_name="postgresql_dashboard",
            targets=_SHOP_IDENTITY_REFRESH_TARGETS,
            context={
                "shop_account_id": shop_account.shop_account_id,
                "shop_account_db_id": shop_account.id,
                "platform": shop_account.platform,
                "changed_fields": changed_fields,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to enqueue dashboard refresh for shop_account_id=%s: %s",
            shop_account.shop_account_id,
            exc,
            exc_info=True,
        )
    try:
        await get_cache_service().invalidate_dashboard_business_overview()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ShopIdentity] failed to invalidate business overview cache for shop_account_id=%s: %s",
            shop_account.shop_account_id,
            exc,
            exc_info=True,
        )


@router.get("", response_model=List[ShopAccountResponse])
async def list_shop_accounts(
    platform: Optional[str] = Query(None),
    main_account_id: Optional[str] = Query(None),
    business_role: Optional[ShopAccountBusinessRole] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ShopAccount).order_by(ShopAccount.platform, ShopAccount.shop_account_id)
    if platform:
        stmt = stmt.where(ShopAccount.platform == platform)
    if main_account_id:
        stmt = stmt.where(ShopAccount.main_account_id == main_account_id)
    if business_role is not None:
        stmt = stmt.where(ShopAccount.business_role == business_role)
    if enabled is not None:
        stmt = stmt.where(ShopAccount.enabled == enabled)
    result = await db.execute(stmt)
    records = result.scalars().all()
    taken_codes = await load_taken_internal_codes(db)
    return [
        await _serialize_shop_account(db, record, taken_codes=taken_codes)
        for record in records
    ]


@router.post("", response_model=ShopAccountResponse)
async def create_shop_account(
    payload: ShopAccountCreate,
    db: AsyncSession = Depends(get_async_db),
):
    await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
    await _assert_platform_shop_id_unique(
        db,
        platform=payload.platform,
        platform_shop_id=payload.platform_shop_id,
    )
    normalized_internal_code = str(payload.internal_code or "").strip() or None
    if normalized_internal_code:
        await _assert_internal_code_unique(
            db,
            platform=payload.platform,
            internal_code=normalized_internal_code,
        )
    existing = await db.execute(
        select(ShopAccount).where(
            ShopAccount.platform == payload.platform,
            ShopAccount.shop_account_id == payload.shop_account_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"shop_account_id '{payload.shop_account_id}' already exists")

    record = ShopAccount(
        platform=payload.platform,
        shop_account_id=payload.shop_account_id,
        main_account_id=payload.main_account_id,
        store_name=payload.store_name,
        internal_code=normalized_internal_code,
        platform_shop_id=payload.platform_shop_id,
        platform_shop_id_status="manual_confirmed" if payload.platform_shop_id else "missing",
        shop_region=payload.shop_region,
        shop_type=payload.shop_type,
        business_role=payload.business_role,
        enabled=payload.enabled,
        notes=payload.notes,
        created_by="system",
        updated_by="system",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await _ensure_capability_rows(
        db,
        record,
        shop_type=payload.shop_type,
        capabilities=payload.capabilities,
    )
    await db.commit()
    return await _serialize_shop_account(db, record)


@router.post("/batch", response_model=List[ShopAccountResponse])
async def batch_create_shop_accounts(
    payloads: List[ShopAccountCreate],
    db: AsyncSession = Depends(get_async_db),
):
    created: List[tuple[ShopAccount, ShopAccountCreate]] = []
    for payload in payloads:
        await _assert_main_account_exists(db, payload.platform, payload.main_account_id)
        existing = await db.execute(
            select(ShopAccount).where(
                ShopAccount.platform == payload.platform,
                ShopAccount.shop_account_id == payload.shop_account_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        normalized_internal_code = str(payload.internal_code or "").strip() or None
        if normalized_internal_code:
            await _assert_internal_code_unique(
                db,
                platform=payload.platform,
                internal_code=normalized_internal_code,
            )
        record = ShopAccount(
            platform=payload.platform,
            shop_account_id=payload.shop_account_id,
            main_account_id=payload.main_account_id,
            store_name=payload.store_name,
            internal_code=normalized_internal_code,
            platform_shop_id=payload.platform_shop_id,
            platform_shop_id_status="manual_confirmed" if payload.platform_shop_id else "missing",
            shop_region=payload.shop_region,
            shop_type=payload.shop_type,
            business_role=payload.business_role,
            enabled=payload.enabled,
            notes=payload.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(record)
        created.append((record, payload))
    await db.commit()
    for record, payload in created:
        await db.refresh(record)
        await _ensure_capability_rows(
            db,
            record,
            shop_type=record.shop_type,
            capabilities=payload.capabilities,
        )
    await db.commit()
    return [await _serialize_shop_account(db, record) for record, _ in created]


@router.put("/{shop_account_id}", response_model=ShopAccountResponse)
async def update_shop_account(
    shop_account_id: str,
    payload: ShopAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    capabilities_submitted = "capabilities" in update_data
    capabilities = update_data.pop("capabilities", None)
    # 改名联动的两个「原值」必须在赋值前抓住 —— 前端每次提交的是整个表单
    original_store_name = record.store_name
    original_internal_code = record.internal_code
    if "platform_shop_id" in update_data:
        await _assert_platform_shop_id_unique(
            db,
            platform=record.platform,
            platform_shop_id=update_data["platform_shop_id"],
            exclude_id=record.id,
        )
    if "internal_code" in update_data:
        # 空串 = 清空标准名（内部标准名不参与匹配，清掉不影响历史数据）
        normalized_internal_code = str(update_data["internal_code"] or "").strip()
        update_data["internal_code"] = normalized_internal_code or None
        await _assert_internal_code_unique(
            db,
            platform=record.platform,
            internal_code=normalized_internal_code,
            exclude_id=record.id,
        )
    if "store_name" in update_data:
        await _assert_store_name_unique_in_main_account(
            db,
            record.main_account_id,
            update_data["store_name"],
            exclude_id=record.id,
        )
    # 1) 先按现有逻辑全量赋值（保留 platform_shop_id 唯一性校验与 capabilities 处理）
    for field, value in update_data.items():
        setattr(record, field, value)
    # 2) 再对 store_name 走改名联动。
    #    注意：前端每次编辑提交整个表单（store_name 恒存在），
    #    若把改名做成 if/else，else 分支永远不走 -> 其它字段全部不落库。
    if "store_name" in update_data and update_data["store_name"] != original_store_name:
        await _apply_store_name_rename(
            db,
            record,
            update_data["store_name"],
            old_store_name=original_store_name,
            original_internal_code=original_internal_code,
        )
    if capabilities_submitted or "shop_type" in update_data:
        await _ensure_capability_rows(
            db,
            record,
            shop_type=update_data.get("shop_type", record.shop_type),
            capabilities=capabilities,
        )
    record.updated_at = datetime.now(timezone.utc)
    record.updated_by = "system"
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(record)
    changed_identity_fields = [
        field for field in update_data.keys() if field in _SHOP_IDENTITY_FIELDS
    ]
    # 改名一定会带上 store_name -> 归属重算已经由这一次入队覆盖
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=record,
        changed_fields=changed_identity_fields,
    )
    return await _serialize_shop_account(db, record)


@router.delete("/{shop_account_id}")
async def delete_shop_account(
    shop_account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    await db.delete(record)
    await db.commit()
    return {"message": f"shop_account_id '{shop_account_id}' deleted"}
