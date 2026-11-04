from typing import Dict, List, Optional

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
    """把一个店铺账号序列化成「目录项」。

    显示名口径（全站唯一，与前端 ``frontend/src/utils/shopDisplay.js`` 保持一致）：

        主名 = internal_code（内部编号，唯一且不随改名变化）
             → account_alias（人工别名）
             → store_name（平台原始店名）
             → 键值（shop_id）

        副显 = store_name / account_alias（主名之外的另一个可读名字）

    为什么主名用 internal_code
    -------------------------
    平台上能看到的是店名（"xhkj11.sg"），但**店名会改、别名会改**；
    internal_code 是内部编号，唯一且稳定 —— 报表、截图、对账都以它为准。
    以前这个接口只给 ``display_name``（别名优先）而**不给 internal_code**，
    前端就算想按内部编号显示也拿不到。
    """
    canonical_name = str(getattr(record, "store_name", "") or "").strip()
    internal_code = str(getattr(record, "internal_code", "") or "").strip()
    shop_id = (
        str(getattr(record, "platform_shop_id", "") or "").strip()
        or str(getattr(record, "shop_account_id", "") or "").strip()
    )
    normalized_alias = normalize_alias_text(account_alias)
    display_name = internal_code or normalized_alias or canonical_name or shop_id
    secondary_name = (
        canonical_name if canonical_name != display_name else normalized_alias or ""
    )
    return ShopDirectoryItemResponse(
        platform_code=str(getattr(record, "platform", "") or "").strip().lower(),
        shop_id=shop_id,
        shop_account_id=str(getattr(record, "shop_account_id", "") or "").strip(),
        main_account_id=str(getattr(record, "main_account_id", "") or "").strip(),
        display_name=display_name,
        canonical_name=canonical_name,
        internal_code=internal_code,
        secondary_name=secondary_name,
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
    if not records:
        return []

    # ⚠️ 以前是「每个账号查一次别名」⇒ N+1 查询（52 个店就是 52 条 SQL）。
    # 现在一次把全部别名捞回来，在内存里按账号分组。
    account_ids = [record.id for record in records]
    alias_rows = (
        (
            await db.execute(
                select(ShopAccountAlias).where(
                    ShopAccountAlias.shop_account_id.in_(account_ids),
                    ShopAccountAlias.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    aliases_by_account: Dict[int, List[ShopAccountAlias]] = {}
    for alias in alias_rows:
        aliases_by_account.setdefault(alias.shop_account_id, []).append(alias)

    items: list[ShopDirectoryItemResponse] = []
    for record in records:
        aliases = aliases_by_account.get(record.id, [])
        primary_alias = next(
            (alias.alias_value for alias in aliases if alias.is_primary), None
        )
        if primary_alias is None:
            primary_alias = next((alias.alias_value for alias in aliases), None)
        items.append(_serialize_shop_directory_item(record, primary_alias))
    return items
