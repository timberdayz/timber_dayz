from __future__ import annotations

import codecs
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.account import UnmatchedShopAliasItem, UnmatchedShopAliasResponse
from backend.schemas.shop_account_alias import ShopAccountAliasCreate, ShopAccountAliasResponse
from backend.utils.text_normalization import normalize_alias_key, normalize_alias_text
from modules.core.db import ShopAccount, ShopAccountAlias


router = APIRouter(prefix="/shop-account-aliases", tags=["Shop Account Aliases"])


def _u(value: str) -> str:
    return codecs.decode(value, "unicode_escape")


_CN_SITE = _u(r"\u7ad9\u70b9")
_CN_STORE = _u(r"\u5e97\u94fa")
_CN_STORE_SHORT = _u(r"\u5e97\u94fa\u540d")
_CN_STORE_NAME = _u(r"\u5e97\u94fa\u540d\u79f0")
_CN_ORDER_ID = _u(r"\u8ba2\u5355\u53f7")
_CN_SHOPEE_PAID = _u(r"\u5b9e\u4ed8\u91d1\u989d")
_CN_TIKTOK_PAID = _u(r"\u652f\u4ed8\u91d1\u989d")


_UNMATCHED_ALIAS_QUERY = """
WITH raw_candidates AS (
    SELECT
        'shopee'::varchar AS platform,
        NULLIF(TRIM(COALESCE(raw_data->>:cn_site, raw_data->>'site')), '') AS site,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>:cn_store,
                    raw_data->>:cn_store_short,
                    raw_data->>:cn_store_name,
                    raw_data->>'store_name',
                    raw_data->>'store_label_raw'
                )
            ),
            ''
        ) AS store_label_raw,
        COALESCE(raw_data->>:cn_order_id, raw_data->>'order_id') AS order_id,
        COALESCE(NULLIF(raw_data->>:cn_shopee_paid, '')::numeric, 0) AS paid_amount
    FROM b_class.fact_shopee_orders_daily
    WHERE COALESCE(shop_id, '') IN ('', 'none', 'unknown')

    UNION ALL

    SELECT
        'tiktok'::varchar AS platform,
        NULLIF(TRIM(COALESCE(raw_data->>:cn_site, raw_data->>'site')), '') AS site,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>:cn_store,
                    raw_data->>:cn_store_short,
                    raw_data->>:cn_store_name,
                    raw_data->>'store_name',
                    raw_data->>'store_label_raw'
                )
            ),
            ''
        ) AS store_label_raw,
        COALESCE(raw_data->>:cn_order_id, raw_data->>'order_id') AS order_id,
        COALESCE(NULLIF(raw_data->>:cn_tiktok_paid, '')::numeric, 0) AS paid_amount
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


_UNMATCHED_ALIAS_PARAMS = {
    "cn_site": _CN_SITE,
    "cn_store": _CN_STORE,
    "cn_store_short": _CN_STORE_SHORT,
    "cn_store_name": _CN_STORE_NAME,
    "cn_order_id": _CN_ORDER_ID,
    "cn_shopee_paid": _CN_SHOPEE_PAID,
    "cn_tiktok_paid": _CN_TIKTOK_PAID,
}


class ShopAccountAliasClaimRequest(BaseModel):
    platform: str = Field(..., description="platform code")
    alias_value: str = Field(..., description="alias to claim")
    shop_account_id: str = Field(..., description="target shop account id")
    source: str | None = Field(default="manual_claim", description="source")


def _normalize_alias(alias: str) -> str:
    return normalize_alias_key(alias)


def _serialize_alias(record: ShopAccountAlias) -> ShopAccountAliasResponse:
    alias_value = normalize_alias_text(record.alias_value) or ""
    return ShopAccountAliasResponse(
        id=record.id,
        shop_account_id=record.shop_account_id,
        platform=record.platform,
        alias_value=alias_value,
        alias_normalized=_normalize_alias(alias_value),
        alias_type=record.alias_type,
        source=record.source,
        is_primary=record.is_primary,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=List[ShopAccountAliasResponse])
async def list_shop_account_aliases(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(ShopAccountAlias).order_by(ShopAccountAlias.platform, ShopAccountAlias.alias_value)
    )
    return [_serialize_alias(record) for record in result.scalars().all()]


@router.post("", response_model=ShopAccountAliasResponse)
async def create_shop_account_alias(
    payload: ShopAccountAliasCreate,
    db: AsyncSession = Depends(get_async_db),
):
    alias_value = normalize_alias_text(payload.alias_value)
    if not alias_value:
        raise HTTPException(status_code=400, detail="alias_value is required")

    record = ShopAccountAlias(
        shop_account_id=payload.shop_account_id,
        platform=payload.platform,
        alias_value=alias_value,
        alias_normalized=_normalize_alias(alias_value),
        alias_type=payload.alias_type,
        source=payload.source,
        is_primary=payload.is_primary,
        is_active=payload.is_active,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_alias(record)


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
        raise HTTPException(status_code=404, detail=f"shop account id '{payload.shop_account_id}' not found")

    alias_value = normalize_alias_text(payload.alias_value)
    if not alias_value:
        raise HTTPException(status_code=400, detail="alias_value is required")

    record = ShopAccountAlias(
        shop_account_id=shop_account.id,
        platform=payload.platform,
        alias_value=alias_value,
        alias_normalized=_normalize_alias(alias_value),
        alias_type="claimed",
        source=payload.source,
        is_primary=False,
        is_active=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_alias(record)


@router.get("/unmatched", response_model=UnmatchedShopAliasResponse)
async def get_unmatched_shop_aliases(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(text(_UNMATCHED_ALIAS_QUERY), _UNMATCHED_ALIAS_PARAMS)
    items = [UnmatchedShopAliasItem(**dict(row)) for row in result.mappings().all()]
    return UnmatchedShopAliasResponse(items=items, count=len(items))
