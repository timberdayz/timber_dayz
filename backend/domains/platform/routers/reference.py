from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.auth import UserResponse
from backend.schemas.reference import ShopDirectoryItemResponse
from backend.utils.text_normalization import normalize_alias_text
from modules.core.db import ShopAccount, ShopAccountAlias


router = APIRouter(prefix="/reference", tags=["reference"])


def _serialize_shop_directory_item(
    record: ShopAccount,
    account_alias: str | None,
) -> ShopDirectoryItemResponse:
    canonical_name = str(getattr(record, "store_name", "") or "").strip()
    shop_id = (
        str(getattr(record, "platform_shop_id", "") or "").strip()
        or str(getattr(record, "shop_account_id", "") or "").strip()
    )
    normalized_alias = normalize_alias_text(account_alias)
    display_name = normalized_alias or canonical_name or shop_id
    return ShopDirectoryItemResponse(
        platform_code=str(getattr(record, "platform", "") or "").strip().lower(),
        shop_id=shop_id,
        shop_account_id=str(getattr(record, "shop_account_id", "") or "").strip(),
        main_account_id=str(getattr(record, "main_account_id", "") or "").strip(),
        display_name=display_name,
        canonical_name=canonical_name,
        account_alias=normalized_alias,
        shop_region=getattr(record, "shop_region", None),
        enabled=bool(getattr(record, "enabled", False)),
    )


@router.get("/shop-directory", response_model=List[ShopDirectoryItemResponse])
async def list_shop_directory(
    platform_code: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_async_db),
    _current_user: UserResponse = Depends(get_current_user),
):
    stmt = select(ShopAccount).order_by(
        ShopAccount.platform,
        ShopAccount.store_name,
        ShopAccount.shop_account_id,
    )
    if platform_code:
        stmt = stmt.where(ShopAccount.platform == platform_code)
    if enabled is not None:
        stmt = stmt.where(ShopAccount.enabled == enabled)
    records = (await db.execute(stmt)).scalars().all()

    items: list[ShopDirectoryItemResponse] = []
    for record in records:
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
        items.append(_serialize_shop_directory_item(record, primary_alias))
    return items
