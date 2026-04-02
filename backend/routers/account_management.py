"""
Legacy-compatible account management routes.

This router preserves `/api/accounts/*` for compatibility while serving data
from the canonical `main_accounts` / `shop_accounts` / `shop_account_aliases`
tables introduced during the account model redesign.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.account import (
    AccountCreate,
    AccountResponse,
    AccountStats,
    AccountUpdate,
    BatchCreateRequest,
    UnmatchedShopAliasItem,
    UnmatchedShopAliasResponse,
)
from backend.services.encryption_service import get_encryption_service
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/accounts", tags=["账号管理"])


def _extract_legacy_shop_extra(shop: ShopAccount) -> dict:
    data = shop.extra_config or {}
    return {
        "proxy_required": bool(data.get("legacy_proxy_required", False)),
        "currency": data.get("legacy_currency", "CNY"),
        "region": data.get("legacy_region", "CN"),
        "email": data.get("legacy_email"),
        "phone": data.get("legacy_phone"),
    }


async def _serialize_account_response(
    db: AsyncSession,
    shop: ShopAccount,
) -> AccountResponse:
    main = (
        await db.execute(
            select(MainAccount).where(
                MainAccount.main_account_id == shop.main_account_id,
                MainAccount.platform == shop.platform,
            )
        )
    ).scalar_one_or_none()
    aliases = (
        await db.execute(
            select(ShopAccountAlias).where(
                ShopAccountAlias.shop_account_id == shop.id,
                ShopAccountAlias.is_active == True,
            )
        )
    ).scalars().all()
    primary_alias = next((alias.alias_value for alias in aliases if alias.is_primary), None)
    capabilities = {
        row.data_domain: bool(row.enabled)
        for row in (
            await db.execute(
                select(ShopAccountCapability).where(
                    ShopAccountCapability.shop_account_id == shop.id
                )
            )
        ).scalars().all()
    }
    legacy_extra = _extract_legacy_shop_extra(shop)

    return AccountResponse(
        id=shop.id,
        account_id=shop.shop_account_id,
        parent_account=shop.main_account_id,
        platform=shop.platform,
        account_alias=primary_alias,
        store_name=shop.store_name,
        shop_type=shop.shop_type,
        shop_region=shop.shop_region,
        shop_id=shop.platform_shop_id,
        username=main.username if main else "",
        login_url=main.login_url if main else None,
        email=legacy_extra["email"],
        phone=legacy_extra["phone"],
        region=legacy_extra["region"],
        currency=legacy_extra["currency"],
        capabilities=capabilities,
        enabled=shop.enabled,
        proxy_required=legacy_extra["proxy_required"],
        notes=shop.notes,
        created_at=shop.created_at,
        updated_at=shop.updated_at,
        created_by=shop.created_by,
        updated_by=shop.updated_by,
    )


async def _get_shop_or_404(db: AsyncSession, shop_account_id: str) -> ShopAccount:
    result = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
    )
    shop = result.scalar_one_or_none()
    if shop is None:
        raise HTTPException(status_code=404, detail=f"店铺账号ID '{shop_account_id}' 不存在")
    return shop


async def _invalidate_dashboard_cache(request: Request | None) -> None:
    if request is None:
        return
    cache_service = getattr(request.app.state, "cache_service", None)
    if cache_service is None:
        return
    try:
        await cache_service.invalidate_dashboard_business_overview()
    except Exception as exc:
        logger.warning(f"[AccountManagement] 失效 Dashboard 缓存失败: {exc}", exc_info=True)


@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    main = (
        await db.execute(
            select(MainAccount).where(
                MainAccount.platform == account.platform,
                MainAccount.main_account_id == (account.parent_account or account.account_id),
            )
        )
    ).scalar_one_or_none()
    if main is None:
        encryption_service = get_encryption_service()
        main = MainAccount(
            platform=account.platform,
            main_account_id=account.parent_account or account.account_id,
            username=account.username,
            password_encrypted=encryption_service.encrypt_password(account.password),
            login_url=account.login_url,
            enabled=account.enabled,
            notes=account.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(main)
        await db.flush()

    existing = await db.execute(
        select(ShopAccount).where(ShopAccount.shop_account_id == account.account_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"店铺账号ID '{account.account_id}' 已存在")

    shop = ShopAccount(
        platform=account.platform,
        shop_account_id=account.account_id,
        main_account_id=main.main_account_id,
        store_name=account.store_name,
        platform_shop_id=account.shop_id,
        platform_shop_id_status="manual_confirmed" if account.shop_id else "missing",
        shop_region=account.shop_region,
        shop_type=account.shop_type,
        enabled=account.enabled,
        notes=account.notes,
        extra_config={
            "legacy_proxy_required": account.proxy_required,
            "legacy_currency": account.currency,
            "legacy_region": account.region,
            "legacy_email": account.email,
            "legacy_phone": account.phone,
        },
        created_by="system",
        updated_by="system",
    )
    db.add(shop)
    await db.flush()

    for domain, enabled in account.capabilities.model_dump().items():
        db.add(
            ShopAccountCapability(
                shop_account_id=shop.id,
                data_domain=domain,
                enabled=enabled,
            )
        )
    if account.account_alias:
        db.add(
            ShopAccountAlias(
                shop_account_id=shop.id,
                platform=account.platform,
                alias_value=account.account_alias,
                alias_normalized=account.account_alias.strip().lower(),
                alias_type="legacy_compat",
                source="accounts_router",
                is_primary=True,
                is_active=True,
            )
        )

    await db.commit()
    await db.refresh(shop)
    await _invalidate_dashboard_cache(request)
    return await _serialize_account_response(db, shop)


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="平台筛选"),
    enabled: Optional[bool] = Query(None, description="启用状态筛选"),
    shop_type: Optional[str] = Query(None, description="店铺类型筛选"),
    search: Optional[str] = Query(None, description="搜索店铺名称或店铺账号ID"),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ShopAccount)
    if platform:
        stmt = stmt.where(ShopAccount.platform.ilike(platform))
    if enabled is not None:
        stmt = stmt.where(ShopAccount.enabled == enabled)
    if shop_type:
        stmt = stmt.where(ShopAccount.shop_type == shop_type)
    if search:
        stmt = stmt.where(
            ShopAccount.store_name.ilike(f"%{search}%")
            | ShopAccount.shop_account_id.ilike(f"%{search}%")
        )
    stmt = stmt.order_by(ShopAccount.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _serialize_account_response(db, row) for row in rows]


@router.get("/unmatched-shop-aliases", response_model=UnmatchedShopAliasResponse)
async def get_unmatched_shop_aliases(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            WITH raw_candidates AS (
                SELECT
                    'shopee'::varchar AS platform,
                    NULLIF(TRIM(COALESCE(raw_data->>'站点', raw_data->>'site')), '') AS site,
                    NULLIF(TRIM(COALESCE(raw_data->>'店铺', raw_data->>'店铺名', raw_data->>'店铺名称', raw_data->>'store_name', raw_data->>'store_label_raw')), '') AS store_label_raw,
                    COALESCE(raw_data->>'订单号', raw_data->>'order_id') AS order_id,
                    COALESCE(NULLIF(raw_data->>'实付金额', '')::numeric, 0) AS paid_amount
                FROM b_class.fact_shopee_orders_daily
                WHERE COALESCE(shop_id, '') IN ('', 'none', 'unknown')
                UNION ALL
                SELECT
                    'tiktok'::varchar AS platform,
                    NULLIF(TRIM(COALESCE(raw_data->>'站点', raw_data->>'site')), '') AS site,
                    NULLIF(TRIM(COALESCE(raw_data->>'店铺', raw_data->>'店铺名', raw_data->>'店铺名称', raw_data->>'store_name', raw_data->>'store_label_raw')), '') AS store_label_raw,
                    COALESCE(raw_data->>'订单号', raw_data->>'order_id') AS order_id,
                    COALESCE(NULLIF(raw_data->>'买家实付金额', '')::numeric, 0) AS paid_amount
                FROM b_class.fact_tiktok_orders_daily
                WHERE COALESCE(shop_id, '') IN ('', 'none', 'unknown')
            ),
            grouped AS (
                SELECT
                    platform,
                    site,
                    store_label_raw,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT order_id) AS order_count,
                    COALESCE(SUM(paid_amount), 0) AS paid_amount
                FROM raw_candidates
                WHERE store_label_raw IS NOT NULL
                GROUP BY platform, site, store_label_raw
            )
            SELECT
                g.platform,
                g.site,
                g.store_label_raw,
                g.row_count,
                g.order_count,
                g.paid_amount
            FROM grouped g
            WHERE NOT EXISTS (
                SELECT 1
                FROM core.shop_account_aliases saa
                WHERE LOWER(COALESCE(saa.platform, '')) = LOWER(g.platform)
                  AND LOWER(COALESCE(saa.alias_normalized, '')) = LOWER(g.store_label_raw)
                  AND saa.is_active = true
            )
            ORDER BY g.paid_amount DESC, g.row_count DESC, g.platform, g.store_label_raw
            """
        )
    )
    items = [UnmatchedShopAliasItem(**dict(row)) for row in result.mappings().all()]
    return UnmatchedShopAliasResponse(items=items, count=len(items))


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    shop = await _get_shop_or_404(db, account_id)
    return await _serialize_account_response(db, shop)


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    account_update: AccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    shop = await _get_shop_or_404(db, account_id)
    update_data = account_update.model_dump(exclude_unset=True)
    shop.store_name = update_data.get("store_name", shop.store_name)
    shop.shop_type = update_data.get("shop_type", shop.shop_type)
    shop.shop_region = update_data.get("shop_region", shop.shop_region)
    if "shop_id" in update_data:
        shop.platform_shop_id = update_data["shop_id"]
        shop.platform_shop_id_status = "manual_confirmed" if update_data["shop_id"] else "missing"
    if "enabled" in update_data and update_data["enabled"] is not None:
        shop.enabled = update_data["enabled"]
    if "notes" in update_data:
        shop.notes = update_data["notes"]
    shop.updated_by = "system"
    shop.updated_at = datetime.now(timezone.utc)

    main = (
        await db.execute(
            select(MainAccount).where(
                MainAccount.platform == shop.platform,
                MainAccount.main_account_id == shop.main_account_id,
            )
        )
    ).scalar_one_or_none()
    if main is not None:
        if update_data.get("username") is not None:
            main.username = update_data["username"]
        if update_data.get("login_url") is not None:
            main.login_url = update_data["login_url"]
        if update_data.get("password"):
            encryption_service = get_encryption_service()
            main.password_encrypted = encryption_service.encrypt_password(update_data["password"])
        if update_data.get("enabled") is not None:
            main.enabled = update_data["enabled"]
        if update_data.get("notes") is not None:
            main.notes = update_data["notes"]
        main.updated_by = "system"
        main.updated_at = datetime.now(timezone.utc)

    if update_data.get("capabilities") is not None:
        capabilities = update_data["capabilities"]
        if hasattr(capabilities, "model_dump"):
            capabilities = capabilities.model_dump()
        existing_capabilities = (
            await db.execute(
                select(ShopAccountCapability).where(
                    ShopAccountCapability.shop_account_id == shop.id
                )
            )
        ).scalars().all()
        existing_map = {row.data_domain: row for row in existing_capabilities}
        for domain, enabled_value in capabilities.items():
            row = existing_map.get(domain)
            if row is None:
                db.add(
                    ShopAccountCapability(
                        shop_account_id=shop.id,
                        data_domain=domain,
                        enabled=enabled_value,
                    )
                )
            else:
                row.enabled = enabled_value

    await db.commit()
    await db.refresh(shop)
    await _invalidate_dashboard_cache(request)
    return await _serialize_account_response(db, shop)


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    shop = await _get_shop_or_404(db, account_id)
    await db.delete(shop)
    await db.commit()
    await _invalidate_dashboard_cache(request)
    return {"message": f"店铺账号 '{account_id}' 已删除"}


