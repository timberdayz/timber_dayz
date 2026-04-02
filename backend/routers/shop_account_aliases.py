from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.account import UnmatchedShopAliasItem, UnmatchedShopAliasResponse
from backend.schemas.shop_account_alias import ShopAccountAliasCreate, ShopAccountAliasResponse
from modules.core.db import ShopAccount, ShopAccountAlias


router = APIRouter(prefix="/shop-account-aliases", tags=["店铺别名管理"])


class ShopAccountAliasClaimRequest(BaseModel):
    platform: str = Field(..., description="平台代码")
    alias_value: str = Field(..., description="待认领别名")
    shop_account_id: str = Field(..., description="目标店铺账号ID")
    source: str | None = Field(default="manual_claim", description="来源")


def _normalize_alias(alias: str) -> str:
    return " ".join(str(alias or "").strip().lower().split())


@router.get("", response_model=List[ShopAccountAliasResponse])
async def list_shop_account_aliases(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(ShopAccountAlias).order_by(ShopAccountAlias.platform, ShopAccountAlias.alias_value)
    )
    return result.scalars().all()


@router.post("", response_model=ShopAccountAliasResponse)
async def create_shop_account_alias(
    payload: ShopAccountAliasCreate,
    db: AsyncSession = Depends(get_async_db),
):
    record = ShopAccountAlias(
        shop_account_id=payload.shop_account_id,
        platform=payload.platform,
        alias_value=payload.alias_value,
        alias_normalized=_normalize_alias(payload.alias_value),
        alias_type=payload.alias_type,
        source=payload.source,
        is_primary=payload.is_primary,
        is_active=payload.is_active,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.post("/claim", response_model=ShopAccountAliasResponse)
async def claim_shop_account_alias(
    payload: ShopAccountAliasClaimRequest,
    db: AsyncSession = Depends(get_async_db),
):
    shop_account = (
        await db.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == payload.shop_account_id)
        )
    ).scalar_one_or_none()
    if shop_account is None:
        raise HTTPException(status_code=404, detail=f"店铺账号ID '{payload.shop_account_id}' 不存在")

    record = ShopAccountAlias(
        shop_account_id=shop_account.id,
        platform=payload.platform,
        alias_value=payload.alias_value,
        alias_normalized=_normalize_alias(payload.alias_value),
        alias_type="claimed",
        source=payload.source,
        is_primary=False,
        is_active=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/unmatched", response_model=UnmatchedShopAliasResponse)
async def get_unmatched_shop_aliases(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            WITH raw_candidates AS (
                SELECT
                    'shopee'::varchar AS platform,
                    NULLIF(TRIM(COALESCE(raw_data->>'绔欑偣', raw_data->>'site')), '') AS site,
                    NULLIF(TRIM(COALESCE(raw_data->>'搴楅摵', raw_data->>'搴楅摵鍚?, raw_data->>'搴楅摵鍚嶇О', raw_data->>'store_name', raw_data->>'store_label_raw')), '') AS store_label_raw,
                    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'order_id') AS order_id,
                    COALESCE(NULLIF(raw_data->>'瀹炰粯閲戦', '')::numeric, 0) AS paid_amount
                FROM b_class.fact_shopee_orders_daily
                WHERE COALESCE(shop_id, '') IN ('', 'none', 'unknown')
                UNION ALL
                SELECT
                    'tiktok'::varchar AS platform,
                    NULLIF(TRIM(COALESCE(raw_data->>'绔欑偣', raw_data->>'site')), '') AS site,
                    NULLIF(TRIM(COALESCE(raw_data->>'搴楅摵', raw_data->>'搴楅摵鍚?, raw_data->>'搴楅摵鍚嶇О', raw_data->>'store_name', raw_data->>'store_label_raw')), '') AS store_label_raw,
                    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'order_id') AS order_id,
                    COALESCE(NULLIF(raw_data->>'涔板瀹炰粯閲戦', '')::numeric, 0) AS paid_amount
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
