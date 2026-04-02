from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
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