@router.post("/batch", response_model=List[AccountResponse])
async def batch_create_accounts(
    batch_request: BatchCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    encryption_service = get_encryption_service()
    main = (
        await db.execute(
            select(MainAccount).where(
                MainAccount.platform == batch_request.platform,
                MainAccount.main_account_id == batch_request.parent_account,
            )
        )
    ).scalar_one_or_none()
    if main is None:
        main = MainAccount(
            platform=batch_request.platform,
            main_account_id=batch_request.parent_account,
            username=batch_request.username,
            password_encrypted=encryption_service.encrypt_password(batch_request.password),
            enabled=True,
            created_by="system",
            updated_by="system",
        )
        db.add(main)
        await db.flush()

    created_accounts: list[ShopAccount] = []
    for shop in batch_request.shops:
        shop_account_id = (
            f"{batch_request.platform}_"
            f"{shop.get('shop_region', 'unknown').lower()}_"
            f"{shop.get('store_name', 'shop')}"
        )
        existing = await db.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
        )
        if existing.scalar_one_or_none() is not None:
            continue

        record = ShopAccount(
            platform=batch_request.platform,
            shop_account_id=shop_account_id,
            main_account_id=batch_request.parent_account,
            store_name=shop.get("store_name"),
            shop_type=shop.get("shop_type", "local"),
            shop_region=shop.get("shop_region"),
            enabled=True,
            created_by="system",
            updated_by="system",
        )
        db.add(record)
        await db.flush()
        created_accounts.append(record)

        capabilities = {
            "orders": True,
            "products": True,
            "services": shop.get("shop_type") == "local",
            "analytics": True,
            "finance": True,
            "inventory": True,
        }
        for domain, enabled in capabilities.items():
            db.add(
                ShopAccountCapability(
                    shop_account_id=record.id,
                    data_domain=domain,
                    enabled=enabled,
                )
            )
        if shop.get("account_alias"):
            db.add(
                ShopAccountAlias(
                    shop_account_id=record.id,
                    platform=batch_request.platform,
                    alias_value=shop["account_alias"],
                    alias_normalized=str(shop["account_alias"]).strip().lower(),
                    alias_type="legacy_batch_alias",
                    source="accounts_batch_router",
                    is_primary=True,
                    is_active=True,
                )
            )

    await db.commit()
    await _invalidate_dashboard_cache(request)
    return [await _serialize_account_response(db, item) for item in created_accounts]


@router.get("/stats/summary", response_model=AccountStats)
async def get_account_stats(
    db: AsyncSession = Depends(get_async_db),
):
    rows = (await db.execute(select(ShopAccount))).scalars().all()
    total = len(rows)
    active = sum(1 for account in rows if account.enabled)
    inactive = total - active
    platform_breakdown: dict[str, int] = {}
    for account in rows:
        platform_breakdown[account.platform] = platform_breakdown.get(account.platform, 0) + 1
    return AccountStats(
        total=total,
        active=active,
        inactive=inactive,
        platforms=len(platform_breakdown),
        platform_breakdown=platform_breakdown,
    )
